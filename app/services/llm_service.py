"""
Watheeq AI Service — LLM Integration Service (Google Gemini SDK)

Handles all communication with the Gemini API using the official google-genai SDK.
Implements retry logic with exponential backoff and automatic model fallback
for resilience (NFR-08: 99% API success rate).

Key design decisions:
  - Uses google-genai SDK for direct Gemini API access (no proxy)
  - Gemini 2.5 Flash as primary model, with automatic fallback chain
  - Structured JSON output via response_mime_type for reliable parsing
  - Low temperature (0.1) for consistent, deterministic analysis
  - Configurable model and parameters via environment variables
"""

import json
import logging
import asyncio
from typing import Optional

from google import genai
from google.genai import types

from app.config import settings
from app.utils.exceptions import LLMServiceError, LLMResponseParsingError

logger = logging.getLogger(__name__)

# Initialize the Gemini client (lazy)
_client: Optional[genai.Client] = None

# Fallback model chain: if the primary model is overloaded (503),
# try lighter alternatives automatically.
FALLBACK_MODELS = ["gemini-2.5-flash", "gemini-2.5-flash-lite", "gemini-2.0-flash-lite"]


def _get_client() -> genai.Client:
    """Get or create the Gemini client (lazy initialization)."""
    global _client
    if _client is None:
        _client = genai.Client(api_key=settings.GEMINI_API_KEY)
    return _client


def _strip_code_fences(text: str) -> str:
    """Strip markdown code fences (```json ... ```) from LLM output."""
    cleaned = text.strip()
    if cleaned.startswith("```"):
        try:
            first_newline = cleaned.index("\n")
            cleaned = cleaned[first_newline + 1:]
        except ValueError:
            cleaned = cleaned[3:]
    if cleaned.endswith("```"):
        cleaned = cleaned[:-3].rstrip()
    return cleaned


def _get_model_chain() -> list:
    """Return the ordered list of models to try: primary + fallbacks."""
    chain = [settings.LLM_MODEL]
    for fb in FALLBACK_MODELS:
        if fb != settings.LLM_MODEL:
            chain.append(fb)
    return chain


def _call_gemini_json(system_prompt: str, user_prompt: str, model: str = None) -> str:
    """Synchronous Gemini API call expecting JSON output."""
    client = _get_client()
    use_model = model or settings.LLM_MODEL
    response = client.models.generate_content(
        model=use_model,
        contents=user_prompt,
        config=types.GenerateContentConfig(
            system_instruction=system_prompt,
            temperature=settings.LLM_TEMPERATURE,
            max_output_tokens=settings.LLM_MAX_TOKENS,
            response_mime_type="application/json",
        ),
    )
    return response.text


def _call_gemini_text(system_prompt: str, user_prompt: str, model: str = None) -> str:
    """Synchronous Gemini API call expecting plain text output."""
    client = _get_client()
    use_model = model or settings.LLM_MODEL
    response = client.models.generate_content(
        model=use_model,
        contents=user_prompt,
        config=types.GenerateContentConfig(
            system_instruction=system_prompt,
            temperature=0.3,
            max_output_tokens=settings.LLM_MAX_TOKENS,
        ),
    )
    return response.text


def _is_overloaded_error(error: Exception) -> bool:
    """Check if the error indicates the model is overloaded (503/429)."""
    error_str = str(error).lower()
    return any(
        keyword in error_str
        for keyword in [
            "503", "unavailable", "overloaded",
            "high demand", "resource_exhausted", "429",
        ]
    )


def _is_transient_error(error: Exception) -> bool:
    """Check if the error is transient and worth retrying."""
    error_str = str(error).lower()
    return any(
        keyword in error_str
        for keyword in [
            "timeout", "rate", "503", "500",
            "overloaded", "unavailable", "resource_exhausted",
            "deadline", "429",
        ]
    )


async def analyze(
    user_prompt: str,
    system_prompt: str,
    max_retries: int = 3,
) -> dict:
    """
    Send a prompt to Gemini and return the parsed JSON response.

    Implements exponential backoff retry logic with automatic model fallback.
    If the primary model (gemini-3.1-flash-lite-preview) is overloaded, automatically
    falls back to lighter models (gemini-2.5-flash, gemini-2.5-flash-lite, etc.).

    Args:
        user_prompt: The user message containing claim and policy data.
        system_prompt: The system message defining the AI's role and output format.
        max_retries: Maximum number of retry attempts per model.

    Returns:
        Parsed JSON dictionary from the LLM response.

    Raises:
        LLMServiceError: If the API call fails after all retries and fallbacks.
        LLMResponseParsingError: If the response cannot be parsed as JSON.
    """
    model_chain = _get_model_chain()
    last_error = None

    for model in model_chain:
        for attempt in range(1, max_retries + 1):
            try:
                logger.info(
                    f"Gemini API call attempt {attempt}/{max_retries} "
                    f"(model: {model})"
                )

                content = await asyncio.to_thread(
                    _call_gemini_json, system_prompt, user_prompt, model
                )

                if not content:
                    raise LLMResponseParsingError("Gemini returned empty response")

                cleaned = _strip_code_fences(content)

                try:
                    parsed = json.loads(cleaned)
                except json.JSONDecodeError as e:
                    raise LLMResponseParsingError(
                        f"Gemini response is not valid JSON: {str(e)}\n"
                        f"Raw response: {content[:500]}"
                    )

                logger.info(f"Gemini API call successful (model: {model})")
                return parsed

            except LLMResponseParsingError:
                raise

            except Exception as e:
                last_error = e

                # If model is overloaded, skip to next model immediately
                if _is_overloaded_error(e):
                    logger.warning(
                        f"Model {model} is overloaded. "
                        f"{'Trying fallback model...' if model != model_chain[-1] else 'No more fallbacks.'}"
                    )
                    break  # Break inner retry loop, try next model

                if _is_transient_error(e) and attempt < max_retries:
                    wait_time = 2 ** attempt
                    logger.warning(
                        f"Gemini API transient error (attempt {attempt}/{max_retries}): "
                        f"{e}. Retrying in {wait_time}s..."
                    )
                    await asyncio.sleep(wait_time)
                else:
                    logger.error(f"Gemini API error on model {model}: {e}")
                    break  # Break inner retry loop, try next model

    raise LLMServiceError(
        f"Gemini API call failed after trying all models "
        f"{[m for m in model_chain]}: {str(last_error)}"
    )


async def generate_text(
    user_prompt: str,
    system_prompt: str,
    max_retries: int = 3,
) -> str:
    """
    Send a prompt to Gemini and return the raw text response (not JSON).

    Used for draft response generation where free-form text is expected.
    Implements the same model fallback chain as analyze().

    Args:
        user_prompt: The user message.
        system_prompt: The system message.
        max_retries: Maximum number of retry attempts per model.

    Returns:
        Raw text string from the Gemini response.

    Raises:
        LLMServiceError: If the API call fails after all retries and fallbacks.
    """
    model_chain = _get_model_chain()
    last_error = None

    for model in model_chain:
        for attempt in range(1, max_retries + 1):
            try:
                logger.info(
                    f"Gemini text generation attempt {attempt}/{max_retries} "
                    f"(model: {model})"
                )

                content = await asyncio.to_thread(
                    _call_gemini_text, system_prompt, user_prompt, model
                )

                if not content:
                    raise LLMServiceError("Gemini returned empty text response")

                logger.info(f"Gemini text generation successful (model: {model})")
                return content.strip()

            except Exception as e:
                last_error = e

                if _is_overloaded_error(e):
                    logger.warning(
                        f"Model {model} is overloaded. "
                        f"{'Trying fallback model...' if model != model_chain[-1] else 'No more fallbacks.'}"
                    )
                    break

                if _is_transient_error(e) and attempt < max_retries:
                    wait_time = 2 ** attempt
                    logger.warning(
                        f"Gemini API transient error (attempt {attempt}/{max_retries}): "
                        f"{e}. Retrying in {wait_time}s..."
                    )
                    await asyncio.sleep(wait_time)
                else:
                    logger.error(f"Gemini API error on model {model}: {e}")
                    break

    raise LLMServiceError(
        f"Gemini text generation failed after trying all models "
        f"{[m for m in model_chain]}: {str(last_error)}"
    )

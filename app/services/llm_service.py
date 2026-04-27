"""
Watheeq AI Service — LLM Integration Service (Gemini 2.5 Flash via OpenAI SDK)

Handles all communication with the LLM API.
Uses the OpenAI-compatible SDK to call Gemini 2.5 Flash model.
Implements retry logic with exponential backoff for NFR-08 (99% API success rate).

Key design decisions:
  - Uses openai SDK for API compatibility and reliability
  - Gemini 2.5 Flash model via OpenAI-compatible endpoint
  - Structured JSON output via response_format for reliable parsing
  - Low temperature (0.1) for consistent, deterministic analysis
  - Configurable model and parameters via environment variables
"""

import json
import logging
import asyncio
from typing import Optional

from openai import OpenAI

from app.config import settings
from app.utils.exceptions import LLMServiceError, LLMResponseParsingError

logger = logging.getLogger(__name__)

# Initialize the OpenAI client (lazy)
_client: Optional[OpenAI] = None


def _get_client() -> OpenAI:
    """Get or create the OpenAI client (lazy initialization)."""
    global _client
    if _client is None:
        _client = OpenAI()  # Uses OPENAI_API_KEY and base_url from env
    return _client


def _call_llm_json(system_prompt: str, user_prompt: str) -> str:
    """Synchronous LLM call expecting JSON output."""
    client = _get_client()
    response = client.chat.completions.create(
        model=settings.LLM_MODEL,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        temperature=settings.LLM_TEMPERATURE,
        max_tokens=settings.LLM_MAX_TOKENS,
        response_format={"type": "json_object"},
    )
    return response.choices[0].message.content


def _call_llm_text(system_prompt: str, user_prompt: str) -> str:
    """Synchronous LLM call expecting plain text output."""
    client = _get_client()
    response = client.chat.completions.create(
        model=settings.LLM_MODEL,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        temperature=0.3,  # Slightly higher for more natural language
        max_tokens=settings.LLM_MAX_TOKENS,
    )
    return response.choices[0].message.content


async def analyze(
    user_prompt: str,
    system_prompt: str,
    max_retries: int = 3,
) -> dict:
    """
    Send a prompt to the LLM and return the parsed JSON response.

    Implements exponential backoff retry logic for resilience (NFR-08).

    Args:
        user_prompt: The user message containing claim and policy data.
        system_prompt: The system message defining the AI's role and output format.
        max_retries: Maximum number of retry attempts on transient failures.

    Returns:
        Parsed JSON dictionary from the LLM response.

    Raises:
        LLMServiceError: If the API call fails after all retries.
        LLMResponseParsingError: If the response cannot be parsed as JSON.
    """
    last_error = None

    for attempt in range(1, max_retries + 1):
        try:
            logger.info(
                f"LLM API call attempt {attempt}/{max_retries} "
                f"(model: {settings.LLM_MODEL})"
            )

            # Run synchronous SDK call in a thread pool to avoid blocking
            content = await asyncio.to_thread(
                _call_llm_json, system_prompt, user_prompt
            )

            if not content:
                raise LLMResponseParsingError("LLM returned empty response")

            # Strip markdown code fences if present (```json ... ```)
            cleaned = content.strip()
            if cleaned.startswith("```"):
                # Remove opening fence (```json or ```)
                first_newline = cleaned.index("\n")
                cleaned = cleaned[first_newline + 1:]
            if cleaned.endswith("```"):
                cleaned = cleaned[:-3].rstrip()

            # Parse JSON from the response
            try:
                parsed = json.loads(cleaned)
            except json.JSONDecodeError as e:
                raise LLMResponseParsingError(
                    f"LLM response is not valid JSON: {str(e)}\n"
                    f"Raw response: {content[:500]}"
                )

            logger.info("LLM API call successful")
            return parsed

        except LLMResponseParsingError:
            raise

        except Exception as e:
            last_error = e
            error_str = str(e).lower()

            # Check for transient/retryable errors
            is_transient = any(
                keyword in error_str
                for keyword in [
                    "timeout", "rate", "503", "500",
                    "overloaded", "unavailable", "resource_exhausted",
                ]
            )

            if is_transient and attempt < max_retries:
                wait_time = 2 ** attempt  # 2, 4, 8 seconds
                logger.warning(
                    f"LLM API transient error (attempt {attempt}/{max_retries}): "
                    f"{e}. Retrying in {wait_time}s..."
                )
                await asyncio.sleep(wait_time)
            else:
                logger.error(f"LLM API error: {e}")
                break

    raise LLMServiceError(
        f"LLM API call failed after {max_retries} attempts: {str(last_error)}"
    )


async def generate_text(
    user_prompt: str,
    system_prompt: str,
    max_retries: int = 3,
) -> str:
    """
    Send a prompt to the LLM and return the raw text response (not JSON).

    Used for draft response generation where free-form text is expected.

    Args:
        user_prompt: The user message.
        system_prompt: The system message.
        max_retries: Maximum number of retry attempts.

    Returns:
        Raw text string from the LLM response.

    Raises:
        LLMServiceError: If the API call fails after all retries.
    """
    last_error = None

    for attempt in range(1, max_retries + 1):
        try:
            logger.info(
                f"LLM text generation attempt {attempt}/{max_retries} "
                f"(model: {settings.LLM_MODEL})"
            )

            content = await asyncio.to_thread(
                _call_llm_text, system_prompt, user_prompt
            )

            if not content:
                raise LLMServiceError("LLM returned empty text response")

            logger.info("LLM text generation successful")
            return content.strip()

        except Exception as e:
            last_error = e
            error_str = str(e).lower()

            is_transient = any(
                keyword in error_str
                for keyword in [
                    "timeout", "rate", "503", "500",
                    "overloaded", "unavailable", "resource_exhausted",
                ]
            )

            if is_transient and attempt < max_retries:
                wait_time = 2 ** attempt
                logger.warning(
                    f"LLM API transient error (attempt {attempt}/{max_retries}): "
                    f"{e}. Retrying in {wait_time}s..."
                )
                await asyncio.sleep(wait_time)
            else:
                logger.error(f"LLM API error: {e}")
                break

    raise LLMServiceError(
        f"LLM text generation failed after {max_retries} attempts: "
        f"{str(last_error)}"
    )

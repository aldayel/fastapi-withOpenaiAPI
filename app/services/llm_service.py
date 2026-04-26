"""
Watheeq AI Service — LLM Integration Service

Handles all communication with the OpenAI API (or compatible LLM providers).
Implements retry logic with exponential backoff for NFR-08 (99% API success rate).

Key design decisions:
  - Uses AsyncOpenAI for non-blocking API calls
  - Structured JSON output via response_format for reliable parsing
  - Low temperature (0.1) for consistent, deterministic analysis
  - Configurable model and parameters via environment variables
"""

import json
import logging
import asyncio
from typing import Optional

from openai import AsyncOpenAI, APIError, APITimeoutError, RateLimitError

from app.config import settings
from app.utils.exceptions import LLMServiceError, LLMResponseParsingError

logger = logging.getLogger(__name__)

# Initialize the async OpenAI client
_client: Optional[AsyncOpenAI] = None


def _get_client() -> AsyncOpenAI:
    """Get or create the AsyncOpenAI client (lazy initialization)."""
    global _client
    if _client is None:
        _client = AsyncOpenAI(api_key=settings.OPENAI_API_KEY)
    return _client


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
    client = _get_client()
    last_error = None

    for attempt in range(1, max_retries + 1):
        try:
            logger.info(
                f"LLM API call attempt {attempt}/{max_retries} "
                f"(model: {settings.LLM_MODEL})"
            )

            response = await client.chat.completions.create(
                model=settings.LLM_MODEL,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                response_format={"type": "json_object"},
                temperature=settings.LLM_TEMPERATURE,
                max_tokens=settings.LLM_MAX_TOKENS,
            )

            # Extract and parse the response content
            content = response.choices[0].message.content
            if not content:
                raise LLMResponseParsingError("LLM returned empty response")

            try:
                parsed = json.loads(content)
            except json.JSONDecodeError as e:
                raise LLMResponseParsingError(
                    f"LLM response is not valid JSON: {str(e)}"
                )

            logger.info("LLM API call successful")
            return parsed

        except (APITimeoutError, RateLimitError) as e:
            # Transient errors — retry with exponential backoff
            last_error = e
            wait_time = 2 ** attempt  # 2, 4, 8 seconds
            logger.warning(
                f"LLM API transient error (attempt {attempt}/{max_retries}): {e}. "
                f"Retrying in {wait_time}s..."
            )
            if attempt < max_retries:
                await asyncio.sleep(wait_time)

        except APIError as e:
            # Non-transient API errors
            last_error = e
            logger.error(f"LLM API error: {e}")
            if attempt < max_retries and e.status_code and e.status_code >= 500:
                # Server errors may be transient — retry
                wait_time = 2 ** attempt
                await asyncio.sleep(wait_time)
            else:
                break

        except LLMResponseParsingError:
            raise

        except Exception as e:
            last_error = e
            logger.error(f"Unexpected LLM error: {e}")
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
    client = _get_client()
    last_error = None

    for attempt in range(1, max_retries + 1):
        try:
            logger.info(
                f"LLM text generation attempt {attempt}/{max_retries} "
                f"(model: {settings.LLM_MODEL})"
            )

            response = await client.chat.completions.create(
                model=settings.LLM_MODEL,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                temperature=0.3,  # Slightly higher for more natural language
                max_tokens=settings.LLM_MAX_TOKENS,
            )

            content = response.choices[0].message.content
            if not content:
                raise LLMServiceError("LLM returned empty text response")

            logger.info("LLM text generation successful")
            return content.strip()

        except (APITimeoutError, RateLimitError) as e:
            last_error = e
            wait_time = 2 ** attempt
            logger.warning(
                f"LLM API transient error (attempt {attempt}/{max_retries}): {e}. "
                f"Retrying in {wait_time}s..."
            )
            if attempt < max_retries:
                await asyncio.sleep(wait_time)

        except APIError as e:
            last_error = e
            logger.error(f"LLM API error: {e}")
            if attempt < max_retries and e.status_code and e.status_code >= 500:
                wait_time = 2 ** attempt
                await asyncio.sleep(wait_time)
            else:
                break

        except Exception as e:
            last_error = e
            logger.error(f"Unexpected LLM error: {e}")
            break

    raise LLMServiceError(
        f"LLM text generation failed after {max_retries} attempts: {str(last_error)}"
    )

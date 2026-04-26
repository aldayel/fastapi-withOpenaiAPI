"""
Watheeq AI Service — PDF Extraction Service

Handles downloading and extracting text from PDF documents.
Supports multiple input sources:
  - HTTP/HTTPS URLs (Firebase Storage download URLs)
  - Base64-encoded PDF strings
  - Local file paths (for testing)

Uses PyMuPDF (fitz) for fast, reliable text extraction from text-based PDFs.

NFR-03: PDF processing under 10 seconds for files up to 20MB.
"""

import base64
import logging
from io import BytesIO

import fitz  # PyMuPDF
import httpx

from app.config import settings
from app.utils.exceptions import PDFDownloadError, PDFExtractionError

logger = logging.getLogger(__name__)


async def extract_text(source: str) -> str:
    """
    Extract text from a PDF source.

    Args:
        source: One of:
            - HTTP/HTTPS URL to a PDF file
            - Base64-encoded PDF string (optionally with data URI prefix)
            - Local file path (for testing)

    Returns:
        Extracted text content from all pages of the PDF.

    Raises:
        PDFExtractionError: If text extraction fails.
        PDFDownloadError: If the PDF cannot be downloaded from a URL.
    """
    try:
        pdf_bytes = await _resolve_source(source)
        text = _extract_text_from_bytes(pdf_bytes)

        if not text.strip():
            logger.warning(
                "PDF extraction returned empty text. "
                "The PDF may be image-based (scanned). "
                "Consider using OCR for scanned documents."
            )

        return text

    except (PDFDownloadError, PDFExtractionError):
        raise
    except Exception as e:
        logger.error(f"Unexpected error during PDF extraction: {e}")
        raise PDFExtractionError(f"Failed to extract text from PDF: {str(e)}")


async def _resolve_source(source: str) -> bytes:
    """Resolve the PDF source to raw bytes."""
    if source.startswith(("http://", "https://")):
        return await _download_pdf(source)
    elif source.startswith("data:"):
        # Data URI format: data:application/pdf;base64,<encoded_data>
        try:
            encoded = source.split(",", 1)[-1]
            return base64.b64decode(encoded)
        except Exception as e:
            raise PDFExtractionError(f"Invalid base64 data URI: {str(e)}")
    elif len(source) > 500:
        # Assume raw base64 string if very long
        try:
            return base64.b64decode(source)
        except Exception as e:
            raise PDFExtractionError(f"Invalid base64 string: {str(e)}")
    else:
        # Local file path (for testing)
        try:
            with open(source, "rb") as f:
                return f.read()
        except FileNotFoundError:
            raise PDFExtractionError(f"PDF file not found: {source}")
        except Exception as e:
            raise PDFExtractionError(f"Failed to read PDF file: {str(e)}")


async def _download_pdf(url: str) -> bytes:
    """
    Download a PDF from a URL with timeout and size validation.

    NFR-03: Must handle files up to MAX_PDF_SIZE_MB within 10 seconds.
    """
    max_size_bytes = settings.MAX_PDF_SIZE_MB * 1024 * 1024

    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.get(url)
            response.raise_for_status()

            content = response.content
            if len(content) > max_size_bytes:
                raise PDFDownloadError(
                    url,
                    f"PDF exceeds maximum size of {settings.MAX_PDF_SIZE_MB}MB",
                )

            return content

    except httpx.TimeoutException:
        raise PDFDownloadError(url, "Download timed out")
    except httpx.HTTPStatusError as e:
        raise PDFDownloadError(url, f"HTTP {e.response.status_code}")
    except PDFDownloadError:
        raise
    except Exception as e:
        raise PDFDownloadError(url, str(e))


def _extract_text_from_bytes(pdf_bytes: bytes) -> str:
    """
    Extract text from PDF bytes using PyMuPDF.

    Processes all pages and joins text with double newlines.
    """
    try:
        doc = fitz.open(stream=pdf_bytes, filetype="pdf")
        text_parts = []

        for page_num, page in enumerate(doc):
            page_text = page.get_text()
            if page_text.strip():
                text_parts.append(f"--- Page {page_num + 1} ---\n{page_text}")

        doc.close()

        return "\n\n".join(text_parts)

    except Exception as e:
        raise PDFExtractionError(f"PyMuPDF extraction failed: {str(e)}")

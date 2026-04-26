"""
Watheeq AI Service — Custom Exception Classes

Centralized exception definitions for consistent error handling across the service.
"""

from fastapi import HTTPException, status


class PDFExtractionError(Exception):
    """Raised when PDF text extraction fails."""

    def __init__(self, message: str = "Failed to extract text from PDF"):
        self.message = message
        super().__init__(self.message)


class LLMServiceError(Exception):
    """Raised when the LLM API call fails."""

    def __init__(self, message: str = "LLM service encountered an error"):
        self.message = message
        super().__init__(self.message)


class LLMResponseParsingError(Exception):
    """Raised when the LLM response cannot be parsed into the expected format."""

    def __init__(self, message: str = "Failed to parse LLM response"):
        self.message = message
        super().__init__(self.message)


class AnalysisNotFoundError(Exception):
    """Raised when an analysis record is not found for the given claim."""

    def __init__(self, claim_id: str):
        self.message = f"No analysis found for claim: {claim_id}"
        super().__init__(self.message)


class DraftNotFoundError(Exception):
    """Raised when a draft response is not found for the given claim."""

    def __init__(self, claim_id: str):
        self.message = f"No draft response found for claim: {claim_id}"
        super().__init__(self.message)


class PDFDownloadError(Exception):
    """Raised when a PDF cannot be downloaded from the provided URL."""

    def __init__(self, url: str, reason: str = ""):
        self.message = f"Failed to download PDF from {url}"
        if reason:
            self.message += f": {reason}"
        super().__init__(self.message)


class AnalysisAlreadyExistsError(Exception):
    """Raised when an analysis has already been triggered for a claim."""

    def __init__(self, claim_id: str):
        self.message = f"Analysis already exists for claim: {claim_id}"
        super().__init__(self.message)


# --- HTTP Exception Helpers ---

def not_found_exception(detail: str) -> HTTPException:
    """Return a 404 Not Found HTTPException."""
    return HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=detail)


def bad_request_exception(detail: str) -> HTTPException:
    """Return a 400 Bad Request HTTPException."""
    return HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=detail)


def service_unavailable_exception(detail: str) -> HTTPException:
    """Return a 503 Service Unavailable HTTPException."""
    return HTTPException(
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=detail
    )

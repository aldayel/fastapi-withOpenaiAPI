"""
Watheeq AI Service — Shared Dependencies

FastAPI dependency injection functions used across routers.
Includes Bearer token authentication for role-based access control (NFR-05).
"""

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.config import settings

# Bearer token security scheme
security = HTTPBearer(auto_error=False)


async def verify_bearer_token(
    credentials: HTTPAuthorizationCredentials = Depends(security),
) -> str:
    """
    Validate the Bearer token from the Authorization header.

    In production, this would verify a Firebase ID token or JWT.
    For the MVP, it checks against a configured secret token.

    Returns the token string if valid.
    Raises 401 Unauthorized if the token is missing or invalid.
    """
    # If no BEARER_TOKEN is configured, skip authentication (development mode)
    if not settings.BEARER_TOKEN:
        return "dev-mode-no-auth"

    if credentials is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing authentication credentials",
            headers={"WWW-Authenticate": "Bearer"},
        )

    if credentials.credentials != settings.BEARER_TOKEN:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid authentication credentials",
            headers={"WWW-Authenticate": "Bearer"},
        )

    return credentials.credentials

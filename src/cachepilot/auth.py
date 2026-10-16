"""API-key authentication for gateway routes."""

import hashlib
import hmac
import os

from fastapi import HTTPException, Security, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

_bearer = HTTPBearer(auto_error=False)


def require_api_key(
    credentials: HTTPAuthorizationCredentials | None = Security(_bearer),
) -> str:
    """Validate a bearer key and return its SHA-256 tenant identifier."""
    expected_key = os.getenv("CACHEPILOT_API_KEY")
    if not expected_key:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="API key authentication is not configured",
        )

    if credentials is None or not hmac.compare_digest(
        credentials.credentials, expected_key
    ):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or missing API key",
            headers={"WWW-Authenticate": "Bearer"},
        )

    return hashlib.sha256(credentials.credentials.encode("utf-8")).hexdigest()

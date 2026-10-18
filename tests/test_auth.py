"""Authentication edge-case tests."""

import pytest
from fastapi import HTTPException
from fastapi.security import HTTPAuthorizationCredentials

from cachepilot.auth import require_api_key


def test_non_ascii_bearer_token_is_rejected_with_401(monkeypatch) -> None:
    monkeypatch.setenv("CACHEPILOT_API_KEY", "expected-ascii-key")
    credentials = HTTPAuthorizationCredentials(
        scheme="Bearer", credentials="café"
    )

    with pytest.raises(HTTPException) as error:
        require_api_key(credentials)

    assert error.value.status_code == 401

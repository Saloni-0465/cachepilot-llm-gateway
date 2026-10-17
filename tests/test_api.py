"""HTTP-level tests for CachePilot's gateway behavior."""

from sqlalchemy.exc import SQLAlchemyError


def _headers(key: str = "test-gateway-key") -> dict[str, str]:
    return {"Authorization": f"Bearer {key}"}


def _payload(message: str = "Hello, CachePilot") -> dict[str, object]:
    return {
        "model": "mock-model",
        "messages": [{"role": "user", "content": message}],
    }


def test_health_is_public(gateway: dict[str, object]) -> None:
    response = gateway["client"].get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_chat_completion_rejects_missing_or_invalid_api_key(
    gateway: dict[str, object],
) -> None:
    client = gateway["client"]

    missing = client.post("/v1/chat/completions", json=_payload())
    invalid = client.post(
        "/v1/chat/completions", headers=_headers("wrong-key"), json=_payload()
    )

    assert missing.status_code == 401
    assert invalid.status_code == 401
    assert invalid.headers["www-authenticate"] == "Bearer"


def test_identical_request_misses_then_hits_cache(gateway: dict[str, object]) -> None:
    client = gateway["client"]

    first = client.post(
        "/v1/chat/completions", headers=_headers(), json=_payload()
    )
    second = client.post(
        "/v1/chat/completions", headers=_headers(), json=_payload()
    )

    assert first.status_code == second.status_code == 200
    assert first.headers["x-cache"] == "MISS"
    assert second.headers["x-cache"] == "HIT"
    assert first.json()["choices"] == second.json()["choices"]
    assert first.json()["id"] != second.json()["id"]
    assert len(gateway["recorded"]) == 2


def test_rate_limit_returns_429_after_configured_limit(
    gateway: dict[str, object], monkeypatch
) -> None:
    monkeypatch.setenv("RATE_LIMIT_REQUESTS", "1")
    client = gateway["client"]

    allowed = client.post(
        "/v1/chat/completions", headers=_headers(), json=_payload()
    )
    rejected = client.post(
        "/v1/chat/completions", headers=_headers(), json=_payload("different")
    )

    assert allowed.status_code == 200
    assert allowed.headers["x-ratelimit-status"] == "ACTIVE"
    assert rejected.status_code == 429
    assert rejected.headers["ratelimit-remaining"] == "0"
    assert int(rejected.headers["retry-after"]) > 0


def test_redis_outage_fails_open_and_is_reported(gateway: dict[str, object]) -> None:
    gateway["cache"].unavailable = True
    gateway["limiter"].unavailable = True

    response = gateway["client"].post(
        "/v1/chat/completions", headers=_headers(), json=_payload()
    )

    assert response.status_code == 200
    assert response.headers["x-cache"] == "UNAVAILABLE"
    assert response.headers["x-ratelimit-status"] == "UNAVAILABLE"


def test_database_outage_does_not_discard_completion(gateway: dict[str, object], monkeypatch) -> None:
    from cachepilot import main

    def unavailable_log(**_row: object) -> None:
        raise SQLAlchemyError("test database unavailable")

    monkeypatch.setattr(main, "record_request", unavailable_log)
    response = gateway["client"].post(
        "/v1/chat/completions", headers=_headers(), json=_payload()
    )

    assert response.status_code == 200
    assert response.headers["x-usage-log"] == "UNAVAILABLE"
    assert response.json()["choices"][0]["message"]["content"] == (
        "Mock response: Hello, CachePilot"
    )

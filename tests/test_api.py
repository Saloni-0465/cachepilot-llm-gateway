"""HTTP-level tests for CachePilot's gateway behavior."""

import hashlib

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
    assert len(gateway["recorded"]) == 2
    assert gateway["recorded"][1]["http_status"] == 429


def test_provider_failure_is_logged_with_502(gateway: dict[str, object], monkeypatch) -> None:
    from cachepilot import main
    from cachepilot.providers.base import ProviderError

    class FailingProvider:
        name = "mock"

        def complete(self, _request):
            raise ProviderError("simulated provider failure")

    monkeypatch.setattr(main, "active_provider", FailingProvider())
    response = gateway["client"].post(
        "/v1/chat/completions", headers=_headers(), json=_payload()
    )

    assert response.status_code == 502
    assert len(gateway["recorded"]) == 1
    assert gateway["recorded"][0]["http_status"] == 502


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


def test_dashboard_page_is_public_and_contains_key_input(
    gateway: dict[str, object],
) -> None:
    response = gateway["client"].get("/dashboard")

    assert response.status_code == 200
    assert "text/html" in response.headers["content-type"]
    assert "CachePilot API key" in response.text


def test_analytics_summary_requires_authentication(gateway: dict[str, object]) -> None:
    response = gateway["client"].get("/v1/analytics/summary")

    assert response.status_code == 401


def test_analytics_summary_is_scoped_to_authenticated_key(
    gateway: dict[str, object], monkeypatch
) -> None:
    from cachepilot import main

    calls: list[str] = []

    def summarize(tenant_scope: str) -> dict[str, object]:
        calls.append(tenant_scope)
        return {
            "total_requests": 3,
            "failed_requests": 0,
            "cache_hits": 1,
            "cache_hit_rate_percent": 33.33,
            "average_latency_ms": 4.5,
            "estimated_cost_usd": 0.0,
            "estimated_cost_saved_usd": 0.0,
            "providers": [{"name": "mock", "requests": 3}],
        }

    monkeypatch.setattr(main, "get_analytics_summary", summarize)
    response = gateway["client"].get(
        "/v1/analytics/summary", headers=_headers()
    )

    expected_scope = hashlib.sha256(b"test-gateway-key").hexdigest()
    assert response.status_code == 200
    assert response.json()["total_requests"] == 3
    assert calls == [expected_scope]


def test_analytics_database_failure_returns_service_unavailable(
    gateway: dict[str, object], monkeypatch
) -> None:
    from cachepilot import main

    def unavailable(_tenant_scope: str) -> dict[str, object]:
        raise SQLAlchemyError("test database unavailable")

    monkeypatch.setattr(main, "get_analytics_summary", unavailable)
    response = gateway["client"].get(
        "/v1/analytics/summary", headers=_headers()
    )

    assert response.status_code == 503
    assert response.json()["detail"] == "Usage analytics are temporarily unavailable"

"""Shared fixtures for isolated API tests."""

from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient

from cachepilot import main
from cachepilot import rate_limit


class MemoryCache:
    def __init__(self) -> None:
        self.values: dict[str, str] = {}
        self.unavailable = False

    @staticmethod
    def _key(tenant: str, provider: str, request: object) -> str:
        return f"{tenant}:{provider}:{request.model_dump_json()}"

    def get(self, tenant: str, provider: str, request: object) -> str | None:
        if self.unavailable:
            from redis.exceptions import ConnectionError

            raise ConnectionError("test Redis unavailable")
        return self.values.get(self._key(tenant, provider, request))

    def set(
        self, tenant: str, provider: str, request: object, response_json: str
    ) -> None:
        if self.unavailable:
            from redis.exceptions import ConnectionError

            raise ConnectionError("test Redis unavailable")
        self.values[self._key(tenant, provider, request)] = response_json


class MemoryRateLimiter:
    def __init__(self) -> None:
        self.counts: dict[str, int] = {}
        self.unavailable = False

    def eval(self, _script: str, _key_count: int, key: str, _window: int) -> list[int]:
        if self.unavailable:
            from redis.exceptions import ConnectionError

            raise ConnectionError("test Redis unavailable")
        count = self.counts.get(key, 0) + 1
        self.counts[key] = count
        return [count, 60]


@pytest.fixture
def gateway(monkeypatch: pytest.MonkeyPatch) -> Iterator[dict[str, object]]:
    """Run the API with isolated cache, limiter, and request-log storage."""
    monkeypatch.setenv("CACHEPILOT_API_KEY", "test-gateway-key")
    monkeypatch.setenv("RATE_LIMIT_REQUESTS", "60")
    monkeypatch.setenv("RATE_LIMIT_WINDOW_SECONDS", "60")

    cache = MemoryCache()
    limiter = MemoryRateLimiter()
    recorded: list[dict[str, object]] = []
    monkeypatch.setattr(main, "exact_cache", cache)
    monkeypatch.setattr(rate_limit, "_redis", limiter)
    monkeypatch.setattr(main, "record_request", lambda **row: recorded.append(row))
    monkeypatch.setattr(main, "initialize_database", lambda: None)

    with TestClient(main.app) as client:
        yield {"client": client, "cache": cache, "limiter": limiter, "recorded": recorded}

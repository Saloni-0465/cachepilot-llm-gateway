"""Unit tests for exact cache key isolation."""

from cachepilot.cache.exact import ExactResponseCache
from cachepilot.schemas import ChatCompletionRequest


def _request(temperature: float = 0) -> ChatCompletionRequest:
    return ChatCompletionRequest(
        model="mock-model",
        messages=[{"role": "user", "content": "hello"}],
        temperature=temperature,
    )


def test_cache_key_is_scoped_to_tenant() -> None:
    assert ExactResponseCache.make_key("tenant-a", "mock", _request()) != (
        ExactResponseCache.make_key("tenant-b", "mock", _request())
    )


def test_cache_key_is_scoped_to_provider() -> None:
    assert ExactResponseCache.make_key("tenant", "mock", _request()) != (
        ExactResponseCache.make_key("tenant", "openai", _request())
    )


def test_cache_key_includes_generation_settings() -> None:
    assert ExactResponseCache.make_key("tenant", "mock", _request(0)) != (
        ExactResponseCache.make_key("tenant", "mock", _request(1))
    )

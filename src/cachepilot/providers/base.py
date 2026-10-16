"""Shared provider contract and provider-facing errors."""

from typing import Protocol

from cachepilot.schemas import ChatCompletionRequest, ChatCompletionResponse


class ProviderError(Exception):
    """Raised when a configured LLM provider cannot complete a request."""


class LLMProvider(Protocol):
    name: str

    def complete(self, request: ChatCompletionRequest) -> ChatCompletionResponse: ...

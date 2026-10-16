"""Deterministic mock provider for local development without API costs."""

from math import ceil
from time import time
from uuid import uuid4

from cachepilot.schemas import (
    AssistantMessage,
    ChatCompletionChoice,
    ChatCompletionRequest,
    ChatCompletionResponse,
    TokenUsage,
)


def _estimate_tokens(text: str) -> int:
    """Rough character-based estimate for mock responses, not billing data."""
    return ceil(len(text) / 4)


class MockProvider:
    name = "mock"

    def complete(self, request: ChatCompletionRequest) -> ChatCompletionResponse:
        last_user_message = next(
            (message.content for message in reversed(request.messages) if message.role == "user"),
            "",
        )
        answer = (
            f"Mock response: {last_user_message}"
            if last_user_message
            else "Mock provider received the conversation."
        )
        prompt_text = " ".join(message.content for message in request.messages)
        prompt_tokens = _estimate_tokens(prompt_text)
        completion_tokens = _estimate_tokens(answer)

        return ChatCompletionResponse(
            id=f"chatcmpl-{uuid4().hex}",
            created=int(time()),
            model=request.model,
            choices=[
                ChatCompletionChoice(message=AssistantMessage(content=answer))
            ],
            usage=TokenUsage(
                prompt_tokens=prompt_tokens,
                completion_tokens=completion_tokens,
                total_tokens=prompt_tokens + completion_tokens,
            ),
        )

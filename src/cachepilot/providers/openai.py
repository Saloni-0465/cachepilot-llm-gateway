"""OpenAI Chat Completions adapter."""

import os
from time import time
from uuid import uuid4

from openai import APIError, OpenAI

from cachepilot.providers.base import ProviderError
from cachepilot.schemas import (
    AssistantMessage,
    ChatCompletionChoice,
    ChatCompletionRequest,
    ChatCompletionResponse,
    TokenUsage,
)


class OpenAIProvider:
    name = "openai"

    def __init__(self) -> None:
        api_key = os.getenv("OPENAI_API_KEY")
        if not api_key:
            raise RuntimeError(
                "Set OPENAI_API_KEY before starting with LLM_PROVIDER=openai"
            )
        self._client = OpenAI(
            api_key=api_key,
            timeout=float(os.getenv("OPENAI_TIMEOUT_SECONDS", "30")),
        )

    def complete(self, request: ChatCompletionRequest) -> ChatCompletionResponse:
        params = {
            "model": request.model,
            "messages": [message.model_dump() for message in request.messages],
        }
        if request.temperature is not None:
            params["temperature"] = request.temperature

        try:
            result = self._client.chat.completions.create(**params)
        except APIError as exc:
            raise ProviderError("OpenAI request failed") from exc

        choice = result.choices[0]
        usage = result.usage
        prompt_tokens = usage.prompt_tokens if usage else 0
        completion_tokens = usage.completion_tokens if usage else 0
        return ChatCompletionResponse(
            id=f"chatcmpl-{uuid4().hex}",
            created=int(time()),
            model=result.model,
            choices=[
                ChatCompletionChoice(
                    message=AssistantMessage(content=choice.message.content or ""),
                    finish_reason=choice.finish_reason or "stop",
                )
            ],
            usage=TokenUsage(
                prompt_tokens=prompt_tokens,
                completion_tokens=completion_tokens,
                total_tokens=prompt_tokens + completion_tokens,
            ),
        )

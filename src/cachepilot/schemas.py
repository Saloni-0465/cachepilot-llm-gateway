"""Request and response models for the chat completions API."""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class ChatMessage(BaseModel):
    role: Literal["system", "developer", "user", "assistant"]
    content: str


class ChatCompletionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    model: str = Field(min_length=1)
    messages: list[ChatMessage] = Field(min_length=1)
    temperature: float | None = Field(default=None, ge=0, le=2)


class AssistantMessage(BaseModel):
    role: Literal["assistant"] = "assistant"
    content: str


class ChatCompletionChoice(BaseModel):
    index: int = 0
    message: AssistantMessage
    finish_reason: str | None = "stop"


class TokenUsage(BaseModel):
    prompt_tokens: int
    completion_tokens: int
    total_tokens: int


class ChatCompletionResponse(BaseModel):
    id: str
    object: Literal["chat.completion"] = "chat.completion"
    created: int
    model: str
    choices: list[ChatCompletionChoice]
    usage: TokenUsage


class ProviderUsage(BaseModel):
    name: str
    requests: int


class AnalyticsSummary(BaseModel):
    total_requests: int
    failed_requests: int = 0
    cache_hits: int
    cache_hit_rate_percent: float
    average_latency_ms: float | None
    estimated_cost_usd: float | None
    estimated_cost_saved_usd: float | None
    providers: list[ProviderUsage]

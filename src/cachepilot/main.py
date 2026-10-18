"""CachePilot API application."""

import logging
import os
from contextlib import asynccontextmanager
from decimal import Decimal
from time import perf_counter, time
from uuid import uuid4

from fastapi import APIRouter, Depends, FastAPI, HTTPException, Response, status
from fastapi.responses import HTMLResponse
from redis.exceptions import RedisError
from sqlalchemy.exc import SQLAlchemyError

from cachepilot.auth import require_api_key
from cachepilot.cache.exact import ExactResponseCache
from cachepilot.db import get_analytics_summary, initialize_database, record_request
from cachepilot.dashboard import dashboard_page
from cachepilot.pricing import estimate_cost_usd
from cachepilot.providers.base import LLMProvider, ProviderError
from cachepilot.providers.mock import MockProvider
from cachepilot.providers.openai import OpenAIProvider
from cachepilot.rate_limit import enforce_rate_limit
from cachepilot.schemas import AnalyticsSummary, ChatCompletionRequest, ChatCompletionResponse

logger = logging.getLogger("cachepilot")


def create_provider() -> LLMProvider:
    provider_name = os.getenv("LLM_PROVIDER", "mock").lower()
    if provider_name == "mock":
        return MockProvider()
    if provider_name == "openai":
        return OpenAIProvider()
    raise RuntimeError("LLM_PROVIDER must be 'mock' or 'openai'")


@asynccontextmanager
async def lifespan(_: FastAPI):
    initialize_database()
    yield


app = FastAPI(
    lifespan=lifespan,
    title="CachePilot",
    description="An LLM gateway with exact and semantic caching.",
    version="0.1.0",
)
active_provider = create_provider()
exact_cache = ExactResponseCache.from_url(
    os.getenv("REDIS_URL", "redis://localhost:6379/0"),
    ttl_seconds=int(os.getenv("CACHE_TTL_SECONDS", "300")),
)


@app.get("/health", tags=["health"])
def health() -> dict[str, str]:
    """Report that the API process is responding."""
    return {"status": "ok"}


@app.get("/dashboard", response_class=HTMLResponse, include_in_schema=False)
def dashboard() -> HTMLResponse:
    """Serve the local dashboard shell; its data endpoint requires a bearer key."""
    return dashboard_page()


protected = APIRouter(prefix="/v1", dependencies=[Depends(require_api_key)])


@protected.get("/status", tags=["gateway"])
def gateway_status() -> dict[str, str]:
    """Temporary protected route for checking API-key authentication."""
    return {"status": "authenticated"}


@protected.get(
    "/analytics/summary",
    response_model=AnalyticsSummary,
    tags=["analytics"],
)
def analytics_summary(
    tenant_scope: str = Depends(require_api_key),
) -> dict[str, object]:
    """Return persisted aggregate usage for the authenticated tenant."""
    try:
        return get_analytics_summary(tenant_scope)
    except SQLAlchemyError as exc:
        logger.exception("Failed to load gateway analytics")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Usage analytics are temporarily unavailable",
        ) from exc


@protected.post(
    "/chat/completions",
    response_model=ChatCompletionResponse,
    tags=["gateway"],
    dependencies=[Depends(enforce_rate_limit)],
)
def create_chat_completion(
    request: ChatCompletionRequest,
    response: Response,
    tenant_scope: str = Depends(require_api_key),
) -> ChatCompletionResponse:
    """Return an OpenAI-shaped completion with exact caching and usage logging."""
    started_at = perf_counter()
    cache_available = True
    try:
        cached_json = exact_cache.get(tenant_scope, active_provider.name, request)
    except RedisError:
        cached_json = None
        cache_available = False

    cache_status = "hit" if cached_json is not None else (
        "miss" if cache_available else "unavailable"
    )
    if cached_json is not None:
        cached_completion = ChatCompletionResponse.model_validate_json(cached_json)
        completion = cached_completion.model_copy(
            update={"id": f"chatcmpl-{uuid4().hex}", "created": int(time())}
        )
        response.headers["X-Cache"] = "HIT"
        response.headers["X-Provider"] = "cache"
        provider_used = "cache"
        estimated_cost_usd = Decimal("0")
        estimated_cost_saved_usd = estimate_cost_usd(
            active_provider.name, request.model, completion.usage
        )
    else:
        try:
            completion = active_provider.complete(request)
        except ProviderError as exc:
            logger.exception("Configured provider failed")
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail="The configured LLM provider could not complete the request",
            ) from exc

        response.headers["X-Provider"] = active_provider.name
        provider_used = active_provider.name
        estimated_cost_usd = estimate_cost_usd(
            active_provider.name, request.model, completion.usage
        )
        estimated_cost_saved_usd = Decimal("0")

        if cache_available:
            try:
                exact_cache.set(
                    tenant_scope,
                    active_provider.name,
                    request,
                    completion.model_dump_json(),
                )
            except RedisError:
                cache_available = False
                cache_status = "unavailable"

        response.headers["X-Cache"] = "MISS" if cache_available else "UNAVAILABLE"

    latency_ms = (perf_counter() - started_at) * 1000
    response.headers["X-Usage-Log"] = "RECORDED"
    try:
        record_request(
            request_id=completion.id,
            tenant_key_hash=tenant_scope,
            model=request.model,
            provider_used=provider_used,
            cache_status=cache_status,
            prompt_tokens=completion.usage.prompt_tokens,
            completion_tokens=completion.usage.completion_tokens,
            total_tokens=completion.usage.total_tokens,
            latency_ms=latency_ms,
            estimated_cost_usd=estimated_cost_usd,
            estimated_cost_saved_usd=estimated_cost_saved_usd,
        )
    except SQLAlchemyError:
        logger.exception("Failed to persist request usage for %s", completion.id)
        response.headers["X-Usage-Log"] = "UNAVAILABLE"

    return completion


app.include_router(protected)

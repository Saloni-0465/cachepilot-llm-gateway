"""Redis-backed, tenant-scoped request rate limiting."""

import os

from fastapi import Depends, HTTPException, Response, status
from redis import Redis
from redis.exceptions import RedisError

from cachepilot.auth import require_api_key

_INCREMENT_WINDOW = """
local count = redis.call('INCR', KEYS[1])
if count == 1 then
    redis.call('EXPIRE', KEYS[1], ARGV[1])
end
return {count, redis.call('TTL', KEYS[1])}
"""


def _make_client() -> Redis:
    return Redis.from_url(
        os.getenv("REDIS_URL", "redis://localhost:6379/0"),
        decode_responses=True,
        socket_connect_timeout=0.25,
        socket_timeout=0.25,
    )


_redis = _make_client()


def enforce_rate_limit(
    response: Response,
    tenant_scope: str = Depends(require_api_key),
) -> None:
    """Allow a fixed number of requests per tenant per time window.

    The limit is a fixed window shared by all gateway workers through Redis.
    Redis failures fail open and are exposed through a response header.
    """
    limit = int(os.getenv("RATE_LIMIT_REQUESTS", "60"))
    window = int(os.getenv("RATE_LIMIT_WINDOW_SECONDS", "60"))
    if limit <= 0 or window <= 0:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Rate limit configuration must use positive values",
        )

    key = f"cachepilot:rate:v1:{tenant_scope}"
    try:
        count, ttl = _redis.eval(_INCREMENT_WINDOW, 1, key, window)
    except RedisError:
        response.headers["X-RateLimit-Status"] = "UNAVAILABLE"
        return

    remaining = max(0, limit - int(count))
    response.headers["RateLimit-Limit"] = str(limit)
    response.headers["RateLimit-Remaining"] = str(remaining)
    response.headers["RateLimit-Reset"] = str(max(0, int(ttl)))
    response.headers["X-RateLimit-Status"] = "ACTIVE"

    if int(count) > limit:
        retry_after = max(1, int(ttl))
        response.headers["Retry-After"] = str(retry_after)
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Request rate limit exceeded; retry after the current window",
            headers={
                "Retry-After": str(retry_after),
                "RateLimit-Limit": str(limit),
                "RateLimit-Remaining": "0",
                "RateLimit-Reset": str(retry_after),
            },
        )

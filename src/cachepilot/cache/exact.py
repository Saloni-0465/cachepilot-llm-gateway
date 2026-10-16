"""Redis-backed exact-response cache."""

import hashlib
import json

from redis import Redis

from cachepilot.schemas import ChatCompletionRequest


class ExactResponseCache:
    """Store completed responses under a tenant-scoped request hash."""

    def __init__(self, redis_client: Redis, ttl_seconds: int = 300) -> None:
        if ttl_seconds <= 0:
            raise ValueError("ttl_seconds must be positive")
        self._redis = redis_client
        self._ttl_seconds = ttl_seconds

    @classmethod
    def from_url(cls, redis_url: str, ttl_seconds: int = 300) -> "ExactResponseCache":
        client = Redis.from_url(
            redis_url,
            decode_responses=True,
            socket_connect_timeout=0.25,
            socket_timeout=0.25,
        )
        return cls(client, ttl_seconds=ttl_seconds)

    @staticmethod
    def make_key(
        tenant_scope: str, provider_name: str, request: ChatCompletionRequest
    ) -> str:
        request_json = json.dumps(
            request.model_dump(mode="json"),
            sort_keys=True,
            separators=(",", ":"),
        )
        request_hash = hashlib.sha256(request_json.encode("utf-8")).hexdigest()
        return f"cachepilot:exact:v3:{tenant_scope}:{provider_name}:{request_hash}"

    def get(
        self, tenant_scope: str, provider_name: str, request: ChatCompletionRequest
    ) -> str | None:
        return self._redis.get(self.make_key(tenant_scope, provider_name, request))

    def set(
        self,
        tenant_scope: str,
        provider_name: str,
        request: ChatCompletionRequest,
        response_json: str,
    ) -> None:
        self._redis.set(
            self.make_key(tenant_scope, provider_name, request),
            response_json,
            ex=self._ttl_seconds,
        )

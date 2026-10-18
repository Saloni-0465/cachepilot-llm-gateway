"""Database aggregation tests for the tenant-scoped dashboard summary."""

from datetime import datetime, timezone
from decimal import Decimal

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from cachepilot import db


@pytest.fixture
def analytics_session(monkeypatch: pytest.MonkeyPatch):
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    db.Base.metadata.create_all(engine)
    test_sessions = sessionmaker(bind=engine, expire_on_commit=False)
    monkeypatch.setattr(db, "SessionLocal", test_sessions)
    yield test_sessions
    engine.dispose()


def _row(
    *,
    request_id: str,
    tenant: str,
    provider: str,
    cache_status: str,
    latency_ms: float,
    cost: Decimal | None,
    saved: Decimal | None,
) -> db.RequestLog:
    return db.RequestLog(
        request_id=request_id,
        tenant_key_hash=tenant,
        model="test-model",
        provider_used=provider,
        cache_status=cache_status,
        prompt_tokens=5,
        completion_tokens=3,
        total_tokens=8,
        latency_ms=latency_ms,
        estimated_cost_usd=cost,
        estimated_cost_saved_usd=saved,
        http_status=200,
        created_at=datetime.now(timezone.utc),
    )


def test_summary_aggregates_only_the_requested_tenant(analytics_session) -> None:
    with analytics_session.begin() as session:
        session.add_all(
            [
                _row(
                    request_id="a-1",
                    tenant="tenant-a",
                    provider="mock",
                    cache_status="miss",
                    latency_ms=10,
                    cost=Decimal("0"),
                    saved=Decimal("0"),
                ),
                _row(
                    request_id="a-2",
                    tenant="tenant-a",
                    provider="cache",
                    cache_status="hit",
                    latency_ms=2,
                    cost=Decimal("0"),
                    saved=Decimal("0"),
                ),
                _row(
                    request_id="b-1",
                    tenant="tenant-b",
                    provider="openai",
                    cache_status="miss",
                    latency_ms=100,
                    cost=Decimal("4"),
                    saved=Decimal("0"),
                ),
            ]
        )

    summary = db.get_analytics_summary("tenant-a")

    assert summary == {
        "total_requests": 2,
        "failed_requests": 0,
        "cache_hits": 1,
        "cache_hit_rate_percent": 50.0,
        "average_latency_ms": 6.0,
        "estimated_cost_usd": 0.0,
        "estimated_cost_saved_usd": 0.0,
        "providers": [
            {"name": "cache", "requests": 1},
            {"name": "mock", "requests": 1},
        ],
    }


def test_summary_marks_cost_unknown_when_any_request_lacks_pricing(
    analytics_session,
) -> None:
    with analytics_session.begin() as session:
        session.add_all(
            [
                _row(
                    request_id="known",
                    tenant="tenant-a",
                    provider="mock",
                    cache_status="miss",
                    latency_ms=10,
                    cost=Decimal("0"),
                    saved=Decimal("0"),
                ),
                _row(
                    request_id="unknown",
                    tenant="tenant-a",
                    provider="openai",
                    cache_status="miss",
                    latency_ms=20,
                    cost=None,
                    saved=None,
                ),
            ]
        )

    summary = db.get_analytics_summary("tenant-a")

    assert summary["estimated_cost_usd"] is None
    assert summary["estimated_cost_saved_usd"] is None


def test_summary_counts_failed_http_requests(analytics_session) -> None:
    with analytics_session.begin() as session:
        failed = _row(
            request_id="failed-1",
            tenant="tenant-a",
            provider="openai",
            cache_status="miss",
            latency_ms=12,
            cost=None,
            saved=None,
        )
        failed.http_status = 502
        session.add(failed)

    summary = db.get_analytics_summary("tenant-a")

    assert summary["total_requests"] == 1
    assert summary["failed_requests"] == 1


def test_summary_for_tenant_without_requests_is_empty(analytics_session) -> None:
    summary = db.get_analytics_summary("no-requests")

    assert summary == {
        "total_requests": 0,
        "failed_requests": 0,
        "cache_hits": 0,
        "cache_hit_rate_percent": 0.0,
        "average_latency_ms": None,
        "estimated_cost_usd": None,
        "estimated_cost_saved_usd": None,
        "providers": [],
    }

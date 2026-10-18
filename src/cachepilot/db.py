"""PostgreSQL persistence for CachePilot request usage."""

import os
from datetime import datetime
from decimal import Decimal

from sqlalchemy import DateTime, Float, Integer, Numeric, String, case, create_engine, func, select, text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, sessionmaker

DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "postgresql+psycopg://cachepilot:cachepilot_local_dev@localhost:5432/cachepilot",
)

engine = create_engine(DATABASE_URL, pool_pre_ping=True)
SessionLocal = sessionmaker(bind=engine, expire_on_commit=False)


class Base(DeclarativeBase):
    pass


class RequestLog(Base):
    """Operational metadata for one completed chat request; no prompt text."""

    __tablename__ = "request_logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    request_id: Mapped[str] = mapped_column(String(80), index=True)
    tenant_key_hash: Mapped[str] = mapped_column(String(64), index=True)
    model: Mapped[str] = mapped_column(String(120))
    provider_used: Mapped[str] = mapped_column(String(40))
    cache_status: Mapped[str] = mapped_column(String(20))
    prompt_tokens: Mapped[int] = mapped_column(Integer)
    completion_tokens: Mapped[int] = mapped_column(Integer)
    total_tokens: Mapped[int] = mapped_column(Integer)
    latency_ms: Mapped[float] = mapped_column(Float)
    estimated_cost_usd: Mapped[Decimal | None] = mapped_column(Numeric(12, 8), nullable=True)
    estimated_cost_saved_usd: Mapped[Decimal | None] = mapped_column(Numeric(12, 8), nullable=True)
    http_status: Mapped[int] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


def initialize_database() -> None:
    """Create the initial schema for local development."""
    Base.metadata.create_all(engine)
    # Keep existing local databases compatible as cost estimates become optional.
    with engine.begin() as connection:
        connection.execute(
            text("ALTER TABLE request_logs ALTER COLUMN estimated_cost_usd DROP NOT NULL")
        )
        connection.execute(
            text("ALTER TABLE request_logs ALTER COLUMN estimated_cost_saved_usd DROP NOT NULL")
        )


def record_request(
    *,
    request_id: str,
    tenant_key_hash: str,
    model: str,
    provider_used: str,
    cache_status: str,
    prompt_tokens: int,
    completion_tokens: int,
    total_tokens: int,
    latency_ms: float,
    estimated_cost_usd: Decimal | None,
    estimated_cost_saved_usd: Decimal | None,
    http_status: int = 200,
) -> None:
    """Persist metadata for a completed request in one transaction."""
    with SessionLocal.begin() as session:
        session.add(
            RequestLog(
                request_id=request_id,
                tenant_key_hash=tenant_key_hash,
                model=model,
                provider_used=provider_used,
                cache_status=cache_status,
                prompt_tokens=prompt_tokens,
                completion_tokens=completion_tokens,
                total_tokens=total_tokens,
                latency_ms=latency_ms,
                estimated_cost_usd=estimated_cost_usd,
                estimated_cost_saved_usd=estimated_cost_saved_usd,
                http_status=http_status,
            )
        )


def get_analytics_summary(tenant_key_hash: str) -> dict[str, object]:
    """Summarize persisted request metadata for one authenticated tenant."""
    with SessionLocal() as session:
        totals = session.execute(
            select(
                func.count(RequestLog.id),
                func.coalesce(
                    func.sum(case((RequestLog.cache_status == "hit", 1), else_=0)), 0
                ),
                func.avg(RequestLog.latency_ms),
                func.sum(RequestLog.estimated_cost_usd),
                func.count(RequestLog.estimated_cost_usd),
                func.sum(RequestLog.estimated_cost_saved_usd),
                func.count(RequestLog.estimated_cost_saved_usd),
                func.sum(case((RequestLog.http_status >= 400, 1), else_=0)),
            ).where(RequestLog.tenant_key_hash == tenant_key_hash)
        ).one()
        provider_rows = session.execute(
            select(RequestLog.provider_used, func.count(RequestLog.id))
            .where(RequestLog.tenant_key_hash == tenant_key_hash)
            .group_by(RequestLog.provider_used)
            .order_by(RequestLog.provider_used)
        ).all()

    total_requests = int(totals[0])
    cache_hits = int(totals[1])
    average_latency = totals[2]
    estimated_cost = totals[3]
    known_cost_rows = int(totals[4])
    estimated_savings = totals[5]
    known_savings_rows = int(totals[6])
    failed_requests = int(totals[7] or 0)
    return {
        "total_requests": total_requests,
        "failed_requests": failed_requests,
        "cache_hits": cache_hits,
        "cache_hit_rate_percent": (
            round(cache_hits / total_requests * 100, 2) if total_requests else 0.0
        ),
        "average_latency_ms": (
            round(float(average_latency), 2) if average_latency is not None else None
        ),
        "estimated_cost_usd": (
            float(estimated_cost)
            if total_requests and known_cost_rows == total_requests
            else None
        ),
        "estimated_cost_saved_usd": (
            float(estimated_savings)
            if total_requests and known_savings_rows == total_requests
            else None
        ),
        "providers": [
            {"name": provider, "requests": int(count)}
            for provider, count in provider_rows
        ],
    }

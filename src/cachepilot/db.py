"""PostgreSQL persistence for CachePilot request usage."""

import os
from datetime import datetime
from decimal import Decimal

from sqlalchemy import DateTime, Float, Integer, Numeric, String, create_engine, func, text
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

"""News engine table. One row per unique item; point-in-time column `usable_from` gates every consumer."""

from datetime import datetime
from typing import Any

from sqlalchemy import BigInteger, DateTime, Float, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base


class NewsItem(Base):
    __tablename__ = "news_items"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    uid: Mapped[str] = mapped_column(String(32), unique=True)  # content hash (dedup key)
    source: Mapped[str] = mapped_column(String(32), index=True)
    scope: Mapped[str] = mapped_column(String(16))  # company | market | regulatory
    title: Mapped[str] = mapped_column(Text)
    body: Mapped[str] = mapped_column(Text)
    url: Mapped[str] = mapped_column(Text)
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    ingested_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    usable_from: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), index=True
    )  # max(published, ingested)
    timestamp_status: Mapped[str] = mapped_column(String(16))  # ok | missing | future_rejected
    instrument_keys: Mapped[list[str]] = mapped_column(JSONB, default=list)
    symbols: Mapped[list[str]] = mapped_column(JSONB, default=list)
    direct_issuer: Mapped[bool] = mapped_column(default=False)
    event_type: Mapped[str] = mapped_column(String(32), index=True)
    importance: Mapped[float] = mapped_column(Float)
    sentiment_label: Mapped[str | None] = mapped_column(String(16))
    sentiment_score: Mapped[float | None] = mapped_column(Float)
    sentiment_probs: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    sentiment_model: Mapped[str | None] = mapped_column(String(64))
    duplicate_of: Mapped[int | None] = mapped_column(BigInteger)

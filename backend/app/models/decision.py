from datetime import datetime
from typing import Any

from sqlalchemy import DateTime, Float, Integer, String, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base


class DecisionRecord(Base):
    """Every decision, including NO_TRADE, with its full explanation."""

    __tablename__ = "decisions"

    decision_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    instrument_key: Mapped[str] = mapped_column(String(64), index=True)
    symbol: Mapped[str] = mapped_column(String(64))
    pipeline: Mapped[str] = mapped_column(String(16))
    action: Mapped[str] = mapped_column(String(10), index=True)
    confidence: Mapped[float] = mapped_column(Float)
    score: Mapped[float | None] = mapped_column(Float)
    quantity: Mapped[int] = mapped_column(Integer)
    model_version: Mapped[str | None] = mapped_column(String(64))
    explanation: Mapped[dict[str, Any]] = mapped_column(JSONB)
    decided_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

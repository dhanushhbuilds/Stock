"""Data-engine tables: instruments, universe, broker tokens, download checkpoints, file catalogue."""

from datetime import date, datetime
from typing import Any

from sqlalchemy import (
    BigInteger,
    Boolean,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base


class Instrument(Base):
    """Rows copied verbatim from the Upstox instrument master. Never hand-written."""

    __tablename__ = "instruments"

    instrument_key: Mapped[str] = mapped_column(String(64), primary_key=True)
    segment: Mapped[str] = mapped_column(String(16), index=True)
    exchange: Mapped[str] = mapped_column(String(8))
    trading_symbol: Mapped[str] = mapped_column(String(64), index=True)
    name: Mapped[str] = mapped_column(String(128))
    isin: Mapped[str | None] = mapped_column(String(12), index=True)
    instrument_type: Mapped[str] = mapped_column(String(16))
    lot_size: Mapped[int | None] = mapped_column(Integer)
    tick_size_paise: Mapped[float | None] = mapped_column(Float)  # Upstox reports tick size in paise
    exchange_token: Mapped[str | None] = mapped_column(String(32))
    master_fetched_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class UniverseMember(Base):
    """Index constituents as published on a given date (point-in-time snapshot)."""

    __tablename__ = "universe_members"
    __table_args__ = (UniqueConstraint("universe", "as_of", "symbol"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    universe: Mapped[str] = mapped_column(String(32), index=True)
    as_of: Mapped[date] = mapped_column(Date)
    symbol: Mapped[str] = mapped_column(String(64))
    company_name: Mapped[str] = mapped_column(String(128))
    industry: Mapped[str] = mapped_column(String(64))
    isin: Mapped[str] = mapped_column(String(12))
    instrument_key: Mapped[str] = mapped_column(ForeignKey("instruments.instrument_key"))
    sector_index_key: Mapped[str | None] = mapped_column(ForeignKey("instruments.instrument_key"))


class BrokerToken(Base):
    __tablename__ = "broker_tokens"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    broker: Mapped[str] = mapped_column(String(16), index=True)
    broker_user_id: Mapped[str | None] = mapped_column(String(64))
    token_encrypted: Mapped[str] = mapped_column(Text)  # Fernet ciphertext; plaintext never stored
    issued_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    revoked: Mapped[bool] = mapped_column(Boolean, default=False)


class DownloadChunk(Base):
    """Checkpoint for one historical API request. Lets a download resume exactly where it stopped."""

    __tablename__ = "download_chunks"
    __table_args__ = (UniqueConstraint("instrument_key", "unit", "interval", "from_date", "to_date"),)

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    instrument_key: Mapped[str] = mapped_column(String(64), index=True)
    unit: Mapped[str] = mapped_column(String(8))
    interval: Mapped[int] = mapped_column(Integer)
    from_date: Mapped[date] = mapped_column(Date)
    to_date: Mapped[date] = mapped_column(Date)
    status: Mapped[str] = mapped_column(String(12), index=True)  # pending | done | empty | failed
    rows: Mapped[int] = mapped_column(Integer, default=0)
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    last_error: Mapped[str | None] = mapped_column(Text)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class CandleFile(Base):
    """Catalogue of Parquet files in the data lake, with checksums for dataset versioning."""

    __tablename__ = "candle_files"

    path: Mapped[str] = mapped_column(String(256), primary_key=True)  # relative to data_dir
    instrument_key: Mapped[str] = mapped_column(String(64), index=True)
    timeframe: Mapped[str] = mapped_column(String(12), index=True)  # 1minute | 5minute | 1day
    year: Mapped[int] = mapped_column(Integer)
    rows: Mapped[int] = mapped_column(Integer)
    first_ts: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    last_ts: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    sha256: Mapped[str] = mapped_column(String(64))
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class DataQualityReport(Base):
    __tablename__ = "data_quality_reports"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    instrument_key: Mapped[str] = mapped_column(String(64), index=True)
    timeframe: Mapped[str] = mapped_column(String(12))
    generated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    passed: Mapped[bool] = mapped_column(Boolean)
    summary: Mapped[dict[str, Any]] = mapped_column(JSONB)

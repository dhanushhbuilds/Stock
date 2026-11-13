"""ML engine tables: datasets, experiments (one per model per run) and the model registry."""

from datetime import datetime
from typing import Any

from sqlalchemy import BigInteger, Boolean, DateTime, Float, Integer, String, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base


class MLDataset(Base):
    __tablename__ = "ml_datasets"

    version: Mapped[str] = mapped_column(String(24), primary_key=True)  # content hash
    pipeline: Mapped[str] = mapped_column(String(16), index=True)  # swing | intraday
    path: Mapped[str] = mapped_column(String(256))
    rows: Mapped[int] = mapped_column(Integer)
    symbols: Mapped[int] = mapped_column(Integer)
    first_date: Mapped[datetime] = mapped_column(DateTime(timezone=False))
    last_date: Mapped[datetime] = mapped_column(DateTime(timezone=False))
    config: Mapped[dict[str, Any]] = mapped_column(JSONB)
    features: Mapped[list[str]] = mapped_column(JSONB)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class MLExperiment(Base):
    __tablename__ = "ml_experiments"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    run_id: Mapped[str] = mapped_column(String(32), index=True)
    pipeline: Mapped[str] = mapped_column(String(16), index=True)
    model_name: Mapped[str] = mapped_column(String(32))
    dataset_version: Mapped[str] = mapped_column(String(24))
    model_config: Mapped[dict[str, Any]] = mapped_column(JSONB)
    periods: Mapped[dict[str, Any]] = mapped_column(JSONB)  # folds + holdout dates
    walk_forward_metrics: Mapped[dict[str, Any]] = mapped_column(JSONB)
    holdout_metrics: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    train_seconds: Mapped[float] = mapped_column(Float)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class MLModel(Base):
    __tablename__ = "ml_models"

    version: Mapped[str] = mapped_column(String(48), primary_key=True)
    pipeline: Mapped[str] = mapped_column(String(16), index=True)
    model_name: Mapped[str] = mapped_column(String(32))
    run_id: Mapped[str] = mapped_column(String(32))
    dataset_version: Mapped[str] = mapped_column(String(24))
    artifact_path: Mapped[str] = mapped_column(String(256))
    artifact_sha256: Mapped[str] = mapped_column(String(64))
    features: Mapped[list[str]] = mapped_column(JSONB)
    metrics: Mapped[dict[str, Any]] = mapped_column(JSONB)
    promoted: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    promotion_reasons: Mapped[list[str]] = mapped_column(JSONB)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

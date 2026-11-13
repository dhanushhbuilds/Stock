"""Inference with the promoted model. Uses exactly the same dataset builders as training (parity)."""

import hashlib
import time
from datetime import UTC, datetime
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.engines.ml.sequence import SequenceModel
from app.models.ml import MLModel


class ModelUnavailable(Exception):
    pass


def promoted(session: Session, pipeline: str) -> MLModel:
    m = session.scalars(
        select(MLModel)
        .where(MLModel.pipeline == pipeline, MLModel.promoted.is_(True))
        .order_by(MLModel.created_at.desc())
    ).first()
    if m is None:
        raise ModelUnavailable(f"no promoted {pipeline} model (none passed the promotion gate)")
    return m


def load_artifact(m: MLModel) -> dict:
    path = Path(m.artifact_path)
    if not path.exists():
        raise ModelUnavailable(f"artifact missing: {path}")
    if hashlib.sha256(path.read_bytes()).hexdigest() != m.artifact_sha256:
        raise ModelUnavailable("artifact checksum mismatch (tampered or replaced)")
    return joblib.load(path)


def predict_latest(ds: pd.DataFrame, art: dict, time_col: str) -> pd.DataFrame:
    """Probabilities for the most recent timestamp in ds (one row per symbol). Returns empty if none."""
    model, feats = art["model"], art["features"]
    if isinstance(model, SequenceModel):
        ds = ds.sort_values(["symbol", time_col], kind="stable").reset_index(drop=True)
        rows = np.flatnonzero((ds[time_col] == ds[time_col].max()).to_numpy())
        p = model.predict_proba_frame(ds[feats], ds["symbol"], rows)
        out = ds.iloc[rows]
    else:
        out = ds[ds[time_col] == ds[time_col].max()]
        p = model.predict_proba(out[feats])
    out = out[["symbol", "instrument_key", time_col, "close"]].copy()
    out[["p_down", "p_neutral", "p_up"]] = p
    return out.reset_index(drop=True)


def latency_ms(fn, *a, repeat: int = 20) -> dict:
    xs = []
    for _ in range(repeat):
        t = time.perf_counter()
        fn(*a)
        xs.append((time.perf_counter() - t) * 1000)
    xs.sort()
    return {
        "p50_ms": xs[len(xs) // 2],
        "p95_ms": xs[int(len(xs) * 0.95) - 1],
        "n": repeat,
        "measured_at": datetime.now(UTC).isoformat(),
    }

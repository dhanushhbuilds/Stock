"""ML registry and strategy-report read API (Engines 2 and 4)."""

import json
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.config import REPO_DIR
from app.core.db import get_session
from app.engines.strategy.strategies import STRATEGIES
from app.models.ml import MLDataset, MLExperiment, MLModel

router = APIRouter(tags=["ml", "strategies"])
SessionDep = Annotated[Session, Depends(get_session)]


@router.get("/ml/models")
def models(session: SessionDep, pipeline: Literal["swing", "intraday"] | None = None):
    stmt = select(MLModel).order_by(MLModel.created_at.desc())
    if pipeline:
        stmt = stmt.where(MLModel.pipeline == pipeline)
    return [{"version": m.version, "pipeline": m.pipeline, "model": m.model_name, "promoted": m.promoted,
             "promotion_reasons": m.promotion_reasons, "dataset_version": m.dataset_version, "metrics": m.metrics,
             "artifact_sha256": m.artifact_sha256, "created_at": m.created_at} for m in session.scalars(stmt)]


@router.get("/ml/runs")
def runs(session: SessionDep):
    """One row per training run (latest first) with the models compared in it."""
    rows = session.execute(
        select(MLExperiment.run_id, MLExperiment.pipeline, MLExperiment.dataset_version,
               func.min(MLExperiment.created_at), func.array_agg(MLExperiment.model_name))
        .group_by(MLExperiment.run_id, MLExperiment.pipeline, MLExperiment.dataset_version)
        .order_by(func.min(MLExperiment.created_at).desc())
    ).all()
    return [{"run_id": r[0], "pipeline": r[1], "dataset_version": r[2], "created_at": r[3], "models": r[4]}
            for r in rows]


@router.get("/ml/experiments/{run_id}")
def experiments(run_id: str, session: SessionDep):
    rows = session.scalars(select(MLExperiment).where(MLExperiment.run_id == run_id)).all()
    if not rows:
        raise HTTPException(404, "unknown run")
    return [{"model": r.model_name, "dataset_version": r.dataset_version, "config": r.model_config,
             "periods": r.periods, "walk_forward": {k: v for k, v in r.walk_forward_metrics.items() if k != "folds"},
             "folds": r.walk_forward_metrics.get("folds"), "holdout": r.holdout_metrics,
             "train_seconds": r.train_seconds} for r in rows]


@router.get("/ml/datasets")
def datasets(session: SessionDep):
    return [{"version": d.version, "pipeline": d.pipeline, "rows": d.rows, "symbols": d.symbols,
             "first_date": d.first_date, "last_date": d.last_date, "config": d.config, "n_features": len(d.features)}
            for d in session.scalars(select(MLDataset).order_by(MLDataset.created_at.desc()))]


@router.get("/strategies")
def strategies():
    return [{"name": s.name, "timeframe": s.timeframe, "description": s.description, "max_hold": s.max_hold}
            for s in STRATEGIES.values()]


@router.get("/strategies/report")
def strategy_report():
    files = sorted((REPO_DIR / "reports" / "strategies").glob("strategies_*.json"))
    if not files:
        raise HTTPException(404, "no strategy report yet: run python -m app.engines.strategy.runner")
    return {"file": files[-1].name, **json.loads(files[-1].read_text())}

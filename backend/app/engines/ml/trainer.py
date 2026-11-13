"""Experiment runner: identical walk-forward protocol for every model, then a locked holdout.

Selection uses walk-forward results ONLY. The holdout is evaluated afterwards and reported as-is.
"""

import hashlib
import json
import time
import uuid
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
from sqlalchemy.orm import Session

from app.core.logging import get_logger
from app.engines.ml import evaluate as ev
from app.engines.ml.models import TABULAR
from app.engines.ml.sequence import SequenceModel
from app.engines.ml.splits import Fold, masks
from app.models.ml import MLDataset, MLExperiment, MLModel

log = get_logger(__name__)


@dataclass
class PipelineSpec:
    name: str  # swing | intraday
    horizon: int  # purge length in "dates" units (sessions for swing; sessions for intraday too, see below)
    cost: float
    backtest: Callable[[pd.DataFrame, np.ndarray, float], dict]  # (test_df, proba, threshold_or_none) -> dict
    seq_features: list[str] = field(default_factory=list)
    seq_len: int = 20
    model_overrides: dict = field(default_factory=dict)  # per-model constructor params (e.g. compute caps)


def dataset_version(ds: pd.DataFrame, config: dict) -> str:
    h = hashlib.sha256()
    h.update(json.dumps(config, sort_keys=True, default=str).encode())
    h.update(pd.util.hash_pandas_object(ds, index=False).values.tobytes())
    return h.hexdigest()[:16]


def save_dataset(
    session: Session, ds: pd.DataFrame, pipeline: str, config: dict, features: list[str], data_dir: Path
) -> str:
    ver = dataset_version(ds, config)
    path = data_dir / "datasets" / pipeline / f"{ver}.parquet"
    if not path.exists():
        path.parent.mkdir(parents=True, exist_ok=True)
        ds.to_parquet(path, index=False, compression="zstd")
    if session.get(MLDataset, ver) is None:
        session.add(
            MLDataset(
                version=ver,
                pipeline=pipeline,
                path=str(path.relative_to(data_dir)),
                rows=len(ds),
                symbols=int(ds["symbol"].nunique()),
                first_date=ds["date"].min().to_pydatetime(),
                last_date=ds["date"].max().to_pydatetime(),
                config=config,
                features=features,
            )
        )
        session.commit()
    return ver


def _make(name: str, spec: PipelineSpec):
    kw = spec.model_overrides.get(name, {})
    if name in TABULAR:
        return TABULAR[name](**kw)
    return SequenceModel(kind=name, seq_len=spec.seq_len, **kw)


def _fit_predict(name, spec, ds, feats, fit, val, test):
    """Returns (model, val_proba, test_proba)."""
    m = _make(name, spec)
    y = ds["y"]
    if isinstance(m, SequenceModel):
        rows = np.arange(len(ds))
        fit_r = rows[fit.to_numpy() & y.notna().to_numpy()]
        val_r = rows[val.to_numpy() & y.notna().to_numpy()]
        test_r = rows[test.to_numpy()]
        X = ds[spec.seq_features]
        m.fit_frame(X, y.fillna(1).astype(int), ds["symbol"], fit_r, val_r)
        return m, m.predict_proba_frame(X, ds["symbol"], val_r), m.predict_proba_frame(X, ds["symbol"], test_r)
    f, v = fit & y.notna(), val & y.notna()
    m.fit(ds.loc[f, feats], y[f].astype(int), ds.loc[v, feats], y[v].astype(int))
    return m, m.predict_proba(ds.loc[v, feats]), m.predict_proba(ds.loc[test, feats])


def run(
    session: Session,
    ds: pd.DataFrame,
    feats: list[str],
    spec: PipelineSpec,
    folds: list[Fold],
    holdout: Fold,
    model_names: list[str],
    dataset_ver: str,
    artifacts_dir: Path,
    threshold_fn: Callable[[np.ndarray], float] | None = None,
    run_id: str | None = None,
    finalize_run: bool = True,
) -> dict:
    """Evaluate models (walk-forward + holdout) and store one MLExperiment per model under run_id.

    Native-library constraint (macOS): after XGBoost/LightGBM have run, torch can deadlock in the same process
    (observed 2026-11-13). Tree/linear models and LSTM/GRU are therefore evaluated in SEPARATE processes that
    share a run_id (finalize_run=False for all but the last), then `finalize()` selects across ALL stored
    experiments of the run. Every model sees identical folds, data and metrics.
    """
    run_id = run_id or time.strftime("%Y%m%d-%H%M%S-") + uuid.uuid4().hex[:6]
    order = ["symbol", "ts"] if "ts" in ds else ["symbol", "date"]
    ds = ds.sort_values(order, kind="stable").reset_index(drop=True)
    results: dict[str, dict] = {}

    for name in model_names:
        t0 = time.perf_counter()
        oos, fold_rows = [], []
        for f in folds:
            fit, val, test = masks(ds["date"], f)
            if "eval_universe" in ds:
                test = test & ds["eval_universe"]
            test_l = test & ds["y"].notna()
            m, pv, pt = _fit_predict(name, spec, ds, feats, fit, val, test)
            thr = threshold_fn(pv) if threshold_fn else None
            tdf = ds.loc[test]
            lab = tdf["y"].notna().to_numpy()
            cm = ev.classification_metrics(tdf["y"].to_numpy()[lab], pt[lab], tdf["fwd_ret"].to_numpy()[lab])
            base = ev.prior_baseline(ds.loc[fit & ds["y"].notna(), "y"].to_numpy(), tdf["y"].to_numpy()[lab])
            fold_rows.append(
                {
                    "fold": f.as_dict(),
                    "metrics": {
                        k: cm[k]
                        for k in (
                            "n",
                            "accuracy",
                            "macro_f1",
                            "log_loss",
                            "brier",
                            "roc_auc_ovr_macro",
                            "direction_auc",
                        )
                        if k in cm
                    },
                    "baseline": base,
                    "best_iteration": m.best_iteration,
                }
            )
            o = tdf[
                ["date", "symbol", "fwd_ret", "y"] + (["fwd_ret_abs"] if "fwd_ret_abs" in tdf else [])
            ].copy()
            o[["p_down", "p_neutral", "p_up"]] = pt
            o["threshold"] = thr
            oos.append(o)
            log.info(
                "fold_done",
                model=name,
                fold=f.k,
                logloss=round(cm["log_loss"], 4),
                base=round(base["log_loss"], 4),
                dir_auc=round(cm.get("direction_auc", np.nan), 4),
            )
            del test_l
        oos_df = pd.concat(oos)
        lab = oos_df["y"].notna()
        P = oos_df[["p_down", "p_neutral", "p_up"]].to_numpy()
        wf = ev.classification_metrics(
            oos_df.loc[lab, "y"].to_numpy(), P[lab.to_numpy()], oos_df.loc[lab, "fwd_ret"].to_numpy()
        )
        wf.update(
            ev.information_coefficient(
                oos_df["date"].to_numpy(), P[:, 2] - P[:, 0], oos_df["fwd_ret"].to_numpy()
            )
        )
        wf["baseline_prior"] = {
            k: float(np.mean([r["baseline"][k] for r in fold_rows]))
            for k in ("accuracy", "macro_f1", "log_loss", "brier")
        }
        wf["folds"] = fold_rows
        wf["trading"] = _bt(spec, oos_df, P)
        results[name] = {"walk_forward": wf, "seconds_wf": time.perf_counter() - t0}

    # ---- locked holdout: every model retrained on all pre-holdout data, evaluated once ----
    fit, val, test = masks(ds["date"], holdout)
    if "eval_universe" in ds:
        test = test & ds["eval_universe"]
    for name in model_names:
        t0 = time.perf_counter()
        m, pv, pt = _fit_predict(name, spec, ds, feats, fit, val, test)
        tdf = ds.loc[test]
        lab = tdf["y"].notna().to_numpy()
        hm = ev.classification_metrics(tdf["y"].to_numpy()[lab], pt[lab], tdf["fwd_ret"].to_numpy()[lab])
        hm["baseline_prior"] = ev.prior_baseline(
            ds.loc[fit & ds["y"].notna(), "y"].to_numpy(), tdf["y"].to_numpy()[lab]
        )
        hm.update(
            ev.information_coefficient(tdf["date"].to_numpy(), pt[:, 2] - pt[:, 0], tdf["fwd_ret"].to_numpy())
        )
        o = tdf[["date", "symbol", "fwd_ret", "y"] + (["fwd_ret_abs"] if "fwd_ret_abs" in tdf else [])].copy()
        o["threshold"] = threshold_fn(pv) if threshold_fn else None
        hm["trading"] = _bt(spec, o, pt)
        results[name]["holdout"] = hm
        results[name]["model"] = m
        results[name]["seconds_holdout"] = time.perf_counter() - t0

    periods = {"folds": [f.as_dict() for f in folds], "holdout": holdout.as_dict()}
    for name in model_names:
        r = results[name]
        session.add(
            MLExperiment(
                run_id=run_id,
                pipeline=spec.name,
                model_name=name,
                dataset_version=dataset_ver,
                model_config=r["model"].config(),
                periods=periods,
                walk_forward_metrics=_jsonable(r["walk_forward"]),
                holdout_metrics=_jsonable(r["holdout"]),
                train_seconds=r["seconds_wf"] + r["seconds_holdout"],
            )
        )
    session.commit()

    if not finalize_run:
        return {"run_id": run_id, "evaluated": model_names}
    return finalize(session, run_id, ds, feats, spec, holdout, dataset_ver, artifacts_dir,
                    trained={n: r["model"] for n, r in results.items()})


def _rank_key(wf: dict) -> tuple:
    return (wf["log_loss"] < wf["baseline_prior"]["log_loss"], wf.get("direction_auc", 0.5), -wf["log_loss"])


def finalize(session: Session, run_id: str, ds: pd.DataFrame, feats: list[str], spec: PipelineSpec, holdout: Fold,
             dataset_ver: str, artifacts_dir: Path, trained: dict | None = None) -> dict:
    """Select on WALK-FORWARD results of every model stored for run_id, then register the winner.
    If the winner was evaluated in another process, it is refit here on the identical pre-holdout split
    (deterministic seeds) to obtain the artifact; its stored holdout metrics are the ones reported."""
    exps = session.query(MLExperiment).filter_by(run_id=run_id).all()
    if not exps:
        raise ValueError(f"no experiments stored for run {run_id}")
    results = {e.model_name: {"walk_forward": e.walk_forward_metrics, "holdout": e.holdout_metrics} for e in exps}
    ranked = sorted(results, key=lambda n: _rank_key(results[n]["walk_forward"]), reverse=True)
    selected = ranked[0]
    model = (trained or {}).get(selected)
    if model is None:
        order = ["symbol", "ts"] if "ts" in ds else ["symbol", "date"]
        ds = ds.sort_values(order, kind="stable").reset_index(drop=True)
        fit, val, test = masks(ds["date"], holdout)
        model, _, _ = _fit_predict(selected, spec, ds, feats, fit, val, test)
    reg = register(session, spec, {**results[selected], "model": model}, selected, run_id, dataset_ver, feats,
                   artifacts_dir)
    return {"run_id": run_id, "selected": selected, "ranking": ranked, "registered": reg, "results": results}


def _bt(spec: PipelineSpec, df: pd.DataFrame, P: np.ndarray) -> dict:
    thr = df["threshold"].iloc[0] if "threshold" in df and df["threshold"].notna().any() else None
    if thr is not None and df["threshold"].nunique() > 1:  # per-fold thresholds: apply each to its own rows
        thr = df["threshold"].to_numpy()
    return spec.backtest(df, P, thr)


def promotion_decision(r: dict) -> tuple[bool, list[str]]:
    """A model is promoted only if it beats the no-skill baseline out of sample on BOTH walk-forward and
    holdout probability quality, and its walk-forward direction ranking is better than chance."""
    wf, ho = r["walk_forward"], r["holdout"]
    reasons, ok = [], True
    checks = [
        ("walk-forward log loss < prior baseline", wf["log_loss"] < wf["baseline_prior"]["log_loss"]),
        ("holdout log loss < prior baseline", ho["log_loss"] < ho["baseline_prior"]["log_loss"]),
        ("walk-forward direction AUC >= 0.51", wf.get("direction_auc", 0) >= 0.51),
        ("walk-forward mean IC > 0 with t-stat >= 2", wf.get("ic_mean", 0) > 0 and wf.get("ic_t", 0) >= 2),
        ("holdout direction AUC > 0.5", ho.get("direction_auc", 0) > 0.5),
        ("walk-forward strategy Sharpe after costs > 0", (wf["trading"]["strategy"].get("sharpe") or 0) > 0),
    ]
    for text, passed in checks:
        reasons.append(("PASS: " if passed else "FAIL: ") + text)
        ok &= bool(passed)
    return ok, reasons


def register(session, spec, r, name, run_id, dataset_ver, feats, artifacts_dir: Path) -> dict:
    version = f"{spec.name}-{name}-{run_id}"
    d = artifacts_dir / "models" / spec.name / version
    d.mkdir(parents=True, exist_ok=True)
    path = d / "model.joblib"
    joblib.dump({"model": r["model"], "features": feats if name in TABULAR else spec.seq_features}, path)
    sha = hashlib.sha256(path.read_bytes()).hexdigest()
    promoted, reasons = promotion_decision(r)
    meta = {
        "version": version,
        "pipeline": spec.name,
        "model": name,
        "dataset_version": dataset_ver,
        "features": feats,
        "walk_forward": _jsonable(r["walk_forward"]),
        "holdout": _jsonable(r["holdout"]),
        "promoted": promoted,
        "promotion_reasons": reasons,
        "artifact_sha256": sha,
    }
    (d / "meta.json").write_text(json.dumps(meta, indent=2, default=str))
    if promoted:
        session.query(MLModel).filter_by(pipeline=spec.name, promoted=True).update({"promoted": False})
    session.add(
        MLModel(
            version=version,
            pipeline=spec.name,
            model_name=name,
            run_id=run_id,
            dataset_version=dataset_ver,
            artifact_path=str(path),
            artifact_sha256=sha,
            features=feats if name in TABULAR else spec.seq_features,
            metrics={"walk_forward": _summary(r["walk_forward"]), "holdout": _summary(r["holdout"])},
            promoted=promoted,
            promotion_reasons=reasons,
        )
    )
    session.commit()
    return {"version": version, "promoted": promoted, "reasons": reasons, "artifact": str(path)}


def _summary(m: dict) -> dict:
    keys = (
        "n",
        "accuracy",
        "macro_f1",
        "log_loss",
        "brier",
        "roc_auc_ovr_macro",
        "direction_auc",
        "ic_mean",
        "ic_t",
    )
    out = {k: m[k] for k in keys if k in m}
    out["baseline_prior"] = m.get("baseline_prior")
    out["trading"] = m.get("trading")
    return out


def _jsonable(x):
    return json.loads(json.dumps(x, default=lambda o: o.item() if hasattr(o, "item") else str(o)))

"""ML engine CLI.

python -m app.engines.ml.cli global-data
python -m app.engines.ml.cli train --pipeline swing --models logreg,random_forest,xgboost,lightgbm,lstm,gru
python -m app.engines.ml.cli train --pipeline intraday --models ...
"""

import argparse
import json
import sys
import time

import numpy as np

from app.core.config import REPO_DIR, get_settings
from app.core.db import get_session
from app.core.logging import configure_logging
from app.engines.data.global_data import download_global, load_global
from app.engines.data.service import universe_members
from app.engines.data.storage import CandleLake
from app.engines.ml import evaluate as ev
from app.engines.ml import swing
from app.engines.ml.report import write_report
from app.engines.ml.splits import holdout_fold, walk_forward
from app.engines.ml.trainer import PipelineSpec, finalize, run, save_dataset

SWING_SEQ = [
    "ret_1",
    "ret_5",
    "ret_20",
    "dist_ema20",
    "dist_ema50",
    "rsi14",
    "macd_hist",
    "atr14",
    "bb_pctb",
    "vol20",
    "rel_vol20",
    "nifty_ret_1",
    "nifty_ret_5",
    "vix_chg5",
    "rs_nifty_5",
    "g_spx_r1",
]

SWING_PROTOCOL = {"first_test": "2020-01-01", "holdout_start": "2025-11-01", "test_months": 6}
INTRADAY_PROTOCOL = {"first_test": "2023-07-01", "holdout_start": "2026-05-01", "test_months": 3}


def build(pipeline: str, session, settings, overrides: dict | None = None):
    lake = CandleLake(settings.data_dir)
    glob = load_global(settings.data_dir)
    if pipeline == "swing":
        ov = dict(overrides or {})
        if "train_universes" in ov:
            ov["train_universes"] = tuple(ov["train_universes"])
        cfg = swing.SwingConfig(**ov)
        mem, seen = [], set()
        for u in cfg.train_universes:
            for m in universe_members(session, u):
                if m.symbol not in seen:
                    seen.add(m.symbol)
                    mem.append((m.symbol, m.instrument_key, m.sector_index_key, u == "NIFTY50"))
        ds = swing.build_swing_dataset(lake, mem, glob, cfg)
        feats = swing.feature_columns(ds)
        spec = PipelineSpec(
            "swing",
            cfg.horizon,
            cfg.cost,
            lambda df, p, thr: ev.swing_backtest(df, p, cfg.horizon, cfg.cost, top_k=10),
            seq_features=SWING_SEQ,
            seq_len=20,
        )
        return ds, feats, spec, cfg.to_dict(), SWING_PROTOCOL, None
    from app.engines.ml import intraday

    mem = [(m.symbol, m.instrument_key, m.sector_index_key) for m in universe_members(session)]

    cfg = intraday.IntradayConfig()
    ds = intraday.build_intraday_dataset(lake, mem, glob, cfg)
    feats = intraday.feature_columns(ds)
    spec = PipelineSpec(
        "intraday",
        1,
        cfg.cost,
        lambda df, p, thr: ev.intraday_backtest(df, p, cfg.cost, thr),
        seq_features=intraday.SEQ_FEATURES,
        seq_len=12,
        # Compute caps for 1.25M rows (documented in the Phase 4 report); early stopping still applies.
        model_overrides={
            "random_forest": {"n_estimators": 200, "max_samples": 0.1},
            "xgboost": {"n_estimators": 600, "learning_rate": 0.05},
            "lightgbm": {"n_estimators": 800, "learning_rate": 0.05},
            "lstm": {"max_fit_rows": 300_000, "max_epochs": 10, "batch": 1024},
            "gru": {"max_fit_rows": 300_000, "max_epochs": 10, "batch": 1024},
        },
    )
    # Trade only the most confident 10% of decisions, with the cut-off learned on the validation slice.
    thr_fn = lambda pv: float(np.quantile(np.abs(pv[:, 2] - pv[:, 0]), 0.90))  # noqa: E731
    return ds, feats, spec, cfg.to_dict(), INTRADAY_PROTOCOL, thr_fn


def _reexec_torch_mode_if_needed(args, session) -> None:
    """finalize must refit the winner in a process mode that can train it (see app/engines/ml/__init__.py)."""
    import os

    from app.engines.ml.trainer import _rank_key
    from app.models.ml import MLExperiment

    exps = session.query(MLExperiment).filter_by(run_id=args.run_id).all()
    if not exps:
        return
    best = max(exps, key=lambda e: _rank_key(e.walk_forward_metrics)).model_name
    want = "torch" if best in ("lstm", "gru") else "default"
    have = "torch" if os.environ.get("AQ_ML_MODE") == "torch" else "default"
    if want != have:
        env = {**os.environ, "AQ_ML_MODE": "torch"} if want == "torch" else {
            k: v for k, v in os.environ.items() if k != "AQ_ML_MODE"}
        os.execve(sys.executable, [sys.executable, "-m", "app.engines.ml.cli", *sys.argv[1:]], env)


def cmd_train(args, session, settings) -> int:
    if args.cmd == "finalize":
        _reexec_torch_mode_if_needed(args, session)
    t0 = time.perf_counter()
    overrides = json.loads(args.config) if args.config else None
    ds, feats, spec, cfg, proto, thr_fn = build(args.pipeline, session, settings, overrides)
    t_build = time.perf_counter() - t0
    ver = save_dataset(session, ds, args.pipeline, {**cfg, **proto}, feats, settings.data_dir)
    labelled = ds[ds["y"].notna() & ds.get("eval_universe", True)]
    folds = walk_forward(
        labelled["date"],
        proto["first_test"],
        proto["holdout_start"],
        proto["test_months"],
        purge=spec.horizon,
    )
    hold = holdout_fold(labelled["date"], proto["holdout_start"], purge=spec.horizon)
    print(
        json.dumps(
            {
                "dataset_version": ver,
                "rows": len(ds),
                "features": len(feats),
                "folds": len(folds),
                "build_seconds": round(t_build, 1),
            }
        ),
        flush=True,
    )
    if args.cmd == "finalize":
        out = finalize(session, args.run_id, ds, feats, spec, hold, ver, settings.artifacts_dir)
    else:
        out = run(
            session,
            ds,
            feats,
            spec,
            folds,
            hold,
            args.models.split(","),
            ver,
            settings.artifacts_dir,
            threshold_fn=thr_fn,
            run_id=args.run_id or None,
            finalize_run=not args.no_finalize,
        )
        if args.no_finalize:
            print(json.dumps(out))
            return 0
    out["dataset"] = {
        "version": ver,
        "rows": len(ds),
        "labelled_rows": len(labelled),
        "features": feats,
        "symbols": int(ds["symbol"].nunique()),
        "first_date": str(ds["date"].min().date()),
        "last_date": str(ds["date"].max().date()),
        "config": cfg,
        "protocol": proto,
        "label_distribution": labelled["y"].value_counts(normalize=True).sort_index().round(4).tolist(),
        "build_seconds": round(t_build, 1),
    }
    path = write_report(out, REPO_DIR / "reports" / "ml", args.pipeline)
    print(
        json.dumps(
            {
                "selected": out["selected"],
                "ranking": out["ranking"],
                "registered": out["registered"],
                "report": str(path),
            },
            indent=1,
        )
    )
    return 0


def main(argv=None) -> int:
    p = argparse.ArgumentParser(prog="astraquant-ml")
    sub = p.add_subparsers(dest="cmd", required=True)
    sub.add_parser("global-data")
    t = sub.add_parser("train")
    t.add_argument("--pipeline", choices=["swing", "intraday"], required=True)
    t.add_argument("--models", default="logreg,random_forest,xgboost,lightgbm,lstm,gru")
    t.add_argument(
        "--config", default="", help='JSON overrides for the pipeline config, e.g. {"label_c": 0.4}'
    )
    t.add_argument("--run-id", default="", help="append to an existing run (models evaluated in another process)")
    t.add_argument("--no-finalize", action="store_true", help="store experiments only; select/register later")
    fz = sub.add_parser("finalize", help="select across all models stored for a run and register the winner")
    fz.add_argument("--pipeline", choices=["swing", "intraday"], required=True)
    fz.add_argument("--run-id", required=True)
    fz.add_argument("--config", default="")
    fz.set_defaults(models="", no_finalize=False)
    args = p.parse_args(argv)
    settings = get_settings()
    configure_logging(settings.log_level, json=True)
    session = next(get_session())
    try:
        if args.cmd == "global-data":
            print(json.dumps(download_global(settings.data_dir)))
            return 0
        return cmd_train(args, session, settings)  # train and finalize share dataset building
    finally:
        session.close()


if __name__ == "__main__":
    sys.exit(main())

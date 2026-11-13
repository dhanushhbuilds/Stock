"""Signal Lab service: dataset -> same features as training -> models -> causal signals with risk evaluation.

Models used:
  volatility : the PROMOTED swing_vol model from the registry (beats persistence and HAR out of sample)
  direction  : a research Logistic Regression trained on the final swing dataset (all labelled history). It did
               NOT pass the strict promotion gate (the 2020-25 edge did not persist in the 2025-26 holdout), so it is
               only a confirmation filter here, never a sole reason to trade. Disclosed in every response.
"""

import hashlib
import json
from datetime import UTC, datetime
from functools import lru_cache
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.engines.data.global_data import load_global
from app.engines.data.service import universe_members
from app.engines.data.storage import CandleLake
from app.engines.ml import swing
from app.engines.ml.models import LogReg
from app.engines.ml.volatility import add_target
from app.engines.signal_lab import engine
from app.engines.signal_lab.parsing import ParsedSeries
from app.models.ml import MLDataset, MLModel

UPLOAD_PREFIX = "UPLOAD|"


class LabUnavailable(RuntimeError):
    pass


class OverlayLake(CandleLake):
    """The real lake plus uploaded daily series under UPLOAD|<SYMBOL> keys."""

    def __init__(self, base: CandleLake, extra: dict[str, pd.DataFrame]) -> None:
        super().__init__(base.root)
        self.base, self.extra = base, extra
        self.discontinuities, self.quarantine = base.discontinuities, base.quarantine

    def read(self, timeframe, key, start=None, end=None, adjusted=True):
        if key in self.extra and timeframe == "1day":
            return self.extra[key].copy()
        return self.base.read(timeframe, key, start=start, end=end, adjusted=adjusted)


# ---------------------------------------------------------------- models
def direction_model_path(settings: Settings) -> Path:
    return settings.artifacts_dir / "models" / "signal_lab" / "direction_logreg.joblib"


def train_direction_model(session: Session, settings: Settings) -> dict:
    """Fit the research LR on the final swing dataset (all labelled rows; last 15% of dates for calibration)."""
    ds_row = session.scalars(
        select(MLDataset).where(MLDataset.pipeline == "swing").order_by(MLDataset.created_at.desc())
    ).first()
    if ds_row is None:
        raise LabUnavailable("no swing dataset; run the swing training first")
    ds = pd.read_parquet(settings.data_dir / ds_row.path)
    feats = list(ds_row.features)
    lab = ds[ds["y"].notna()].sort_values("date")
    dates = lab["date"].sort_values().unique()
    cut = dates[int(len(dates) * 0.85)]
    fit, val = lab[lab["date"] < cut - pd.Timedelta(days=10)], lab[lab["date"] >= cut]
    m = LogReg().fit(fit[feats], fit["y"].astype(int), val[feats], val["y"].astype(int))
    path = direction_model_path(settings)
    path.parent.mkdir(parents=True, exist_ok=True)
    meta = {
        "dataset_version": ds_row.version,
        "features": feats,
        "trained_through": str(lab["date"].max().date()),
        "rows": int(len(lab)),
        "created_at": datetime.now(UTC).isoformat(),
        "status": "research model (not promoted): direction edge did not persist in the 2025-26 holdout",
    }
    joblib.dump({"model": m, **meta}, path)
    meta["sha256"] = hashlib.sha256(path.read_bytes()).hexdigest()
    path.with_suffix(".json").write_text(json.dumps(meta, indent=2))
    models.cache_clear()
    return meta


@lru_cache
def models(artifacts_dir: str, vol_path: str) -> tuple[dict, dict]:
    d = joblib.load(Path(artifacts_dir) / "models" / "signal_lab" / "direction_logreg.joblib")
    v = joblib.load(vol_path)
    return d, v


def load_models(session: Session, settings: Settings) -> tuple[dict, dict, MLModel]:
    vol = session.scalars(
        select(MLModel)
        .where(MLModel.pipeline == "swing_vol", MLModel.promoted.is_(True))
        .order_by(MLModel.created_at.desc())
    ).first()
    if vol is None:
        raise LabUnavailable("no promoted volatility model (run: python -m app.engines.ml.volatility)")
    if not direction_model_path(settings).exists():
        raise LabUnavailable("direction model not trained (run: python -m app.engines.signal_lab.train)")
    d, v = models(str(settings.artifacts_dir), vol.artifact_path)
    return d, v, vol


# ---------------------------------------------------------------- analysis
def _members(session: Session, exclude: set[str]) -> list[tuple]:
    mem, seen = [], set(exclude)
    for u in ("NIFTY50", "NIFTYNEXT50", "NIFTYMIDCAP100"):
        for m in universe_members(session, u):
            if m.symbol not in seen:
                seen.add(m.symbol)
                mem.append((m.symbol, m.instrument_key, m.sector_index_key, False))
    return mem


def analyze(
    session: Session, settings: Settings, series: list[ParsedSeries], capital: float, source: str = "upload"
) -> dict:
    dmod, vmod, vreg = load_models(session, settings)
    base = CandleLake(settings.data_dir)
    sector_of = {
        m.symbol: m.sector_index_key
        for u in ("NIFTY50", "NIFTYNEXT50", "NIFTYMIDCAP100")
        for m in universe_members(session, u)
    }
    extra = {UPLOAD_PREFIX + s.symbol: s.frame for s in series}
    lake = OverlayLake(base, extra)
    targets = [(s.symbol, UPLOAD_PREFIX + s.symbol, sector_of.get(s.symbol), True) for s in series]
    # Build with the full training universe so cross-sectional rank features mean the same as in training.
    members = _members(session, {s.symbol for s in series}) + targets
    cfg = swing.SwingConfig(start="1990-01-01")
    ds = swing.build_swing_dataset(lake, members, load_global(settings.data_dir), cfg)
    out = {
        "source": source,
        "capital": capital,
        "generated_at": datetime.now(UTC).isoformat(),
        "models": {
            "direction": {
                "name": "Logistic Regression",
                "status": dmod["status"],
                "trained_through": dmod["trained_through"],
                "dataset": dmod["dataset_version"],
            },
            "volatility": {
                "name": vreg.model_name,
                "version": vreg.version,
                "status": "promoted",
                "holdout_r2": (vreg.metrics.get("holdout") or {}).get("r2_log"),
            },
        },
        "rules": engine.__doc__,
        "results": [],
    }
    for s in series:
        key = UPLOAD_PREFIX + s.symbol
        up = ds[ds["instrument_key"] == key].copy()
        if up.empty:
            out["results"].append({"symbol": s.symbol, "error": "not enough history after the 200-day warm-up"})
            continue
        up = add_target(up)  # adds lv5/lv20/lv60 used by the volatility model (forward targets are unused)
        X = up.reindex(columns=dmod["features"])
        p = dmod["model"].predict_proba(X)
        vol_log = vmod["model"].predict(up.reindex(columns=vmod["features"]))
        preds = pd.DataFrame(
            {
                "date": up["date"].to_numpy(),
                "p_down": p[:, 0],
                "p_neutral": p[:, 1],
                "p_up": p[:, 2],
                "vol_log": vol_log,
            }
        )
        res = engine.run(s.frame, preds, key, sector_of.get(s.symbol), capital)
        feature_cov = float(1 - X.iloc[-1].isna().mean()) if len(X) else 0.0
        notes = list(s.notes)
        if s.symbol not in sector_of:
            notes.append("Symbol not in the NIFTY universes: sector-relative features are unavailable (imputed).")
        last_ctx = ds.loc[ds["instrument_key"] == key, ["vix", "nifty_ret_5"]].tail(1)
        if last_ctx.isna().any(axis=None):
            notes.append(
                "Some market-context features (NIFTY/VIX/global) are missing for the latest dates "
                "(data beyond the stored history); the models impute them."
            )
        out["results"].append(
            {
                "symbol": s.symbol,
                "rows": len(s.frame),
                "first_date": str(s.frame["ts"].iloc[0].date()),
                "last_date": str(s.frame["ts"].iloc[-1].date()),
                "quality": s.quality,
                "notes": notes,
                "feature_coverage_latest": feature_cov,
                "final": res.final,
                "metrics": res.metrics,
                "trades": res.trades,
                "equity": res.equity,
                "days": res.days,
            }
        )
    return out


def series_from_lake(session: Session, settings: Settings, symbol: str) -> list[ParsedSeries]:
    from app.engines.data.instruments import resolve

    inst = resolve(session, symbol)
    df = CandleLake(settings.data_dir).read("1day", inst.instrument_key)
    if df.empty:
        raise LabUnavailable(f"no stored daily data for {symbol}")
    frame = df[["ts", "open", "high", "low", "close", "volume", "oi"]].reset_index(drop=True)
    return [ParsedSeries(inst.trading_symbol, frame, ["Stored Upstox daily data (adjusted)."], {"passed": True})]


def to_csv(result: dict) -> str:
    rows = []
    for r in result["results"]:
        for d in r.get("days", []):
            rows.append(
                {
                    "symbol": r["symbol"],
                    **{
                        k: d[k]
                        for k in (
                            "date",
                            "close",
                            "action",
                            "position",
                            "p_up",
                            "p_neutral",
                            "p_down",
                            "score",
                            "vol_pred_annual",
                            "vol_pct",
                            "uptrend",
                            "stop",
                        )
                    },
                    "reasons": " | ".join(d["reasons"]),
                }
            )
    return pd.DataFrame(rows).to_csv(index=False)


def _jsonable(x):
    if isinstance(x, dict):
        return {k: _jsonable(v) for k, v in x.items()}
    if isinstance(x, (list, tuple)):
        return [_jsonable(v) for v in x]
    if isinstance(x, (np.floating, float)):
        return None if not np.isfinite(x) else float(x)
    if isinstance(x, np.integer):
        return int(x)
    if isinstance(x, np.bool_):
        return bool(x)
    return x


def jsonable(result: dict) -> dict:
    return _jsonable(result)

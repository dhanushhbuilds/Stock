"""Volatility forecasting (spec: "Volatility forecasting", "Risk estimation").

Target: log realised volatility of the NEXT h sessions, rv = sqrt(mean(r^2)) of daily log returns t+1..t+h
(known only after t+h; used strictly as a label). Inputs are the swing pipeline's causal features at the close
of day t.

Baselines a model must beat out of sample:
  persistence : log rv_next = log(vol20 at t)                       (naive)
  HAR         : linear in log vol5, log vol20, log vol60             (Corsi 2009, standard benchmark)
Candidates: HAR-X (HAR + VIX, NIFTY vol, range, ATR, volume) and LightGBM on all features.

Same walk-forward folds (purged by h) and a once-only locked holdout, as for direction models.

    python -m app.engines.ml.volatility
"""

import hashlib
import json
import time

import joblib
import lightgbm as lgb
import numpy as np
import pandas as pd
from sklearn.impute import SimpleImputer
from sklearn.linear_model import Ridge
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler

from app.core.config import REPO_DIR, get_settings
from app.core.db import get_session
from app.engines.data.global_data import load_global
from app.engines.data.storage import CandleLake
from app.engines.ml import swing
from app.engines.ml.research import _members
from app.engines.ml.splits import holdout_fold, masks, walk_forward
from app.models.ml import MLExperiment, MLModel

H = 5
PROTO = {"first_test": "2020-01-01", "holdout_start": "2025-11-01", "test_months": 6}
EPS = 1e-4
HAR = ["lv5", "lv20", "lv60"]
HARX = [
    *HAR,
    "vix",
    "vix_chg5",
    "nifty_vol20",
    "range",
    "atr14",
    "rel_vol20",
    "gap",
    "ret_1",
    "ret_5",
    "dow",
    "g_usvix",
    "g_spx_r1",
]


def add_target(ds: pd.DataFrame, h: int = H) -> pd.DataFrame:
    ds = ds.sort_values(["symbol", "date"], kind="stable").reset_index(drop=True)
    r = np.log(ds["close"] / ds.groupby("symbol")["close"].shift(1))
    r2 = (r**2).groupby(ds["symbol"])
    fwd_ms = sum(r2.shift(-k) for k in range(1, h + 1)) / h  # mean of next h squared returns
    ds["rv_next"] = np.sqrt(fwd_ms)
    ds["y_vol"] = np.log(ds["rv_next"] + EPS)
    ds["lv5"] = np.log(ds.groupby("symbol")["close"].transform(lambda c: np.log(c / c.shift(1)).rolling(5).std()) + EPS)
    ds["lv20"] = np.log(ds["vol20"] + EPS)
    ds["lv60"] = np.log(ds["vol60"] + EPS)
    return ds


def _ridge():
    return make_pipeline(SimpleImputer(strategy="median"), StandardScaler(), Ridge(alpha=1.0))


def _lgbm():
    return lgb.LGBMRegressor(
        n_estimators=2000,
        learning_rate=0.03,
        num_leaves=31,
        min_child_samples=200,
        subsample=0.8,
        subsample_freq=1,
        colsample_bytree=0.7,
        reg_lambda=5.0,
        random_state=42,
        verbose=-1,
    )


def fit_predict(name: str, ds, feats, fit, val, test):
    y = ds["y_vol"]
    if name == "persistence":
        return None, ds.loc[test, "lv20"].to_numpy()
    cols = {"har": HAR, "harx": HARX, "lightgbm": feats}[name]
    f, v = fit & y.notna(), val & y.notna()
    if name == "lightgbm":
        m = _lgbm().fit(
            ds.loc[f, cols],
            y[f],
            eval_set=[(ds.loc[v, cols], y[v])],
            callbacks=[lgb.early_stopping(150, verbose=False)],
        )
    else:
        m = _ridge().fit(ds.loc[f | v, cols], y[f | v])
    return m, m.predict(ds.loc[test, cols])


def metrics(y_log: np.ndarray, p_log: np.ndarray) -> dict:
    ok = np.isfinite(y_log) & np.isfinite(p_log)
    y, p = y_log[ok], p_log[ok]
    sst = float(np.sum((y - y.mean()) ** 2))
    v, vh = np.exp(2 * y), np.exp(2 * p)  # variances
    return {
        "n": int(ok.sum()),
        "r2_log": 1 - float(np.sum((y - p) ** 2)) / sst,
        "rmse_log": float(np.sqrt(np.mean((y - p) ** 2))),
        "mae_log": float(np.mean(np.abs(y - p))),
        "qlike": float(np.mean(v / vh - np.log(v / vh) - 1)),
        "corr": float(np.corrcoef(y, p)[0, 1]),
        "rank_corr": float(pd.Series(y).corr(pd.Series(p), method="spearman")),
    }


def main() -> dict:
    s = get_settings()
    session = next(get_session())
    lake = CandleLake(s.data_dir)
    t0 = time.perf_counter()
    ds = swing.build_swing_dataset(lake, _members(session), load_global(s.data_dir), swing.SwingConfig())
    ds = add_target(ds)
    feats = [c for c in swing.feature_columns(ds) if c not in ("rv_next", "y_vol")]
    lab = ds[ds["y_vol"].notna() & ds["eval_universe"]]
    folds = walk_forward(lab["date"], PROTO["first_test"], PROTO["holdout_start"], PROTO["test_months"], purge=H)
    hold = holdout_fold(lab["date"], PROTO["holdout_start"], purge=H)
    names = ["persistence", "har", "harx", "lightgbm"]
    run_id = time.strftime("%Y%m%d-%H%M%S-vol")
    out = {
        "run_id": run_id,
        "target": f"log realised vol of next {H} sessions",
        "protocol": PROTO,
        "rows": len(ds),
        "features": len(feats),
        "walk_forward": {},
        "holdout": {},
        "folds": {},
    }
    for name in names:
        ys, ps, per = [], [], []
        for f in folds:
            fit, val, test = masks(ds["date"], f)
            test = test & ds["eval_universe"] & ds["y_vol"].notna()
            _, p = fit_predict(name, ds, feats, fit, val, test)
            y = ds.loc[test, "y_vol"].to_numpy()
            ys.append(y)
            ps.append(p)
            per.append({"test_start": str(f.test_start.date()), **metrics(y, p)})
        out["walk_forward"][name] = metrics(np.concatenate(ys), np.concatenate(ps))
        out["folds"][name] = per
        fit, val, test = masks(ds["date"], hold)
        test = test & ds["eval_universe"] & ds["y_vol"].notna()
        m, p = fit_predict(name, ds, feats, fit, val, test)
        out["holdout"][name] = metrics(ds.loc[test, "y_vol"].to_numpy(), p)
        if m is not None:
            out.setdefault("_models", {})[name] = m
        print(
            json.dumps(
                {
                    "model": name,
                    "wf_r2": round(out["walk_forward"][name]["r2_log"], 4),
                    "ho_r2": round(out["holdout"][name]["r2_log"], 4),
                }
            ),
            flush=True,
        )

    # selection on walk-forward; promotion requires beating BOTH baselines on walk-forward AND holdout
    cands = ["harx", "lightgbm"]
    best = min(cands, key=lambda n: out["walk_forward"][n]["rmse_log"])
    wf, ho = out["walk_forward"], out["holdout"]
    reasons = []
    for base in ("persistence", "har"):
        for part, d in (("walk-forward", wf), ("holdout", ho)):
            ok = d[best]["rmse_log"] < d[base]["rmse_log"]
            reasons.append(f"{'PASS' if ok else 'FAIL'}: {part} RMSE(log vol) below {base}")
    promoted = all(r.startswith("PASS") for r in reasons)
    model = out.pop("_models")[best]
    version = f"swing_vol-{best}-{run_id}"
    d = s.artifacts_dir / "models" / "swing_vol" / version
    d.mkdir(parents=True, exist_ok=True)
    path = d / "model.joblib"
    cols = HARX if best == "harx" else feats
    joblib.dump({"model": model, "features": cols, "target": out["target"]}, path)
    sha = hashlib.sha256(path.read_bytes()).hexdigest()
    if promoted:
        session.query(MLModel).filter_by(pipeline="swing_vol", promoted=True).update({"promoted": False})
    for n in names:
        session.add(
            MLExperiment(
                run_id=run_id,
                pipeline="swing_vol",
                model_name=n,
                dataset_version="vol-" + run_id[-12:],
                model_config={"name": n},
                periods={"folds": [f.as_dict() for f in folds], "holdout": hold.as_dict()},
                walk_forward_metrics={**wf[n], "folds": out["folds"][n]},
                holdout_metrics=ho[n],
                train_seconds=0.0,
            )
        )
    session.add(
        MLModel(
            version=version,
            pipeline="swing_vol",
            model_name=best,
            run_id=run_id,
            dataset_version="vol",
            artifact_path=str(path),
            artifact_sha256=sha,
            features=cols,
            metrics={"walk_forward": wf[best], "holdout": ho[best]},
            promoted=promoted,
            promotion_reasons=reasons,
        )
    )
    session.commit()
    out.update(
        {
            "selected": best,
            "promoted": promoted,
            "promotion_reasons": reasons,
            "version": version,
            "seconds": round(time.perf_counter() - t0, 1),
        }
    )
    (REPO_DIR / "reports" / "ml" / f"volatility_{run_id}.json").write_text(json.dumps(out, indent=2, default=str))
    print(json.dumps({k: out[k] for k in ("selected", "promoted", "promotion_reasons", "version", "seconds")}))
    return out


if __name__ == "__main__":
    main()

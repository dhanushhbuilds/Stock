"""Research question (Review-1 slide 4): does ML add value over rule-based strategies?

Variants, all on identical walk-forward test windows (2020-01 -> 2025-10), long-only, turnover-based costs:
  A. ml_top10            : top 10 NIFTY 50 stocks by ML score (p_up - p_down), score > 0
  B. trend_equal_weight  : every stock in an uptrend (close > SMA200 and SMA50 > SMA200), equal weight  [no ML]
  C. trend_ml_top10      : the trend filter of B, then the top 10 by ML score                          [ML + rules]
  D. buy_and_hold        : equal weight all stocks (benchmark)
for horizons h = 5 and h = 20 sessions (rebalance every h sessions).

The model is Logistic Regression (best walk-forward IC in Phase 4). The locked holdout (2025-11 ->) is evaluated
ONCE, for the variant/horizon chosen on walk-forward Sharpe, and reported regardless of outcome.

    python -m app.engines.ml.research
"""

import json
import time
from datetime import date

import pandas as pd

from app.core.config import REPO_DIR, get_settings
from app.core.db import get_session
from app.engines.data.global_data import load_global
from app.engines.data.service import universe_members
from app.engines.data.storage import CandleLake
from app.engines.ml import evaluate as ev
from app.engines.ml import indicators as ind
from app.engines.ml import swing
from app.engines.ml.models import LogReg
from app.engines.ml.splits import holdout_fold, masks, walk_forward

PROTO = {"first_test": "2020-01-01", "holdout_start": "2025-11-01", "test_months": 6}
COST = swing.SwingConfig().cost
TOP_K = 10


def _members(session):
    mem, seen = [], set()
    for u in ("NIFTY50", "NIFTYNEXT50", "NIFTYMIDCAP100"):
        for m in universe_members(session, u):
            if m.symbol not in seen:
                seen.add(m.symbol)
                mem.append((m.symbol, m.instrument_key, m.sector_index_key, u == "NIFTY50"))
    return mem


def _trend_flags(lake: CandleLake, members) -> pd.DataFrame:
    rows = []
    for sym, key, _, ev_u in members:
        if not ev_u:
            continue
        d = lake.read("1day", key)
        c = d["close"].reset_index(drop=True)
        s50, s200 = ind.sma(c, 50), ind.sma(c, 200)
        rows.append(
            pd.DataFrame(
                {
                    "date": d["ts"].dt.tz_localize(None).dt.normalize().to_numpy(),
                    "symbol": sym,
                    "uptrend": ((c > s200) & (s50 > s200)).to_numpy(),
                }
            )
        )
    return pd.concat(rows)


def predictions(ds: pd.DataFrame, feats: list[str], folds, horizon: int) -> pd.DataFrame:
    out = []
    for f in folds:
        fit, val, test = masks(ds["date"], f)
        test = test & ds["eval_universe"]
        y = ds["y"]
        m = LogReg().fit(
            ds.loc[fit & y.notna(), feats],
            y[fit & y.notna()].astype(int),
            ds.loc[val & y.notna(), feats],
            y[val & y.notna()].astype(int),
        )
        p = m.predict_proba(ds.loc[test, feats])
        o = ds.loc[test, ["date", "symbol", "fwd_ret", "fwd_ret_abs", "y"]].copy()
        o["score"] = p[:, 2] - p[:, 0]
        o["p"] = list(p)
        out.append(o)
    return pd.concat(out)


def portfolio(pred: pd.DataFrame, trend: pd.DataFrame, horizon: int, variant: str) -> dict:
    d = pred.merge(trend, on=["date", "symbol"], how="left")
    dates = sorted(d["date"].unique())[::horizon]
    rets, bench, prev, costs, turn = [], [], pd.Series(dtype=float), 0.0, 0.0
    for dt in dates:
        x = d[(d["date"] == dt)].dropna(subset=["fwd_ret_abs"])
        if x.empty:
            continue
        bench.append(x["fwd_ret_abs"].mean())
        if variant == "ml_top10":
            pick = x[x["score"] > 0].nlargest(TOP_K, "score")
            w = pd.Series(1.0 / TOP_K, index=pick["symbol"].to_numpy())
        elif variant == "trend_equal_weight":
            pick = x[x["uptrend"] == True]  # noqa: E712
            w = pd.Series(1.0 / max(len(pick), 1), index=pick["symbol"].to_numpy())
        elif variant == "trend_ml_top10":
            pick = x[(x["uptrend"] == True) & (x["score"] > 0)].nlargest(TOP_K, "score")  # noqa: E712
            w = pd.Series(1.0 / TOP_K, index=pick["symbol"].to_numpy())
        else:  # buy_and_hold
            pick = x
            w = pd.Series(1.0 / len(x), index=x["symbol"].to_numpy())
        t = w.subtract(prev, fill_value=0).abs().sum()
        c = t * COST / 2 if variant != "buy_and_hold" else 0.0
        r = float((pick.set_index("symbol")["fwd_ret_abs"] * w).sum()) - c
        rets.append(r)
        costs += c
        turn += t
        prev = w
    stats = ev.perf_stats(pd.Series(rets), 252 / horizon, costs, 0)
    stats["avg_turnover"] = turn / max(len(rets), 1)
    stats["avg_invested"] = None
    return stats


def ic(pred: pd.DataFrame) -> dict:
    return ev.information_coefficient(pred["date"].to_numpy(), pred["score"].to_numpy(), pred["fwd_ret"].to_numpy())


def main() -> dict:
    s = get_settings()
    session = next(get_session())
    lake = CandleLake(s.data_dir)
    mem = _members(session)
    glob = load_global(s.data_dir)
    trend = _trend_flags(lake, mem)
    out = {
        "protocol": PROTO,
        "model": "logreg",
        "top_k": TOP_K,
        "cost_round_trip": COST,
        "run_date": str(date.today()),
        "variants": ["ml_top10", "trend_equal_weight", "trend_ml_top10", "buy_and_hold"],
        "walk_forward": {},
    }
    data = {}
    for h in (5, 20):
        t0 = time.perf_counter()
        cfg = swing.SwingConfig(horizon=h)
        ds = swing.build_swing_dataset(lake, mem, glob, cfg)
        feats = swing.feature_columns(ds)
        lab = ds[ds["y"].notna() & ds["eval_universe"]]
        folds = walk_forward(lab["date"], PROTO["first_test"], PROTO["holdout_start"], PROTO["test_months"], purge=h)
        pred = predictions(ds, feats, folds, h)
        res = {"ic": ic(pred)}
        for v in out["variants"]:
            res[v] = portfolio(pred, trend, h, v)
        res["seconds"] = round(time.perf_counter() - t0, 1)
        out["walk_forward"][f"h{h}"] = res
        data[h] = (ds, feats, lab)
        print(
            json.dumps(
                {
                    "h": h,
                    "ic": res["ic"].get("ic_mean"),
                    "ic_t": res["ic"].get("ic_t"),
                    **{v: round(res[v]["sharpe"] or 0, 3) for v in out["variants"]},
                }
            ),
            flush=True,
        )

    # choose on walk-forward Sharpe among ML variants, then evaluate the locked holdout ONCE
    best = max(
        ((h, v) for h in (5, 20) for v in ("ml_top10", "trend_ml_top10")),
        key=lambda hv: out["walk_forward"][f"h{hv[0]}"][hv[1]]["sharpe"] or -99,
    )
    h, v = best
    ds, feats, lab = data[h]
    hold = holdout_fold(lab["date"], PROTO["holdout_start"], purge=h)
    hp = predictions(ds, feats, [hold], h)
    out["selected_on_walk_forward"] = {"horizon": h, "variant": v}
    out["holdout"] = {
        "ic": ic(hp),
        v: portfolio(hp, trend, h, v),
        "trend_equal_weight": portfolio(hp, trend, h, "trend_equal_weight"),
        "buy_and_hold": portfolio(hp, trend, h, "buy_and_hold"),
        "period": [str(hold.test_start.date()), str(hold.test_end.date())],
    }
    path = REPO_DIR / "reports" / "ml" / f"research_ml_vs_rules_{date.today()}.json"
    path.write_text(json.dumps(out, indent=2, default=str))
    print(
        json.dumps(
            {
                "selected": best,
                "holdout": {
                    k: (val.get("sharpe") if isinstance(val, dict) and "sharpe" in val else val)
                    for k, val in out["holdout"].items()
                },
            },
            default=str,
        )
    )
    return out


if __name__ == "__main__":
    main()

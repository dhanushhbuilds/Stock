"""Run every strategy over the NIFTY 50 universe: equal capital per stock, portfolio equity, metrics, regimes.

python -m app.engines.strategy.runner
"""

import json
import sys
import time
from datetime import date

import numpy as np
import pandas as pd

from app.core.config import REPO_DIR, get_settings
from app.core.db import get_session
from app.engines.data.service import universe_members
from app.engines.data.storage import CandleLake
from app.engines.ml import indicators as ind
from app.engines.ml.evaluate import perf_stats
from app.engines.ml.swing import NIFTY, VIX
from app.engines.strategy.backtest import backtest_symbol, trades_frame
from app.engines.strategy.charges import ChargeSchedule
from app.engines.strategy.strategies import STRATEGIES

CAPITAL = 5_000_000.0  # Rs 1 lakh per stock: same cost basis (~0.39% round trip) as the ML evaluation
PERIODS = {"in_sample": ("2017-01-01", "2019-12-31"), "out_of_sample": ("2020-01-01", "2026-12-31")}


def regime_series(lake: CandleLake) -> pd.DataFrame:
    """Causal daily regime labels from NIFTY 50 + India VIX (same rules as the decision engine)."""
    n = lake.read("1day", NIFTY)
    n.index = n["ts"].dt.tz_localize(None).dt.normalize()
    c = n["close"]
    e50, e200 = ind.ema(c, 50), ind.ema(c, 200)
    slope = e50 / e50.shift(10) - 1
    trend = np.where((c > e200) & (slope > 0), "bull", np.where((c < e200) & (slope < 0), "bear", "sideways"))
    v = lake.read("1day", VIX)
    v.index = v["ts"].dt.tz_localize(None).dt.normalize()
    pct = v["close"].rolling(252, min_periods=60).apply(lambda s: (s[:-1] < s[-1]).mean(), raw=True)
    vol = pd.Series(
        np.where(pct >= 0.8, "high_vol", np.where(pct <= 0.2, "low_vol", "normal_vol")), index=v.index
    )
    return pd.DataFrame({"trend": pd.Series(trend, index=c.index), "vol": vol}).ffill()


def _daily_bars(lake, key):
    d = lake.read("1day", key)
    return d.assign(ts=d["ts"].dt.tz_localize(None))


def _intraday_bars(lake, key):
    d = lake.read("5minute", key)
    if d.empty:
        return d
    d = d.assign(ts=d["ts"].dt.tz_localize(None))
    hm = d["ts"].dt.strftime("%H:%M")
    d = d[(hm >= "09:15") & (hm <= "15:10")].copy()
    d["date"] = d["ts"].dt.normalize()
    first = d.groupby("date")["ts"].transform("min").dt.strftime("%H:%M")
    return d[(first == "09:15") & (d["ts"].dt.day_of_week < 5)].reset_index(drop=True)


def add_rs_rank(bars: dict[str, pd.DataFrame]) -> None:
    mom = pd.DataFrame(
        {
            s: (b.set_index("ts")["close"].shift(5) / b.set_index("ts")["close"].shift(125) - 1)
            for s, b in bars.items()
        }
    )
    rank = mom.rank(axis=1, pct=True)
    for s, b in bars.items():
        b["rs_rank"] = rank[s].reindex(b["ts"]).to_numpy()


def run(names: list[str] | None = None) -> dict:
    s = get_settings()
    db = next(get_session())
    lake = CandleLake(s.data_dir)
    mem = [(m.symbol, m.instrument_key) for m in universe_members(db)]
    charges = ChargeSchedule()
    reg = regime_series(lake)
    daily = {sym: _daily_bars(lake, k) for sym, k in mem}
    add_rs_rank(daily)
    slice_cap = CAPITAL / len(mem)
    results = {}
    for name in names or list(STRATEGIES):
        st = STRATEGIES[name]
        t0 = time.perf_counter()
        all_trades, eq = [], {}
        for sym, key in mem:
            bars = daily[sym] if st.timeframe == "1day" else _intraday_bars(lake, key)
            if len(bars) < 300:
                continue
            tr, e = backtest_symbol(bars, st, sym, slice_cap, charges)
            all_trades += tr
            eq[sym] = e.groupby(e.index.normalize()).last() if st.timeframe == "5minute" else e
        eqdf = pd.DataFrame(eq).sort_index()
        # Stocks not yet listed hold their slice in cash (flat equity) until their first bar.
        eqdf = eqdf.ffill().fillna(slice_cap)
        port = eqdf.sum(axis=1)
        tdf = trades_frame(all_trades)
        out = {
            "description": st.description,
            "timeframe": st.timeframe,
            "seconds": round(time.perf_counter() - t0, 1),
        }
        wk = (port / CAPITAL)[port.index >= "2017-01-01"].resample("W-FRI").last().dropna()
        out["equity_curve_weekly"] = [[str(d.date()), round(float(v), 5)] for d, v in wk.items()]
        for pname, (a, b) in PERIODS.items():
            p = port[(port.index >= a) & (port.index <= b)]
            if len(p) < 20:
                continue
            rets = p.pct_change().dropna()
            t = tdf[(tdf["entry_ts"] >= a) & (tdf["entry_ts"] <= b)] if len(tdf) else tdf
            stats = perf_stats(rets, 252, float(t["costs"].sum()) if len(t) else 0.0, len(t))
            stats["exposure"] = float((eqdf.loc[p.index].diff().abs().sum(axis=1) > 0).mean())
            if len(t):
                stats["avg_trade_net_pct"] = float((t["net"] / (t["qty"] * t["entry_px"])).mean())
                stats["costs_pct_of_gross_profit"] = float(
                    t["costs"].sum() / max(t.loc[t["gross"] > 0, "gross"].sum(), 1)
                )
                stats["exit_reasons"] = t["reason"].value_counts().to_dict()
            out[pname] = stats
        if len(tdf):
            tdf["entry_day"] = pd.to_datetime(tdf["entry_ts"]).dt.normalize()
            tdf = tdf.join(reg, on="entry_day")
            tdf["ret"] = tdf["net"] / (tdf["qty"] * tdf["entry_px"])
            oos = tdf[tdf["entry_ts"] >= PERIODS["out_of_sample"][0]]
            out["regimes_oos"] = {
                f"{k[0]}/{k[1]}": {
                    "trades": int(len(g)),
                    "win_rate": float((g["ret"] > 0).mean()),
                    "avg_net_return_pct": float(g["ret"].mean() * 100),
                }
                for k, g in oos.groupby(["trend", "vol"])
            }
        results[name] = out
        print(
            json.dumps(
                {
                    "strategy": name,
                    "seconds": out["seconds"],
                    "oos_sharpe": out.get("out_of_sample", {}).get("sharpe"),
                    "oos_total": out.get("out_of_sample", {}).get("total_return"),
                }
            ),
            flush=True,
        )
    # Benchmark: equal-weight buy & hold of the same universe (daily rebalanced, costless)
    closes = pd.DataFrame({sym: b.set_index("ts")["close"] for sym, b in daily.items()}).sort_index()
    bench = closes.pct_change().mean(axis=1).dropna()
    bench_eq = (1 + bench[bench.index >= "2017-01-01"]).cumprod().resample("W-FRI").last().dropna()
    results["_benchmark_equal_weight_buy_hold"] = {
        pname: perf_stats(bench[(bench.index >= a) & (bench.index <= b)], 252)
        for pname, (a, b) in PERIODS.items()
    }
    results["_benchmark_equal_weight_buy_hold"]["equity_curve_weekly"] = [
        [str(d.date()), round(float(v), 5)] for d, v in bench_eq.items()
    ]
    nifty = _daily_bars(lake, NIFTY).set_index("ts")["close"].pct_change().dropna()
    results["_benchmark_nifty50_index"] = {
        pname: perf_stats(nifty[(nifty.index >= a) & (nifty.index <= b)], 252)
        for pname, (a, b) in PERIODS.items()
    }
    results["_meta"] = {
        "capital": CAPITAL,
        "symbols": len(mem),
        "charges": charges.__dict__,
        "round_trip_cost_pct_on_20k_delivery": charges.round_trip_pct(20_000, "DELIVERY"),
        "round_trip_cost_pct_on_20k_intraday": charges.round_trip_pct(20_000, "INTRADAY"),
        "periods": PERIODS,
        "run_date": str(date.today()),
        "notes": [
            "Parameters are textbook defaults chosen before testing (no optimisation).",
            "Universe = current NIFTY 50 constituents: survivorship bias inflates results.",
            "Long-only; signals at close t executed at open t+1.",
        ],
    }
    path = REPO_DIR / "reports" / "strategies" / f"strategies_{date.today()}.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(results, indent=2, default=str))
    return results


if __name__ == "__main__":
    run(sys.argv[1].split(",") if len(sys.argv) > 1 else None)

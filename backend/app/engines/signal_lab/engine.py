"""Signal Lab decision engine: day-by-day, causal BUY / SELL / HOLD / NO_TRADE with risk evaluation.

Rules (fixed a priori; documented in the UI):
  Inputs at the close of day t (only data <= t):
    trend   : uptrend = close > SMA200 and SMA50 > SMA200 (best-tested rule: Strategy Lab)
    ml      : direction model probabilities -> score = P(up) - P(down)
    vol     : promoted volatility model -> predicted daily volatility for the next 5 sessions, and its percentile
              versus the stock's own past forecasts
  Flat:
    BUY candidate if uptrend AND score >= -0.05 (model not bearish) AND vol percentile < 0.90 (not extreme)
    -> the independent risk engine sizes it (stop = 2 x max(ATR14, predicted daily vol x price)); BUY only if approved
    otherwise NO_TRADE (with reasons)
  Long:
    SELL if low <= protective stop (intraday, filled at min(open, stop)), or close < SMA200, or score <= -0.25
    otherwise HOLD (fixed protective stop, as in the tested trend rule)
  Execution: a BUY/SELL decided at the close of t fills at the OPEN of t+1, with full NSE/Upstox delivery charges.
"""

import math
from dataclasses import dataclass, field
from datetime import time

import numpy as np
import pandas as pd

from app.engines.ml import indicators as ind
from app.engines.ml.evaluate import perf_stats
from app.engines.risk.engine import RiskEngine
from app.engines.risk.schemas import MarketSnapshot, OrderIntent, PortfolioState, RiskLimits
from app.engines.strategy.charges import ChargeSchedule

IST_CLOSE = time(15, 30)

# Signal Lab sizes ONE stock: the capital entered is that stock's allocation (a "sleeve"), so per-stock and sector
# caps are 100% of it; 2% of the sleeve is risked to the stop (a standard rule). All other risk checks stay on.
SLEEVE_LIMITS = RiskLimits(risk_per_trade_pct=0.02, max_single_stock_pct=1.0, max_sector_pct=1.0,
                           max_portfolio_var_pct=0.05)


@dataclass(frozen=True)
class Policy:
    min_score: float = -0.05
    exit_score: float = -0.25
    max_vol_pct: float = 0.90
    stop_mult: float = 2.0


@dataclass
class Result:
    days: list[dict] = field(default_factory=list)
    trades: list[dict] = field(default_factory=list)
    equity: list[tuple[str, float, float]] = field(default_factory=list)  # date, strategy, buy & hold
    metrics: dict = field(default_factory=dict)
    final: dict = field(default_factory=dict)


def run(
    prices: pd.DataFrame,
    preds: pd.DataFrame,
    instrument_key: str,
    sector: str | None,
    capital: float,
    policy: Policy | None = None,
    limits: RiskLimits | None = None,
) -> Result:
    """prices: ts, open, high, low, close, volume (daily, IST). preds: date, p_down, p_neutral, p_up, vol_log."""
    P, charges = policy or Policy(), ChargeSchedule()
    risk = RiskEngine(limits or SLEEVE_LIMITS)
    d = prices.assign(date=prices["ts"].dt.tz_localize(None).dt.normalize()).reset_index(drop=True)
    c = d["close"]
    d["sma50"], d["sma200"] = ind.sma(c, 50), ind.sma(c, 200)
    d["atr14"] = ind.atr(d["high"], d["low"], c)
    d["ret"] = np.log(c / c.shift(1))
    d = d.merge(preds, on="date", how="left")
    d["vol_pred"] = np.exp(d["vol_log"])
    d["vol_pct"] = (
        d["vol_pred"]
        .expanding(min_periods=60)
        .apply(lambda s: (s[:-1] < s[-1]).mean() if len(s) > 1 else np.nan, raw=True)
    )
    res = Result()
    cash, qty, stop, entry_px, entry_date, entry_cost = capital, 0, 0.0, 0.0, None, 0.0
    pending: str | None = None
    pending_reason, planned_qty = "", None
    first_valid = d.index[d["sma200"].notna() & d["p_up"].notna()]
    start = int(first_valid[0]) if len(first_valid) else len(d)
    bh_units = None

    def close_position(i, px, why):
        nonlocal cash, qty
        notional = qty * px
        cost = charges.costs(notional, "SELL", "DELIVERY")["total"]
        cash += notional - cost
        gross = qty * (px - entry_px)
        res.trades.append(
            {
                "entry_date": str(entry_date.date()),
                "exit_date": str(d.at[i, "date"].date()),
                "entry": entry_px,
                "exit": px,
                "qty": qty,
                "gross": gross,
                "costs": entry_cost + cost,
                "net": gross - entry_cost - cost,
                "return_pct": (px / entry_px - 1) * 100,
                "reason": why,
            }
        )
        qty = 0

    for i in range(start, len(d)):
        r = d.iloc[i]
        day = r["date"]
        executed = None
        # 1) fills for decisions taken at yesterday's close (at today's open)
        if pending == "BUY" and qty == 0:
            px = float(r["open"])
            stop_dist = P.stop_mult * max(
                float(d.at[i - 1, "atr14"]), float(d.at[i - 1, "vol_pred"] or 0) * float(d.at[i - 1, "close"])
            )
            n = int(cash // (px * 1.002))
            n = min(n, planned_qty) if planned_qty else n
            if n > 0:
                entry_cost = charges.costs(n * px, "BUY", "DELIVERY")["total"]
                cash -= n * px + entry_cost
                qty, entry_px, entry_date, stop = n, px, day, px - stop_dist
                executed = f"bought {n} @ {px:.2f}"
        elif pending == "SELL" and qty:
            close_position(i, float(r["open"]), pending_reason)
            executed = "sold at open"
        pending, planned_qty = None, None
        # 2) intraday stop-loss
        if qty and float(r["low"]) <= stop:
            close_position(i, min(float(r["open"]), stop), "stop-loss hit")
            executed = "stop-loss hit intraday"

        score = float(r["p_up"] - r["p_down"]) if pd.notna(r["p_up"]) else None
        uptrend = bool(r["close"] > r["sma200"] and r["sma50"] > r["sma200"]) if pd.notna(r["sma200"]) else False
        vol_pct = None if pd.isna(r["vol_pct"]) else float(r["vol_pct"])
        reasons: list[str] = []
        risk_view = None
        if qty:
            if float(r["close"]) < float(r["sma200"]):
                action, pending, pending_reason = "SELL", "SELL", "trend broken (close < SMA200)"
                reasons.append("Close fell below the 200-day average: trend exit.")
            elif score is not None and score <= P.exit_score:
                action, pending, pending_reason = "SELL", "SELL", "model turned bearish"
                reasons.append(f"Model turned clearly bearish (score {score:+.2f}).")
            else:
                action = "HOLD"
                reasons.append(f"In position; trend intact. Protective stop {stop:.2f}.")
        else:
            if executed == "stop-loss hit intraday":
                action = "SELL"
                reasons.append(f"Stop-loss hit intraday (stop {stop:.2f}).")
            elif not uptrend:
                action = "NO_TRADE"
                reasons.append("No uptrend (needs close > SMA200 and SMA50 > SMA200).")
            elif score is not None and score < P.min_score:
                action = "NO_TRADE"
                reasons.append(f"Uptrend, but the model is bearish (score {score:+.2f}).")
            elif vol_pct is not None and vol_pct >= P.max_vol_pct:
                action = "NO_TRADE"
                reasons.append(f"Uptrend, but forecast volatility is extreme ({vol_pct:.0%} percentile).")
            else:
                atr_eff = max(float(r["atr14"]), float(r["vol_pred"] or 0) * float(r["close"]))
                when = pd.Timestamp.combine(day, IST_CLOSE).tz_localize("Asia/Kolkata").to_pydatetime()
                conf = float(min(1.0, max(0.0, 0.55 + 0.5 * (score or 0.0))))
                intent = OrderIntent(
                    intent_id=f"lab-{instrument_key}-{day.date()}",
                    instrument_key=instrument_key,
                    sector=sector,
                    side="BUY",
                    product="DELIVERY",
                    entry_price=float(r["close"]),
                    stop_price=float(r["close"]) - P.stop_mult * atr_eff,
                    confidence=conf,
                    created_at=when,
                )
                snap = MarketSnapshot(
                    instrument_key=instrument_key, last_price=float(r["close"]), atr=atr_eff, data_ts=when
                )
                pf = PortfolioState(
                    equity=max(cash, 1.0), cash=cash, start_of_day_equity=max(cash, 1.0), peak_equity=max(cash, 1.0)
                )
                rets = pd.DataFrame({instrument_key: d.loc[:i, "ret"].dropna().tail(500).to_numpy()})
                v = risk.evaluate(intent, snap, pf, returns=rets if len(rets) >= 20 else None, now=when)
                risk_view = {
                    "approved": v.approved,
                    "quantity": v.quantity,
                    "stop": v.stop_price,
                    "target": v.take_profit,
                    "checks": [c.model_dump() for c in v.checks],
                    "reasons": v.reasons,
                }
                if v.approved:
                    action, pending, planned_qty = "BUY", "BUY", v.quantity
                    reasons.append(
                        f"Uptrend + model not bearish + volatility acceptable; risk approved {v.quantity} shares."
                    )
                else:
                    action = "NO_TRADE"
                    reasons.append("Signal present but the risk engine rejected it: " + "; ".join(v.reasons))

        if bh_units is None:
            bh_units = capital / float(r["close"])
        equity = cash + qty * float(r["close"])
        res.equity.append((str(day.date()), equity / capital, bh_units * float(r["close"]) / capital))
        res.days.append(
            {
                "date": str(day.date()),
                "open": float(r["open"]),
                "high": float(r["high"]),
                "low": float(r["low"]),
                "close": float(r["close"]),
                "volume": int(r["volume"]),
                "action": action,
                "position": qty,
                "executed": executed,
                "p_up": _f(r["p_up"]),
                "p_neutral": _f(r["p_neutral"]),
                "p_down": _f(r["p_down"]),
                "score": score,
                "vol_pred_daily": _f(r["vol_pred"]),
                "vol_pred_annual": _f(r["vol_pred"] * math.sqrt(252)) if pd.notna(r["vol_pred"]) else None,
                "vol_pct": vol_pct,
                "uptrend": uptrend,
                "sma50": _f(r["sma50"]),
                "sma200": _f(r["sma200"]),
                "atr14": _f(r["atr14"]),
                "stop": stop if qty else None,
                "reasons": reasons,
                "risk": risk_view,
            }
        )

    if qty:  # mark-to-market; keep the open position in the record
        res.trades.append(
            {
                "entry_date": str(entry_date.date()),
                "exit_date": None,
                "entry": entry_px,
                "exit": float(d["close"].iloc[-1]),
                "qty": qty,
                "gross": qty * (float(d["close"].iloc[-1]) - entry_px),
                "costs": entry_cost,
                "net": qty * (float(d["close"].iloc[-1]) - entry_px) - entry_cost,
                "return_pct": (float(d["close"].iloc[-1]) / entry_px - 1) * 100,
                "reason": "open",
            }
        )
    eq = pd.Series([e[1] for e in res.equity])
    bh = pd.Series([e[2] for e in res.equity])
    closed = [t for t in res.trades if t["exit_date"]]
    res.metrics = {
        "strategy": perf_stats(eq.pct_change().dropna(), 252, sum(t["costs"] for t in res.trades), len(res.trades)),
        "buy_and_hold": perf_stats(bh.pct_change().dropna(), 252),
        "closed_trades": len(closed),
        "win_rate_trades": float(np.mean([t["net"] > 0 for t in closed])) if closed else None,
        "exposure": float(np.mean([x["position"] > 0 for x in res.days])) if res.days else None,
        "period": [res.days[0]["date"], res.days[-1]["date"]] if res.days else None,
    }
    if res.days:
        last = res.days[-1]
        res.final = {**last, "next_session": _next_step(last)}
    return res


def _next_step(last: dict) -> str:
    a = last["action"]
    if a == "BUY":
        r = last["risk"] or {}
        return (
            f"Buy {r.get('quantity')} shares at the next open; stop-loss {r.get('stop')}, target {r.get('target')} "
            f"(risk-approved)."
        )
    if a == "SELL":
        return "Exit the position at the next open."
    if a == "HOLD":
        return f"Keep holding; protective stop at {last['stop']:.2f}."
    return "Stay in cash; no qualifying, risk-approved setup."


def _f(x) -> float | None:
    try:
        return None if x is None or pd.isna(x) else float(x)
    except (TypeError, ValueError):
        return None

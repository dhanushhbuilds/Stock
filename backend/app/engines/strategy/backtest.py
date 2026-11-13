"""Event-driven, long-only backtester with realistic execution:

- signals at bar t's close are executed at bar t+1's OPEN (no same-bar look-ahead);
- ATR stop-loss (2 x ATR at entry) checked on every bar's low; a gap through the stop fills at the open;
- intraday positions are flat by the 15:10 bar's close (before the closing-auction placeholders);
- full Indian charge schedule + slippage on every order; whole shares only.
"""

import math
from dataclasses import asdict, dataclass

import numpy as np
import pandas as pd

from app.engines.ml import indicators as ind
from app.engines.strategy.charges import ChargeSchedule
from app.engines.strategy.strategies import Strategy


@dataclass
class Trade:
    symbol: str
    entry_ts: pd.Timestamp
    exit_ts: pd.Timestamp
    entry_px: float
    exit_px: float
    qty: int
    gross: float
    costs: float
    net: float
    reason: str
    bars: int


def backtest_symbol(
    d: pd.DataFrame,
    strat: Strategy,
    symbol: str,
    capital: float,
    charges: ChargeSchedule,
    atr_mult: float = 2.0,
) -> tuple[list[Trade], pd.Series]:
    """d: one instrument's bars with ts, open, high, low, close, volume (+ date for intraday). Returns trades and
    a mark-to-market equity series (index = ts)."""
    product = "INTRADAY" if strat.timeframe == "5minute" else "DELIVERY"
    entry_sig, exit_sig = strat.fn(d)
    entry_sig, exit_sig = entry_sig.fillna(False).to_numpy(), exit_sig.fillna(False).to_numpy()
    o, h, lo, c = (d[k].to_numpy(float) for k in ("open", "high", "low", "close"))
    atr = ind.atr(d["high"], d["low"], d["close"]).to_numpy()
    ts = d["ts"].to_numpy()
    last_bar = (
        (d["ts"].dt.strftime("%H:%M") >= "15:10").to_numpy()
        if product == "INTRADAY"
        else np.zeros(len(d), bool)
    )
    day = d["date"].to_numpy() if product == "INTRADAY" else None

    cash, qty, stop, entry_px, entry_i, entry_cost = capital, 0, 0.0, 0.0, -1, 0.0
    pend_in = pend_out = False
    trades: list[Trade] = []
    equity = np.empty(len(d))

    def close_pos(i, px, reason):
        nonlocal cash, qty
        notional = qty * px
        cost = charges.costs(notional, "SELL", product)["total"]
        cash += notional - cost
        gross = qty * (px - entry_px)
        trades.append(
            Trade(
                symbol,
                pd.Timestamp(ts[entry_i]),
                pd.Timestamp(ts[i]),
                entry_px,
                px,
                qty,
                gross,
                entry_cost + cost,
                gross - entry_cost - cost,
                reason,
                i - entry_i,
            )
        )
        qty = 0

    for i in range(len(d)):
        new_day = product == "INTRADAY" and i > 0 and day[i] != day[i - 1]
        if new_day:
            pend_in = False  # intraday signals never carry overnight
        if qty:
            if pend_out:
                close_pos(i, o[i], "exit_signal")
            elif strat.max_hold and i - entry_i >= strat.max_hold:
                close_pos(i, o[i], "time_exit")
            elif lo[i] <= stop:
                close_pos(i, min(o[i], stop), "stop_loss")
            elif last_bar[i]:
                close_pos(i, c[i], "end_of_day")
        elif pend_in and not last_bar[i] and math.isfinite(atr[i - 1] if i else math.nan) and o[i] > 0:
            px = o[i]
            n = int(cash // (px * (1 + 0.002)))  # leave room for costs
            if n > 0:
                cost = charges.costs(n * px, "BUY", product)["total"]
                cash -= n * px + cost
                qty, entry_px, entry_i, entry_cost = n, px, i, cost
                stop = px - atr_mult * atr[i - 1]
                if lo[i] <= stop:  # stop hit on the entry bar itself
                    close_pos(i, stop, "stop_loss")
        pend_out = bool(exit_sig[i]) and qty > 0
        pend_in = bool(entry_sig[i]) and qty == 0 and not last_bar[i]
        equity[i] = cash + qty * c[i]
    if qty:
        close_pos(len(d) - 1, c[-1], "end_of_data")
        equity[-1] = cash
    return trades, pd.Series(equity, index=pd.DatetimeIndex(ts))


def trades_frame(trades: list[Trade]) -> pd.DataFrame:
    return pd.DataFrame([asdict(t) for t in trades])

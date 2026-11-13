"""Ten rule-based strategies with explicit entry/exit rules and fixed textbook parameters (not optimised).

Each daily strategy returns (entry, exit) boolean Series evaluated at the CLOSE of bar t; the backtester executes
at the NEXT bar's open. Every position also carries an ATR stop-loss enforced by the backtester.
"""

from collections.abc import Callable
from dataclasses import dataclass

import numpy as np
import pandas as pd

from app.engines.ml import indicators as ind


@dataclass(frozen=True)
class Strategy:
    name: str
    timeframe: str  # 1day | 5minute
    description: str
    fn: Callable[[pd.DataFrame], tuple[pd.Series, pd.Series]]
    max_hold: int | None = None  # bars
    params: dict | None = None


def _cross_up(a, b):
    return (a > b) & (a.shift(1) <= b.shift(1))


def ema_crossover(d):
    f, s = ind.ema(d["close"], 20), ind.ema(d["close"], 50)
    return _cross_up(f, s), _cross_up(s, f)


def macd_momentum(d):
    line, sig, _ = ind.macd(d["close"])
    return _cross_up(line, sig) & (line > 0), _cross_up(sig, line)


def rsi_mean_reversion(d):
    r, c = ind.rsi(d["close"], 14), d["close"]
    return (r < 30) & (c > ind.sma(c, 200)), r > 55


def bollinger_mean_reversion(d):
    c = d["close"]
    mid, sd = ind.sma(c, 20), c.rolling(20).std(ddof=0)
    return c < mid - 2 * sd, c > mid


def donchian_breakout(d):
    hi, lo = d["high"].rolling(20).max().shift(1), d["low"].rolling(10).min().shift(1)
    return d["close"] > hi, d["close"] < lo


def trend_following(d):
    c = d["close"]
    s50, s200 = ind.sma(c, 50), ind.sma(c, 200)
    cond = (c > s200) & (s50 > s200)
    return cond & ~cond.shift(1, fill_value=False), c < s200  # enter when the condition turns true


def atr_breakout(d):
    c = d["close"]
    a = ind.atr(d["high"], d["low"], c)
    return c > c.shift(1) + 1.5 * a.shift(1), pd.Series(False, index=d.index)


def relative_strength_momentum(d):
    """Needs 'rs_rank' (cross-sectional percentile of 120-day return, skip 5 days) added by the runner."""
    return d["rs_rank"] >= 0.8, d["rs_rank"] < 0.5


def vwap_trend(d):
    """5-minute: long when price reclaims session VWAP with above-average volume after 10:00."""
    day = d["date"]
    tp = (d["high"] + d["low"] + d["close"]) / 3
    vwap = (tp * d["volume"]).groupby(day).cumsum() / d["volume"].groupby(day).cumsum().replace(0, np.nan)
    hm = d["ts"].dt.strftime("%H:%M")
    rel_vol = d["volume"] / d["volume"].rolling(12).mean()
    return _cross_up(d["close"], vwap) & (hm >= "10:00") & (hm <= "14:30") & (rel_vol > 1.2), d[
        "close"
    ] < vwap


def opening_range_breakout(d):
    """5-minute: long on a close above the 09:15-09:40 range high, from 09:45 to 13:00; exit below range low."""
    day, hm = d["date"], d["ts"].dt.strftime("%H:%M")
    first = hm <= "09:40"
    orh = d["high"].where(first).groupby(day).transform("max")
    orl = d["low"].where(first).groupby(day).transform("min")
    window = (hm >= "09:45") & (hm <= "13:00")
    return _cross_up(d["close"], orh) & window, d["close"] < orl


STRATEGIES: dict[str, Strategy] = {
    s.name: s
    for s in [
        Strategy(
            "ema_crossover",
            "1day",
            "Long when EMA20 crosses above EMA50; exit on cross below.",
            ema_crossover,
        ),
        Strategy(
            "macd_momentum",
            "1day",
            "Long when MACD crosses its signal above zero; exit on cross below.",
            macd_momentum,
        ),
        Strategy(
            "rsi_mean_reversion",
            "1day",
            "Long when RSI14 < 30 in a long-term uptrend (close > SMA200); exit RSI > 55.",
            rsi_mean_reversion,
            max_hold=20,
        ),
        Strategy(
            "bollinger_mean_reversion",
            "1day",
            "Long below the lower 20/2 Bollinger band; exit at the middle band.",
            bollinger_mean_reversion,
            max_hold=20,
        ),
        Strategy(
            "donchian_breakout",
            "1day",
            "Long on a close above the prior 20-day high; exit below the prior 10-day low.",
            donchian_breakout,
        ),
        Strategy(
            "trend_following",
            "1day",
            "Long when close > SMA200 and SMA50 > SMA200; exit when close < SMA200.",
            trend_following,
        ),
        Strategy(
            "atr_breakout",
            "1day",
            "Long when close exceeds previous close by 1.5 ATR; time exit after 10 days.",
            atr_breakout,
            max_hold=10,
        ),
        Strategy(
            "relative_strength_momentum",
            "1day",
            "Long stocks in the top 20% of 120-day return (skip 5 days); exit below the median.",
            relative_strength_momentum,
        ),
        Strategy(
            "vwap_trend",
            "5minute",
            "Intraday: long on VWAP reclaim with volume; exit below VWAP; flat by 15:10.",
            vwap_trend,
        ),
        Strategy(
            "opening_range_breakout",
            "5minute",
            "Intraday: long above the 30-min opening range high; exit below range low; flat by 15:10.",
            opening_range_breakout,
        ),
    ]
}

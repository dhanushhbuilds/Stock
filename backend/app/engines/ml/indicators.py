"""Technical indicators. All are causal: the value at row t uses rows <= t only.

Conventions follow the original definitions: Wilder smoothing (alpha = 1/n) for RSI and ATR,
span-based EMA (alpha = 2/(n+1)) for EMA/MACD.
"""

import numpy as np
import pandas as pd


def ema(x: pd.Series, n: int) -> pd.Series:
    return x.ewm(span=n, adjust=False, min_periods=n).mean()


def sma(x: pd.Series, n: int) -> pd.Series:
    return x.rolling(n, min_periods=n).mean()


def wilder(x: pd.Series, n: int) -> pd.Series:
    return x.ewm(alpha=1.0 / n, adjust=False, min_periods=n).mean()


def rsi(close: pd.Series, n: int = 14) -> pd.Series:
    d = close.diff()
    up = wilder(d.clip(lower=0), n)
    dn = wilder((-d).clip(lower=0), n)
    rs = up / dn
    out = 100 - 100 / (1 + rs)
    return out.where(dn != 0, 100.0).where(up.notna())


def true_range(high: pd.Series, low: pd.Series, close: pd.Series) -> pd.Series:
    pc = close.shift(1)
    return (
        pd.concat([high - low, (high - pc).abs(), (low - pc).abs()], axis=1)
        .max(axis=1, skipna=False)
        .fillna(high - low)
    )


def atr(high: pd.Series, low: pd.Series, close: pd.Series, n: int = 14) -> pd.Series:
    return wilder(true_range(high, low, close), n)


def macd(
    close: pd.Series, fast: int = 12, slow: int = 26, signal: int = 9
) -> tuple[pd.Series, pd.Series, pd.Series]:
    line = ema(close, fast) - ema(close, slow)
    sig = line.ewm(span=signal, adjust=False, min_periods=signal).mean()
    return line, sig, line - sig


def stochastic(
    high: pd.Series, low: pd.Series, close: pd.Series, n: int = 14, d: int = 3
) -> tuple[pd.Series, pd.Series]:
    hh = high.rolling(n, min_periods=n).max()
    ll = low.rolling(n, min_periods=n).min()
    k = 100 * (close - ll) / (hh - ll).replace(0, np.nan)
    return k, k.rolling(d, min_periods=d).mean()


def bollinger(close: pd.Series, n: int = 20, k: float = 2.0) -> tuple[pd.Series, pd.Series]:
    """Returns (%B, bandwidth). Population std (ddof=0) as in Bollinger's definition."""
    mid = sma(close, n)
    sd = close.rolling(n, min_periods=n).std(ddof=0)
    upper, lower = mid + k * sd, mid - k * sd
    pct_b = (close - lower) / (upper - lower).replace(0, np.nan)
    return pct_b, (upper - lower) / mid


def roc(close: pd.Series, n: int) -> pd.Series:
    return close / close.shift(n) - 1


def log_ret(close: pd.Series, n: int = 1) -> pd.Series:
    return np.log(close / close.shift(n))


def realized_vol(close: pd.Series, n: int) -> pd.Series:
    return log_ret(close).rolling(n, min_periods=n).std()

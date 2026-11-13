"""Volatility-adjusted, cost-aware 3-class labels (slide 8 of the Review-1 deck).

R(t,h) = P(t+h)/P(t) - 1;  tau = max(c * sigma_t * sqrt(h), cost)
UP if R > tau, DOWN if R < -tau, otherwise NEUTRAL.
sigma_t is estimated from returns up to and including t only.
"""

import numpy as np
import pandas as pd

DOWN, NEUTRAL, UP = 0, 1, 2
CLASS_NAMES = ["DOWN", "NEUTRAL", "UP"]


def make_labels(close: pd.Series, sigma: pd.Series, h: int, c: float, cost: float) -> pd.DataFrame:
    fwd = close.shift(-h) / close - 1
    tau = np.maximum(c * sigma * np.sqrt(h), cost)
    y = pd.Series(NEUTRAL, index=close.index, dtype="float64")
    y[fwd > tau] = UP
    y[fwd < -tau] = DOWN
    y[fwd.isna() | tau.isna()] = np.nan
    return pd.DataFrame({"fwd_ret": fwd, "tau": tau, "y": y})

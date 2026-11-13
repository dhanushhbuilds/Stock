"""Portfolio risk measures: historical / parametric VaR, CVaR (expected shortfall), stress tests."""

import math

import numpy as np
import pandas as pd

Z = {0.90: 1.2815515655, 0.95: 1.6448536270, 0.975: 1.9599639845, 0.99: 2.3263478740}


def historical_var(pnl: np.ndarray, confidence: float = 0.95) -> float:
    """Loss threshold not exceeded with probability `confidence` (returned as a positive number)."""
    pnl = np.asarray(pnl, dtype=float)
    pnl = pnl[np.isfinite(pnl)]
    if len(pnl) < 20:
        raise ValueError("need at least 20 observations for historical VaR")
    return float(max(-np.quantile(pnl, 1 - confidence, method="lower"), 0.0))


def historical_cvar(pnl: np.ndarray, confidence: float = 0.95) -> float:
    """Expected loss given the loss is at least the VaR (expected shortfall), positive number."""
    pnl = np.asarray(pnl, dtype=float)
    pnl = pnl[np.isfinite(pnl)]
    cut = np.quantile(pnl, 1 - confidence, method="lower")
    tail = pnl[pnl <= cut]
    return float(max(-tail.mean(), 0.0))


def parametric_var(value: float, sigma: float, confidence: float = 0.95, horizon_days: int = 1) -> float:
    z = Z.get(confidence)
    if z is None:
        from statistics import NormalDist

        z = NormalDist().inv_cdf(confidence)
    return float(abs(value) * sigma * z * math.sqrt(horizon_days))


def portfolio_pnl_series(weights_value: dict[str, float], returns: pd.DataFrame) -> np.ndarray:
    """Hypothetical daily P&L of the current holdings replayed over historical returns (full revaluation)."""
    cols = [k for k in weights_value if k in returns.columns]
    missing = set(weights_value) - set(cols)
    if missing:
        raise ValueError(f"no return history for {sorted(missing)}")
    r = returns[cols].dropna()
    v = np.array([weights_value[c] for c in cols])
    return r.to_numpy() @ v


def avg_correlation(
    candidate: str, holdings: list[str], returns: pd.DataFrame, lookback: int = 60
) -> float | None:
    others = [h for h in holdings if h != candidate and h in returns.columns]
    if not others or candidate not in returns.columns:
        return None
    r = returns[[candidate, *others]].dropna().tail(lookback)
    if len(r) < 20:
        return None
    return float(r.corr().loc[candidate, others].mean())


STRESS_SCENARIOS = {
    # Market move applied through each position's beta, plus optional sector-specific shocks.
    "nifty_-5pct_day": {"market": -0.05},
    "covid_2020_03_23_like": {"market": -0.13},  # NIFTY 50 fell ~13% on 23 Mar 2020
    "nifty_+5pct_day": {"market": 0.05},
    "financials_-10pct": {"market": -0.03, "sectors": {"NSE_INDEX|Nifty Fin Service": -0.10}},
    "it_-10pct": {"market": -0.02, "sectors": {"NSE_INDEX|Nifty IT": -0.10}},
}


def stress_test(positions: list[dict], scenarios: dict | None = None) -> dict[str, float]:
    """positions: {value, beta, sector}. Sector shocks replace the beta-scaled market move for that sector."""
    out = {}
    for name, sc in (scenarios or STRESS_SCENARIOS).items():
        pnl = 0.0
        for p in positions:
            shock = sc.get("sectors", {}).get(p.get("sector"))
            move = shock if shock is not None else p.get("beta", 1.0) * sc["market"]
            pnl += p["value"] * move
        out[name] = float(pnl)
    return out

"""Volatility forecasting: target uses only the NEXT h returns; metrics are correct."""

import numpy as np
import pandas as pd
import pytest

from app.engines.ml.volatility import EPS, add_target, metrics


def _ds():
    rng = np.random.default_rng(0)
    rows = []
    for s in ("A", "B"):
        c = 100 * np.exp(np.cumsum(rng.normal(0, 0.02, 120)))
        rows.append(pd.DataFrame({"date": pd.bdate_range("2024-01-01", periods=120), "symbol": s, "close": c,
                                  "vol20": 0.02, "vol60": 0.02}))
    return pd.concat(rows, ignore_index=True)


def test_target_is_forward_rms_of_next_h_returns():
    ds = add_target(_ds(), h=5)
    a = ds[ds["symbol"] == "A"].reset_index(drop=True)
    r = np.log(a["close"] / a["close"].shift(1))
    i = 50
    expect = np.sqrt(np.mean(r.iloc[i + 1:i + 6] ** 2))
    assert a.loc[i, "rv_next"] == pytest.approx(expect)
    assert a.loc[i, "y_vol"] == pytest.approx(np.log(expect + EPS))
    assert a["y_vol"].tail(5).isna().all()  # no future -> no label


def test_target_does_not_leak_across_symbols_or_from_past():
    ds = add_target(_ds(), h=5)
    a = ds[ds["symbol"] == "A"].reset_index(drop=True)
    assert np.isnan(a["y_vol"].iloc[-1])  # last A row must not borrow B's returns
    changed = _ds()
    changed.loc[changed["symbol"] == "A", "close"] = changed.loc[changed["symbol"] == "A", "close"].to_numpy() * np.r_[
        np.ones(40), np.full(80, 2.0)]  # a jump at row 40 only affects labels whose window includes it
    b = add_target(changed, h=5)
    b = b[b["symbol"] == "A"].reset_index(drop=True)
    assert np.allclose(a["y_vol"].iloc[:34], b["y_vol"].iloc[:34], equal_nan=True)
    assert not np.isclose(a["y_vol"].iloc[35], b["y_vol"].iloc[35])


def test_metrics_reference_values():
    y = np.log(np.array([0.01, 0.02, 0.03, 0.015, 0.025]))
    perfect = metrics(y, y)
    assert perfect["r2_log"] == pytest.approx(1.0) and perfect["rmse_log"] == 0 and perfect["qlike"] == pytest.approx(0)
    mean = metrics(y, np.full_like(y, y.mean()))
    assert mean["r2_log"] == pytest.approx(0.0, abs=1e-12)
    worse = metrics(y, y[::-1])
    assert worse["r2_log"] < 0 and worse["rmse_log"] > 0

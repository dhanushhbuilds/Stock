"""Phase 3 tests: indicator correctness vs independent loop implementations, label rules, and leakage checks."""

from datetime import date

import numpy as np
import pandas as pd
import pytest

from app.engines.data.candles import parse_candles
from app.engines.data.storage import CandleLake, aggregate
from app.engines.ml import indicators as ind
from app.engines.ml.intraday import IntradayConfig, bar_features, build_intraday_dataset
from app.engines.ml.labels import DOWN, NEUTRAL, UP, make_labels
from app.engines.ml.splits import holdout_fold, masks, walk_forward
from app.engines.ml.swing import SwingConfig, build_swing_dataset, global_features, price_features
from tests.fixtures.upstox_fake import daily_candle, minute_candles, trading_days

RNG = np.random.default_rng(7)


def _series(n=300):
    c = pd.Series(100 * np.exp(np.cumsum(RNG.normal(0, 0.01, n))))
    h = c * (1 + RNG.uniform(0, 0.01, n))
    lo = c * (1 - RNG.uniform(0, 0.01, n))
    return h, lo, c


# ---------- indicators vs straightforward loop implementations ----------


def ref_ema(x, n):
    a, out, s = 2 / (n + 1), [], None
    for i, v in enumerate(x):
        s = v if s is None else a * v + (1 - a) * s
        out.append(s if i >= n - 1 else np.nan)
    return np.array(out)


def ref_rsi(c, n=14):
    out = [np.nan] * len(c)
    gains = [max(c[i] - c[i - 1], 0) for i in range(1, len(c))]
    losses = [max(c[i - 1] - c[i], 0) for i in range(1, len(c))]
    ag, al = gains[0], losses[0]
    for i in range(1, len(gains)):
        ag = ag + (gains[i] - ag) / n
        al = al + (losses[i] - al) / n
        if i >= n - 1:
            out[i + 1] = 100 - 100 / (1 + ag / al) if al > 0 else 100.0
    return np.array(out)


def ref_atr(h, lo, c, n=14):
    tr = [h[0] - lo[0]] + [
        max(h[i] - lo[i], abs(h[i] - c[i - 1]), abs(lo[i] - c[i - 1])) for i in range(1, len(c))
    ]
    out, s = [], None
    for i, v in enumerate(tr):
        s = v if s is None else s + (v - s) / n
        out.append(s if i >= n - 1 else np.nan)
    return np.array(out)


def test_ema_matches_loop():
    _, _, c = _series()
    np.testing.assert_allclose(
        ind.ema(c, 20).to_numpy(), ref_ema(c.to_numpy(), 20), rtol=1e-12, equal_nan=True
    )


def test_rsi_matches_wilder_loop():
    _, _, c = _series()
    np.testing.assert_allclose(ind.rsi(c, 14).to_numpy(), ref_rsi(c.to_numpy()), rtol=1e-10, equal_nan=True)


def test_atr_matches_wilder_loop():
    h, lo, c = _series()
    np.testing.assert_allclose(
        ind.atr(h, lo, c).to_numpy(),
        ref_atr(h.to_numpy(), lo.to_numpy(), c.to_numpy()),
        rtol=1e-10,
        equal_nan=True,
    )


def test_macd_is_ema_difference():
    _, _, c = _series()
    line, sig, hist = ind.macd(c)
    np.testing.assert_allclose(line, ind.ema(c, 12) - ind.ema(c, 26), equal_nan=True)
    np.testing.assert_allclose(hist, line - sig, equal_nan=True)


def test_bollinger_and_stochastic_reference_values():
    c = pd.Series([float(x) for x in range(1, 21)])
    pctb, width = ind.bollinger(c, 20, 2)
    sd = np.std(np.arange(1, 21))  # population std
    assert pctb.iloc[-1] == pytest.approx((20 - (10.5 - 2 * sd)) / (4 * sd))
    assert width.iloc[-1] == pytest.approx(4 * sd / 10.5)
    k, _ = ind.stochastic(c + 0.5, c - 0.5, c, 14)
    assert k.iloc[-1] == pytest.approx(100 * (20 - 6.5) / (20.5 - 6.5))


def test_rsi_extremes():
    up = pd.Series(np.arange(1.0, 40.0))
    assert ind.rsi(up, 14).iloc[-1] == 100.0
    assert ind.rsi(up[::-1].reset_index(drop=True), 14).iloc[-1] == pytest.approx(0.0)


# ---------- labels ----------


def test_labels_threshold_and_cost_floor():
    close = pd.Series([100.0, 101.0, 100.0, 99.0, 100.0, 100.05])
    sigma = pd.Series([0.004] * 6)
    lab = make_labels(close, sigma, h=1, c=1.0, cost=0.001)
    # tau = max(1 * 0.004 * 1, 0.001) = 0.004
    assert lab["y"].tolist()[:5] == [UP, DOWN, DOWN, UP, NEUTRAL]
    assert np.isnan(lab["y"].iloc[-1])  # no future -> no label, never guessed
    lab2 = make_labels(close, pd.Series([0.0001] * 6), h=1, c=1.0, cost=0.02)
    assert set(lab2["y"].dropna()) == {NEUTRAL}  # moves smaller than costs are NEUTRAL


# ---------- splits ----------


def test_walk_forward_is_chronological_and_purged():
    dates = pd.bdate_range("2019-01-01", "2023-12-31")
    folds = walk_forward(dates, "2021-01-01", "2023-07-01", 6, purge=5)
    assert len(folds) == 5
    u = pd.DatetimeIndex(dates)
    for f in folds:
        assert f.fit_end < f.val_start <= f.val_end < f.test_start <= f.test_end
        # at least `purge` sessions between fit and val, and between val and test
        assert ((u > f.fit_end) & (u < f.val_start)).sum() == 5
        assert ((u > f.val_end) & (u < f.test_start)).sum() == 5
    for a, b in zip(folds, folds[1:], strict=False):
        assert b.test_start > a.test_end  # non-overlapping test windows
    assert folds[-1].test_end < pd.Timestamp("2023-07-01")
    h = holdout_fold(dates, "2023-07-01", purge=5)
    assert h.test_start >= pd.Timestamp("2023-07-01") and h.val_end < h.test_start


def test_masks_never_share_rows():
    d = pd.Series(pd.bdate_range("2020-01-01", "2022-12-31"))
    f = walk_forward(d, "2022-01-01", "2022-12-01", 3, purge=5)[0]
    fit, val, test = masks(d, f)
    assert not (fit & val).any() and not (fit & test).any() and not (val & test).any()


# ---------- leakage: features at t must not change when the future is deleted ----------


def _lake_with_fixture(tmp_path, days, keys, minute_from=date(2024, 1, 1), cut_ts: str | None = None):
    """cut_ts: simulate 'now' mid-session: drop every minute bar at/after it and the daily bar of that day."""
    lake = CandleLake(tmp_path)
    for i, k in enumerate(keys):
        dd = [d for d in days if cut_ts is None or d < pd.Timestamp(cut_ts).date()]
        lake.write(parse_candles([daily_candle(d, base=1000 + 50 * i) for d in dd]), "1day", k)
        m1 = parse_candles(
            [c for d in days if d >= minute_from for c in minute_candles(d, base=1000 + 50 * i)]
        )
        if cut_ts is not None:
            m1 = m1[m1["ts"] < pd.Timestamp(cut_ts, tz="Asia/Kolkata")]
        m5 = aggregate(m1, 5)
        lake.write(m5, "5minute", k)
    return lake


KEYS = ["NSE_INDEX|Nifty 50", "NSE_INDEX|India VIX", "NSE_EQ|A", "NSE_EQ|B", "NSE_INDEX|SECT"]
MEMBERS = [("A", "NSE_EQ|A", "NSE_INDEX|SECT"), ("B", "NSE_EQ|B", "NSE_INDEX|SECT")]


def test_swing_features_do_not_use_future(tmp_path):
    days = trading_days(date(2023, 1, 2), date(2024, 1, 31))
    full = build_swing_dataset(
        _lake_with_fixture(tmp_path / "full", days, KEYS),
        MEMBERS,
        None,
        SwingConfig(start="2023-01-01", min_history=60, label_mode="absolute"),
    )
    cut = days[-15]
    trunc = build_swing_dataset(
        _lake_with_fixture(tmp_path / "cut", [d for d in days if d <= cut], KEYS),
        MEMBERS,
        None,
        SwingConfig(start="2023-01-01", min_history=60, label_mode="absolute"),
    )
    from app.engines.ml.swing import feature_columns

    fc = [c for c in feature_columns(full) if not c.startswith("xs_rank")]
    a = full[full["date"] <= pd.Timestamp(cut)].set_index(["date", "symbol"])[fc].sort_index()
    b = trunc.set_index(["date", "symbol"])[fc].sort_index()
    pd.testing.assert_frame_equal(a, b, check_dtype=False)
    # ...whereas labels near the cut DO depend on the future (they must, and are never inputs)
    assert trunc[trunc["date"] == pd.Timestamp(cut)]["y"].isna().all()
    assert "y" not in fc and "fwd_ret" not in fc and "tau" not in fc


def test_intraday_features_do_not_use_future(tmp_path):
    days = trading_days(date(2024, 1, 1), date(2024, 3, 29))
    cfg = IntradayConfig(start="2024-01-01")
    full = build_intraday_dataset(_lake_with_fixture(tmp_path / "f", days, KEYS), MEMBERS[:1], None, cfg)
    cut = pd.Timestamp(f"{days[-5]} 12:00")  # "now" = noon, mid-session
    trunc = build_intraday_dataset(
        _lake_with_fixture(tmp_path / "c", days, KEYS, cut_ts=str(cut)), MEMBERS[:1], None, cfg
    )
    from app.engines.ml.intraday import feature_columns

    fc = [c for c in feature_columns(full) if not c.startswith("xs_rank")]
    # Every decision whose bar closed by noon (bar start <= 11:55) must have identical features.
    a = full[full["ts"] <= cut - pd.Timedelta(minutes=5)].set_index("ts")[fc].sort_index()
    b = trunc[trunc["ts"] <= cut - pd.Timedelta(minutes=5)].set_index("ts")[fc].sort_index()
    assert len(a) > 500 and a.index.max().date() == days[-5]
    pd.testing.assert_frame_equal(a, b, check_dtype=False)


def test_intraday_label_is_exactly_30_minutes_ahead_same_session(tmp_path):
    days = trading_days(date(2024, 2, 1), date(2024, 3, 15))
    lake = _lake_with_fixture(tmp_path, days, KEYS)
    ds = build_intraday_dataset(lake, MEMBERS[:1], None, IntradayConfig(start="2024-02-01"))
    bars = lake.read("5minute", "NSE_EQ|A").assign(ts=lambda d: d["ts"].dt.tz_localize(None)).set_index("ts")
    row = ds.dropna(subset=["fwd_ret"]).iloc[100]
    expect = bars.loc[row["ts"] + pd.Timedelta(minutes=30), "close"] / bars.loc[row["ts"], "close"] - 1
    assert row["fwd_ret"] == pytest.approx(expect)
    hm = ds["ts"].dt.strftime("%H:%M")
    assert hm.min() == "09:40" and hm.max() == "14:40"  # label ends by 15:15: never in auction placeholders


def test_global_features_strictly_before_session_date():
    g = pd.DataFrame(
        {
            c: np.arange(1, 11, dtype=float)
            for c in ("SPX", "NDX", "N225", "HSI", "BRENT", "USDINR", "USVIX", "US10Y")
        },
        index=pd.date_range("2024-01-01", periods=10),
    )
    out = global_features(g, pd.DatetimeIndex(["2024-01-05", "2024-01-20"]))
    assert out.loc["2024-01-05", "g_usvix"] == 4.0  # value dated 01-04, not 01-05
    assert out.loc["2024-01-05", "g_age_days"] == 1
    assert out.loc["2024-01-20", "g_usvix"] == 10.0 and out.loc["2024-01-20", "g_age_days"] == 10


def test_price_features_handle_missing_volume_and_gaps():
    days = trading_days(date(2023, 1, 2), date(2023, 12, 29))
    df = parse_candles([daily_candle(d) for d in days])
    df = (
        df.assign(date=df["ts"].dt.tz_localize(None))
        .set_index("date")
        .drop(index=df["ts"].dt.tz_localize(None)[50])
    )
    f = price_features(df.assign(volume=0))  # e.g. an index
    assert "rel_vol20" not in f.columns and len(f) == len(days) - 1
    assert np.isfinite(f["rsi14"].dropna()).all()


def test_bar_features_vwap_resets_each_session():
    days = trading_days(date(2024, 2, 5), date(2024, 2, 6))
    m5 = aggregate(parse_candles([c for d in days for c in minute_candles(d)]), 5)
    m5 = m5.assign(ts=m5["ts"].dt.tz_localize(None))
    m5["date"] = m5["ts"].dt.normalize()
    f = bar_features(m5)
    first = m5.groupby("date").head(1).index
    tp = (m5["high"] + m5["low"] + m5["close"]) / 3
    np.testing.assert_allclose(f.loc[first, "vwap_dist"], (m5["close"] / tp - 1)[first], rtol=1e-6)


def test_intraday_drops_special_sessions_causally(tmp_path):
    days = trading_days(date(2024, 1, 1), date(2024, 2, 9))
    lake = _lake_with_fixture(tmp_path, days, KEYS)
    # add an evening-only "Muhurat" session on a weekday and a Saturday session
    muhurat = parse_candles([r[:1] + r[1:] for r in minute_candles(date(2024, 2, 12))])
    muhurat = muhurat.assign(ts=muhurat["ts"] + pd.Timedelta(hours=4, minutes=30)).head(60)  # 13:45 start
    sat = parse_candles(minute_candles(date(2024, 2, 10)))
    for k in ("NSE_EQ|A", "NSE_INDEX|Nifty 50"):
        lake.write(aggregate(muhurat, 5), "5minute", k)
        lake.write(aggregate(sat, 5), "5minute", k)
    ds = build_intraday_dataset(lake, MEMBERS[:1], None, IntradayConfig(start="2024-01-01"))
    assert pd.Timestamp("2024-02-12") not in set(ds["date"]) and pd.Timestamp("2024-02-10") not in set(
        ds["date"]
    )


def test_torch_and_lightgbm_coexist_in_one_process():
    """Regression for the OpenMP import-order segfault: runs in a fresh interpreter via the ml package."""
    import subprocess
    import sys

    code = (
        "import app.engines.ml, lightgbm, torch; "
        "x=torch.zeros(8,5,4); print(torch.nn.LSTM(4,8,batch_first=True)(x)[0].shape)"
    )
    r = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, timeout=120)
    assert r.returncode == 0, r.stderr[-500:]


def test_torch_mode_process_never_loads_tree_libraries_and_trains_lstm():
    """Regression: LSTM/GRU training segfaults once xgboost's OpenMP runtime is loaded first (2026-11-13)."""
    import os
    import subprocess
    import sys

    code = (
        "import sys, app.engines.ml, app.engines.ml.trainer, torch\n"
        "assert 'xgboost' not in sys.modules and 'lightgbm' not in sys.modules\n"
        "m = torch.nn.LSTM(4, 8, batch_first=True); opt = torch.optim.Adam(m.parameters())\n"
        "for _ in range(3):\n"
        "    opt.zero_grad(); m(torch.randn(16, 5, 4))[0].sum().backward(); opt.step()\n"
        "print('ok')"
    )
    r = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, timeout=120,
                       env={**os.environ, "AQ_ML_MODE": "torch"})
    assert r.returncode == 0 and r.stdout.strip().endswith("ok"), r.stderr[-500:]

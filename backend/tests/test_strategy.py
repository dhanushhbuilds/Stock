"""Strategy engine: execution timing, stops, intraday flat rule, charges, signal rules, reproducibility."""

import numpy as np
import pandas as pd
import pytest

from app.engines.strategy.backtest import backtest_symbol
from app.engines.strategy.charges import ChargeSchedule
from app.engines.strategy.strategies import STRATEGIES, Strategy

NO_COST = ChargeSchedule(
    brokerage_per_order=0,
    intraday_brokerage_pct_cap=0,
    exchange_pct=0,
    sebi_pct=0,
    gst_pct=0,
    stt_delivery_pct=0,
    stt_intraday_sell_pct=0,
    stamp_delivery_buy_pct=0,
    stamp_intraday_buy_pct=0,
    dp_charge_per_sell=0,
    slippage_pct=0,
)


def bars(closes, opens=None, lows=None, highs=None, start="2024-01-01", freq="B"):
    c = np.asarray(closes, float)
    o = np.asarray(opens if opens is not None else c, float)
    lo = np.asarray(lows if lows is not None else np.minimum(o, c) - 0.5, float)
    hi = np.asarray(highs if highs is not None else np.maximum(o, c) + 0.5, float)
    ts = pd.date_range(start, periods=len(c), freq=freq)
    return pd.DataFrame({"ts": ts, "open": o, "high": hi, "low": lo, "close": c, "volume": 1000})


def scripted(entries, exits, timeframe="1day", max_hold=None):
    def fn(d):
        e = pd.Series(False, index=d.index)
        x = pd.Series(False, index=d.index)
        e.iloc[entries] = True
        x.iloc[exits] = True
        return e, x

    return Strategy("scripted", timeframe, "test", fn, max_hold=max_hold)


def test_signal_at_close_executes_next_open():
    closes = [100] * 20 + [101, 102, 103, 104, 105]
    opens = [100] * 20 + [100.5, 101.5, 102.5, 103.5, 104.5]
    d = bars(closes, opens)
    trades, eq = backtest_symbol(d, scripted([20], [22]), "X", 10_000, NO_COST)
    (t,) = trades
    assert t.entry_ts == d["ts"][21] and t.entry_px == 101.5  # signal on bar 20 -> open of bar 21
    assert t.exit_ts == d["ts"][23] and t.exit_px == 103.5 and t.reason == "exit_signal"
    assert t.qty == int(10_000 // (101.5 * 1.002))
    assert eq.iloc[-1] == pytest.approx(10_000 + t.net)


def test_stop_loss_and_gap_through_stop():
    closes = [100.0] * 20 + [100, 99, 90, 90]
    d = bars(closes)  # ATR ~ 1.0 -> stop ~ 98
    trades, _ = backtest_symbol(d, scripted([20], []), "X", 10_000, NO_COST)
    t = trades[0]
    assert t.reason == "stop_loss" and t.exit_px < t.entry_px
    gap = bars(closes, opens=[100.0] * 22 + [90, 90])  # opens far below the stop
    t2 = backtest_symbol(gap, scripted([20], []), "X", 10_000, NO_COST)[0][0]
    assert t2.reason == "stop_loss" and t2.exit_px == 90  # filled at the gap open, not the stop price


def test_time_exit():
    d = bars(np.linspace(100, 110, 40))
    t = backtest_symbol(d, scripted([20], [], max_hold=5), "X", 10_000, NO_COST)[0][0]
    assert t.reason == "time_exit" and t.bars == 5


def test_intraday_flat_by_1510_and_no_overnight_signal():
    ts = pd.date_range("2024-02-05 09:15", "2024-02-05 15:10", freq="5min").append(
        pd.date_range("2024-02-06 09:15", "2024-02-06 15:10", freq="5min")
    )
    d = pd.DataFrame({"ts": ts, "open": 100.0, "high": 100.5, "low": 99.5, "close": 100.0, "volume": 1000})
    d["date"] = d["ts"].dt.normalize()
    n = len(ts) // 2
    trades, _ = backtest_symbol(d, scripted([30, n - 1], [], timeframe="5minute"), "X", 100_000, NO_COST)
    assert len(trades) == 1  # the signal on the day's last bar does not open a position next morning
    assert trades[0].reason == "end_of_day" and pd.Timestamp(trades[0].exit_ts).strftime("%H:%M") == "15:10"


def test_costs_deducted_and_schedule_values():
    ch = ChargeSchedule()
    buy = ch.costs(100_000, "BUY", "DELIVERY")
    assert buy["stt"] == pytest.approx(100) and buy["stamp"] == pytest.approx(15) and buy["brokerage"] == 20
    assert buy["gst"] == pytest.approx(0.18 * (20 + 3.22 + 0.1))
    sell_i = ch.costs(100_000, "SELL", "INTRADAY")
    assert sell_i["stt"] == pytest.approx(25) and sell_i["stamp"] == 0 and sell_i["dp"] == 0
    assert ch.costs(5_000, "BUY", "INTRADAY")["brokerage"] == pytest.approx(5)  # 0.1% cap below Rs 20
    d = bars([100] * 20 + [101] * 5)
    t = backtest_symbol(d, scripted([20], [22]), "X", 100_000, ch)[0][0]
    assert t.costs > 0 and t.net == pytest.approx(t.gross - t.costs)
    # Hand-computed on a Rs 20,000 delivery round trip: buy 57.384 + sell 77.984 (incl. Rs 23.6 DP) = 135.368
    assert ch.round_trip_pct(20_000, "DELIVERY") == pytest.approx(135.368 / 20_000, rel=1e-4)
    # Fixed fees make small positions expensive: Rs 20k costs ~0.68% vs ~0.39% on Rs 1 lakh
    assert ch.round_trip_pct(20_000, "DELIVERY") > ch.round_trip_pct(100_000, "DELIVERY") > 0.0035


def test_strategy_rules_on_constructed_series():
    up = bars(list(np.linspace(100, 80, 60)) + list(np.linspace(80, 130, 60)))
    e, x = STRATEGIES["ema_crossover"].fn(up)
    assert e.sum() == 1 and e.idxmax() > 60  # one golden cross, after the turn
    d = bars([100] * 25 + [110])
    e, _ = STRATEGIES["donchian_breakout"].fn(d)
    assert bool(e.iloc[-1]) and not e.iloc[:-1].any()
    dn = bars(list(np.linspace(50, 100, 220)) + [100, 95, 90, 86, 83, 80, 78, 76])
    e, _ = STRATEGIES["rsi_mean_reversion"].fn(dn)
    assert e.iloc[-3:].any()  # oversold inside a long-term uptrend


def test_signals_never_use_future_bars():
    rng = np.random.default_rng(0)
    d = bars(100 * np.exp(np.cumsum(rng.normal(0, 0.01, 400))))
    d["rs_rank"] = rng.uniform(size=len(d))
    for name, st in STRATEGIES.items():
        if st.timeframe != "1day":
            continue
        e_full, x_full = st.fn(d)
        e_cut, x_cut = st.fn(d.iloc[:300].copy())
        pd.testing.assert_series_equal(
            e_full.iloc[:300].fillna(False), e_cut.fillna(False), check_names=False, obj=name
        )
        pd.testing.assert_series_equal(
            x_full.iloc[:300].fillna(False), x_cut.fillna(False), check_names=False, obj=name
        )


def test_backtest_is_deterministic():
    rng = np.random.default_rng(1)
    d = bars(100 * np.exp(np.cumsum(rng.normal(0, 0.02, 500))))
    a = backtest_symbol(d, STRATEGIES["donchian_breakout"], "X", 100_000, ChargeSchedule())
    b = backtest_symbol(d, STRATEGIES["donchian_breakout"], "X", 100_000, ChargeSchedule())
    assert [t.net for t in a[0]] == [t.net for t in b[0]] and len(a[0]) > 3
    pd.testing.assert_series_equal(a[1], b[1])

"""Risk engine: every unsafe condition must block; sizing/limits at exact boundaries; VaR/CVaR correctness."""

from datetime import UTC, datetime, timedelta

import numpy as np
import pandas as pd
import pytest
from pydantic import ValidationError

from app.engines.risk import metrics
from app.engines.risk.engine import RiskEngine, atr_stop, position_size, update_trailing_stop
from app.engines.risk.schemas import MarketSnapshot, OrderIntent, PortfolioState, Position, RiskLimits

NOW = datetime(2026, 11, 13, 10, 0, tzinfo=UTC)
KEY = "NSE_EQ|INE002A01018"


def intent(**kw):
    base = dict(
        intent_id="i1",
        instrument_key=KEY,
        sector="ENERGY",
        side="BUY",
        product="INTRADAY",
        entry_price=1000.0,
        stop_price=990.0,
        confidence=0.6,
        created_at=NOW,
    )
    return OrderIntent(**{**base, **kw})


def market(**kw):
    return MarketSnapshot(**{**dict(instrument_key=KEY, last_price=1000.0, atr=5.0, data_ts=NOW), **kw})


def pf(**kw):
    base = dict(
        equity=1_000_000.0, cash=1_000_000.0, start_of_day_equity=1_000_000.0, peak_equity=1_000_000.0
    )
    return PortfolioState(**{**base, **kw})


def failed(v):
    return {c.name for c in v.checks if not c.passed}


# ---------- happy path & sizing ----------


def test_approves_clean_intent_with_fixed_fractional_size():
    v = RiskEngine().evaluate(intent(), market(), pf(), now=NOW)
    assert v.approved and failed(v) == set()
    # 0.5% of 10L = 5,000 at risk / 10 per share = 500 shares; single-stock cap 10% -> 100 shares binds
    assert v.quantity == 100
    assert v.take_profit == pytest.approx(1020.0) and v.stop_price == 990.0


def test_risk_based_size_when_it_is_the_binding_cap():
    v = RiskEngine(RiskLimits(max_single_stock_pct=1.0, max_sector_pct=1.0)).evaluate(
        intent(), market(), pf(), now=NOW
    )
    assert v.quantity == 500
    v = RiskEngine(RiskLimits(max_single_stock_pct=1.0)).evaluate(intent(), market(), pf(), now=NOW)
    assert v.quantity == 250  # 25% sector cap binds next


def test_atr_stop_used_when_intent_has_none():
    v = RiskEngine().evaluate(intent(stop_price=None), market(atr=5.0), pf(), now=NOW)
    assert v.approved and v.stop_price == 990.0  # 1000 - 2 x 5
    s = RiskEngine().evaluate(intent(side="SELL", stop_price=None), market(atr=5.0), pf(), now=NOW)
    assert s.stop_price == 1010.0 and s.take_profit == pytest.approx(980.0)


def test_position_size_helper_edges():
    assert position_size(1_000_000, 0.005, 100, 100) == 0
    assert position_size(1_000_000, 0.005, 100, 99) == 5000
    assert position_size(1_000_000, 0.005, 100, 98.0001) == 2500  # floor, never rounds up risk


def test_trailing_stop_only_tightens():
    assert update_trailing_stop("BUY", 990, 1030, 5, 2) == 1020
    assert update_trailing_stop("BUY", 1020, 1010, 5, 2) == 1020  # price fell: stop stays
    assert update_trailing_stop("SELL", 1010, 970, 5, 2) == 980
    assert update_trailing_stop("SELL", 980, 990, 5, 2) == 980
    assert atr_stop("BUY", 100, 2, 1.5) == 97


# ---------- every blocking condition ----------


@pytest.mark.parametrize(
    "kw,expect",
    [
        (dict(engine=dict(kill_switch=True)), "kill_switch_off"),
        (dict(market=dict(data_ts=NOW - timedelta(seconds=121))), "market_data_fresh"),
        (dict(market=dict(data_ts=NOW + timedelta(seconds=5))), "market_data_fresh"),  # future-dated data
        (dict(market=dict(feed_healthy=False)), "feed_healthy"),
        (dict(market=dict(instrument_key="NSE_EQ|OTHER")), "instrument_matches"),
        (dict(intent=dict(entry_price=1025.0, stop_price=1015.0)), "entry_near_market"),
        (dict(intent=dict(confidence=0.39)), "confidence"),
        (dict(intent=dict(stop_price=1001.0)), "stop_valid"),  # BUY stop above entry
        (dict(intent=dict(stop_price=None), market=dict(atr=None)), "stop_valid"),
        (dict(pf=dict(equity=899_000.0)), "max_drawdown"),
        (dict(pf=dict(equity=979_000.0, peak_equity=979_000.0)), "daily_loss_limit"),
        (
            dict(intent=dict(entry_price=0.0001, stop_price=0.00005), market=dict(last_price=0.0001)),
            "prices_valid",
        ),
    ],
)
def test_unsafe_conditions_block(kw, expect):
    eng = RiskEngine(**kw.get("engine", {}))
    v = eng.evaluate(
        intent(**kw.get("intent", {})), market(**kw.get("market", {})), pf(**kw.get("pf", {})), now=NOW
    )
    assert not v.approved and v.quantity == 0 and expect in failed(v)
    assert any(expect in r for r in v.reasons)


def test_boundaries_are_exact():
    eng = RiskEngine()
    assert eng.evaluate(intent(), market(data_ts=NOW - timedelta(seconds=120)), pf(), now=NOW).approved
    assert eng.evaluate(intent(confidence=0.40), market(), pf(), now=NOW).approved
    # drawdown of exactly -10% is a breach (limit is "> -10%"), despite float rounding
    assert "max_drawdown" in failed(
        eng.evaluate(intent(), market(), pf(equity=900_000.0, start_of_day_equity=900_000.0), now=NOW)
    )
    assert "daily_loss_limit" in failed(eng.evaluate(intent(), market(), pf(equity=980_000.0), now=NOW))
    assert eng.evaluate(
        intent(), market(), pf(equity=900_001.0, start_of_day_equity=900_001.0), now=NOW
    ).approved


def test_max_concurrent_positions_and_duplicates():
    held = [
        Position(instrument_key=f"NSE_EQ|X{i}", quantity=1, avg_price=10, last_price=10) for i in range(10)
    ]
    rets = pd.DataFrame(
        np.random.default_rng(0).normal(0, 0.01, (100, 11)), columns=[*(p.instrument_key for p in held), KEY]
    )
    v = RiskEngine().evaluate(intent(), market(), pf(positions=held), returns=rets, now=NOW)
    assert "max_concurrent_positions" in failed(v)
    dup = [Position(instrument_key=KEY, quantity=50, avg_price=1000, last_price=1000)]
    v = RiskEngine().evaluate(intent(), market(), pf(positions=dup), returns=rets, now=NOW)
    assert "no_duplicate_position" in failed(v)
    # opposite direction on an existing holding (reducing/closing) is not a duplicate
    v = RiskEngine().evaluate(
        intent(side="SELL", stop_price=1010.0), market(), pf(positions=dup), returns=rets, now=NOW
    )
    assert "no_duplicate_position" not in failed(v)


def test_sector_and_gross_exposure_caps_shrink_or_block():
    held = [
        Position(instrument_key="NSE_EQ|E1", sector="ENERGY", quantity=240, avg_price=1000, last_price=1000)
    ]
    rets = pd.DataFrame(np.random.default_rng(1).normal(0, 0.01, (100, 2)), columns=["NSE_EQ|E1", KEY])
    v = RiskEngine().evaluate(intent(), market(), pf(positions=held), returns=rets, now=NOW)
    assert v.approved and v.quantity == 10  # 25% sector cap: 250k - 240k = 10k -> 10 shares
    held[0].quantity = 250
    v = RiskEngine().evaluate(intent(), market(), pf(positions=held), returns=rets, now=NOW)
    assert not v.approved and "sized_quantity_positive" in failed(v)
    v = RiskEngine(RiskLimits(max_gross_exposure_pct=0.25, max_sector_pct=1.0)).evaluate(
        intent(sector="IT"), market(), pf(positions=held), returns=rets, now=NOW
    )
    assert not v.approved  # gross exposure already at 25%


def test_delivery_buy_limited_by_cash_and_delivery_short_rejected():
    v = RiskEngine().evaluate(intent(product="DELIVERY"), market(), pf(cash=20_500.0), now=NOW)
    assert v.approved and v.quantity == 20
    with pytest.raises(ValidationError):
        intent(side="SELL", product="DELIVERY")


def test_holdings_without_return_history_fail_closed():
    held = [Position(instrument_key="NSE_EQ|E1", quantity=10, avg_price=100, last_price=100)]
    v = RiskEngine().evaluate(intent(), market(), pf(positions=held), returns=None, now=NOW)
    assert not v.approved and {"correlation", "portfolio_var"} <= failed(v)


def test_high_correlation_blocks():
    base = np.random.default_rng(2).normal(0, 0.01, 120)
    rets = pd.DataFrame({"NSE_EQ|E1": base, KEY: base + np.random.default_rng(3).normal(0, 0.0005, 120)})
    held = [Position(instrument_key="NSE_EQ|E1", sector="X", quantity=10, avg_price=100, last_price=100)]
    v = RiskEngine().evaluate(intent(), market(), pf(positions=held), returns=rets, now=NOW)
    assert "correlation" in failed(v)


def test_var_budget_blocks_oversized_book():
    rets = pd.DataFrame({KEY: np.random.default_rng(4).normal(0, 0.05, 250)})  # very volatile stock
    v = RiskEngine(
        RiskLimits(max_single_stock_pct=1.0, max_portfolio_var_pct=0.01, risk_per_trade_pct=0.05)
    ).evaluate(intent(stop_price=950.0), market(), pf(), returns=rets, now=NOW)
    assert "portfolio_var" in failed(v)


def test_nan_price_rejected_at_schema():
    with pytest.raises(ValidationError):
        market(last_price=float("nan"))


def test_every_check_recorded_even_when_rejected():
    v = RiskEngine(kill_switch=True).evaluate(intent(), market(), pf(), now=NOW)
    names = {c.name for c in v.checks}
    assert {
        "kill_switch_off",
        "market_data_fresh",
        "stop_valid",
        "max_drawdown",
        "daily_loss_limit",
        "sized_quantity_positive",
        "correlation",
    } <= names


# ---------- VaR / CVaR / stress ----------


def test_historical_var_cvar_hand_computed():
    pnl = np.array([-10.0, -8, -6, -4, -2] + [1.0] * 95)
    assert metrics.historical_var(pnl, 0.95) == 2.0  # 5th-lowest of 100 (method="lower")
    assert metrics.historical_cvar(pnl, 0.95) == pytest.approx(6.0)  # mean of the worst five
    assert metrics.historical_var(pnl, 0.99) == 10.0
    with pytest.raises(ValueError):
        metrics.historical_var(np.ones(10))


def test_parametric_var():
    assert metrics.parametric_var(1_000_000, 0.01, 0.95) == pytest.approx(16448.536, rel=1e-6)
    assert metrics.parametric_var(1_000_000, 0.01, 0.95, 4) == pytest.approx(32897.07, rel=1e-6)


def test_cvar_at_least_var_on_real_like_data():
    pnl = np.random.default_rng(5).standard_t(3, 2000)
    assert metrics.historical_cvar(pnl) >= metrics.historical_var(pnl)


def test_stress_uses_beta_and_sector_shocks():
    out = metrics.stress_test(
        [
            {"value": 100_000, "beta": 1.2, "sector": "NSE_INDEX|Nifty IT"},
            {"value": 50_000, "beta": 0.8, "sector": "NSE_INDEX|Nifty Fin Service"},
        ]
    )
    assert out["nifty_-5pct_day"] == pytest.approx(100_000 * 1.2 * -0.05 + 50_000 * 0.8 * -0.05)
    assert out["it_-10pct"] == pytest.approx(-10_000 + 50_000 * 0.8 * -0.02)


def test_delivery_uses_end_of_day_freshness_but_intraday_needs_live_data():
    eod = market(data_ts=NOW - timedelta(hours=18))  # yesterday's close
    assert RiskEngine().evaluate(intent(product="DELIVERY"), eod, pf(), now=NOW).approved
    assert "market_data_fresh" in failed(RiskEngine().evaluate(intent(), eod, pf(), now=NOW))
    week_old = market(data_ts=NOW - timedelta(days=5))
    assert "market_data_fresh" in failed(
        RiskEngine().evaluate(intent(product="DELIVERY"), week_old, pf(), now=NOW)
    )


def test_passing_checks_carry_no_failure_text():
    v = RiskEngine().evaluate(intent(), market(), pf(), now=NOW)
    for c in v.checks:
        if c.passed and c.detail:
            assert not any(w in c.detail for w in ("away", "missing", "wrong", "stale")), (c.name, c.detail)

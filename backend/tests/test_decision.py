"""Decision engine: NO_TRADE on every invalid condition; trades only after risk approval; explanations recorded."""

from datetime import UTC, datetime, timedelta

import pytest

from app.engines.decision.engine import DecisionEngine, Inputs
from app.engines.risk.engine import RiskEngine
from app.engines.risk.schemas import MarketSnapshot, PortfolioState

NOW = datetime(2026, 11, 13, 5, 0, tzinfo=UTC)
KEY = "NSE_EQ|INE002A01018"


def inputs(pipeline="intraday", pred=..., news=None, regime=None, market=..., holding=0, **kw):
    if pred is ...:
        pred = {
            "p_up": 0.55,
            "p_neutral": 0.30,
            "p_down": 0.15,
            "as_of": NOW - timedelta(minutes=1),
            "model_version": "m1",
            "promoted": True,
        }
    if market is ...:
        market = MarketSnapshot(
            instrument_key=KEY, last_price=1000.0, atr=5.0, data_ts=NOW - timedelta(seconds=30)
        )
    pf = PortfolioState(equity=1e6, cash=1e6, start_of_day_equity=1e6, peak_equity=1e6)
    return Inputs(
        KEY,
        "RELIANCE",
        pipeline,
        NOW,
        pred,
        news,
        regime,
        market,
        pf,
        sector="ENERGY",
        holding_qty=holding,
        **kw,
    )


def eng(kill=False):
    return DecisionEngine(RiskEngine(kill_switch=kill))


def test_buy_when_signal_strong_and_risk_approves():
    d = eng().decide(inputs())
    assert d.action == "BUY" and d.quantity > 0 and d.risk["approved"]
    assert d.contributions["ml"]["score"] == pytest.approx(0.40) and d.model_version == "m1"
    assert d.risk["stop"] == 990.0 and d.risk["take_profit"] == 1020.0


def test_intraday_sell_signal_shorts():
    p = {
        "p_up": 0.1,
        "p_neutral": 0.3,
        "p_down": 0.6,
        "as_of": NOW - timedelta(minutes=1),
        "model_version": "m",
        "promoted": True,
    }
    d = eng().decide(inputs(pred=p))
    assert d.action == "SELL" and d.risk["stop"] == 1010.0


@pytest.mark.parametrize(
    "kw,reason",
    [
        (dict(pred=None), "no model prediction"),
        (
            dict(
                pred={
                    "p_up": 0.6,
                    "p_neutral": 0.2,
                    "p_down": 0.2,
                    "as_of": NOW,
                    "model_version": "m",
                    "promoted": False,
                }
            ),
            "promotion gate",
        ),
        (
            dict(
                pred={
                    "p_up": 0.6,
                    "p_neutral": 0.2,
                    "p_down": 0.2,
                    "as_of": NOW - timedelta(minutes=30),
                    "model_version": "m",
                    "promoted": True,
                }
            ),
            "stale",
        ),
        (
            dict(
                pred={
                    "p_up": 0.6,
                    "p_neutral": 0.2,
                    "p_down": 0.2,
                    "as_of": NOW + timedelta(minutes=5),
                    "model_version": "m",
                    "promoted": True,
                }
            ),
            "future-dated",
        ),
        (dict(market=None), "no market snapshot"),
        (
            dict(
                pred={
                    "p_up": 0.38,
                    "p_neutral": 0.45,
                    "p_down": 0.17,
                    "as_of": NOW,
                    "model_version": "m",
                    "promoted": True,
                }
            ),
            "not dominant",
        ),
        (
            dict(
                pred={
                    "p_up": 0.42,
                    "p_neutral": 0.20,
                    "p_down": 0.38,
                    "as_of": NOW,
                    "model_version": "m",
                    "promoted": True,
                }
            ),
            "edge",
        ),
        (dict(news={"items": 3, "sentiment": -0.9, "confidence": 0.9, "top": []}), "conflicting signals"),
    ],
)
def test_invalid_or_weak_inputs_give_no_trade(kw, reason):
    d = eng().decide(inputs(**kw))
    assert d.action == "NO_TRADE" and d.quantity == 0 and any(reason in r for r in d.reasons)


def test_stale_market_data_rejected_by_risk_not_bypassed():
    stale = MarketSnapshot(
        instrument_key=KEY, last_price=1000.0, atr=5.0, data_ts=NOW - timedelta(minutes=10)
    )
    d = eng().decide(inputs(market=stale))
    assert d.action == "NO_TRADE" and "market_data_fresh" in d.risk["failed_checks"]


def test_kill_switch_forces_no_trade():
    d = eng(kill=True).decide(inputs())
    assert d.action == "NO_TRADE" and "kill_switch_off" in d.risk["failed_checks"]


def test_swing_rules_no_delivery_short_and_bear_regime():
    p = {
        "p_up": 0.1,
        "p_neutral": 0.3,
        "p_down": 0.6,
        "as_of": NOW - timedelta(hours=14),
        "model_version": "m",
        "promoted": True,
    }
    eod = MarketSnapshot(instrument_key=KEY, last_price=1000.0, atr=20.0, data_ts=NOW - timedelta(hours=14))
    assert "delivery shorts" in " ".join(eng().decide(inputs("swing", pred=p, market=eod)).reasons)
    up = {**p, "p_up": 0.6, "p_down": 0.1}
    d = eng().decide(inputs("swing", pred=up, market=eod, regime={"trend": "bear"}))
    assert d.action == "NO_TRADE" and "bearish market regime" in d.reasons[0]
    assert eng().decide(inputs("swing", pred=up, market=eod, regime={"trend": "bull"})).action == "BUY"


def test_positive_news_can_lift_marginal_signal_and_is_explained():
    p = {
        "p_up": 0.43,
        "p_neutral": 0.21,
        "p_down": 0.36,
        "as_of": NOW,
        "model_version": "m",
        "promoted": True,
    }
    weak = eng().decide(inputs(pred=p))
    assert weak.action == "NO_TRADE" and "edge 0.070 below threshold" in weak.reasons[0]
    d = eng().decide(
        inputs(
            pred=p,
            news={"items": 2, "sentiment": 0.8, "confidence": 0.9, "top": [{"title": "Wins large order"}]},
        )
    )
    assert d.action == "BUY" and d.contributions["news"]["score"] == pytest.approx(0.18)
    assert d.contributions["news"]["top"] == ["Wins large order"]


def test_holding_management():
    assert eng().decide(inputs(holding=100)).action == "HOLD"
    p = {"p_up": 0.1, "p_neutral": 0.3, "p_down": 0.6, "as_of": NOW, "model_version": "m", "promoted": True}
    assert eng().decide(inputs(pred=p, holding=100)).action == "SELL"  # exit long on reversal


def test_every_decision_has_traceable_explanation():
    for kw in ({}, {"pred": None}, {"market": None}):
        d = eng().decide(inputs(**kw)).to_dict()
        assert d["reasons"] and d["decision_id"] and d["created_at"] and "action" in d

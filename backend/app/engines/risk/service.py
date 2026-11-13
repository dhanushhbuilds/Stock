"""Risk engine persistence + orchestration: kill switch, limits, and logging of every decision."""

import numpy as np
import pandas as pd
from sqlalchemy.orm import Session

from app.core.audit import record
from app.engines.data.storage import CandleLake
from app.engines.risk import metrics
from app.engines.risk.engine import RiskEngine, returns_matrix
from app.engines.risk.schemas import MarketSnapshot, OrderIntent, PortfolioState, RiskLimits, RiskVerdict
from app.models.risk import RiskAssessment, RiskState


def get_state(session: Session) -> RiskState:
    st = session.get(RiskState, 1)
    if st is None:
        st = RiskState(id=1, kill_switch=False, limits=RiskLimits().model_dump(), changed_by="system")
        session.add(st)
        session.commit()
    return st


def set_kill_switch(session: Session, on: bool, reason: str, actor: str) -> RiskState:
    st = get_state(session)
    st.kill_switch, st.reason, st.changed_by = on, reason, actor
    session.commit()
    record(session, "risk", "kill_switch_on" if on else "kill_switch_off", {"reason": reason}, actor=actor)
    return st


def set_limits(session: Session, limits: RiskLimits, actor: str) -> RiskState:
    st = get_state(session)
    old = st.limits
    st.limits, st.changed_by = limits.model_dump(), actor
    session.commit()
    record(session, "risk", "limits_changed", {"old": old, "new": st.limits}, actor=actor)
    return st


def history_returns(lake: CandleLake, keys: list[str], lookback_days: int = 500) -> pd.DataFrame:
    closes = {}
    for k in keys:
        d = lake.read("1day", k)
        if not d.empty:
            closes[k] = d.set_index(d["ts"].dt.tz_localize(None).dt.normalize())["close"].tail(
                lookback_days + 1
            )
    return returns_matrix(closes) if closes else pd.DataFrame()


def evaluate_and_log(
    session: Session,
    intent: OrderIntent,
    market: MarketSnapshot,
    pf: PortfolioState,
    returns: pd.DataFrame | None,
) -> RiskVerdict:
    st = get_state(session)
    engine = RiskEngine(RiskLimits(**st.limits), kill_switch=st.kill_switch)
    verdict = engine.evaluate(intent, market, pf, returns)
    session.add(
        RiskAssessment(
            intent_id=intent.intent_id,
            instrument_key=intent.instrument_key,
            approved=verdict.approved,
            quantity=verdict.quantity,
            intent=intent.model_dump(mode="json"),
            verdict=verdict.model_dump(mode="json"),
        )
    )
    session.commit()
    record(
        session,
        "risk",
        "order_approved" if verdict.approved else "order_rejected",
        {
            "intent_id": intent.intent_id,
            "instrument_key": intent.instrument_key,
            "quantity": verdict.quantity,
            "reasons": verdict.reasons,
        },
    )
    return verdict


def portfolio_risk(
    pf: PortfolioState, returns: pd.DataFrame, betas: dict[str, float], confidence: float
) -> dict:
    values = {p.instrument_key: p.market_value for p in pf.positions if p.quantity}
    if not values:
        return {"positions": 0, "var": 0.0, "cvar": 0.0, "stress": {}}
    pnl = metrics.portfolio_pnl_series(values, returns)
    var, cvar = metrics.historical_var(pnl, confidence), metrics.historical_cvar(pnl, confidence)
    sigma = float(np.std(pnl / pf.equity, ddof=1))
    stress = metrics.stress_test(
        [
            {"value": p.market_value, "beta": betas.get(p.instrument_key, 1.0), "sector": p.sector}
            for p in pf.positions
            if p.quantity
        ]
    )
    return {
        "positions": len(values),
        "observations": int(len(pnl)),
        "confidence": confidence,
        "var": var,
        "cvar": cvar,
        "var_pct": var / pf.equity,
        "cvar_pct": cvar / pf.equity,
        "parametric_var": metrics.parametric_var(pf.equity, sigma, confidence),
        "gross_exposure": pf.gross_exposure,
        "gross_exposure_pct": pf.gross_exposure / pf.equity,
        "stress": stress,
    }

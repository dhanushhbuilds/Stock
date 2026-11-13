"""Risk engine API (Engine 5)."""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.db import get_session
from app.engines.data.storage import CandleLake
from app.engines.risk import service
from app.engines.risk.schemas import MarketSnapshot, OrderIntent, PortfolioState, RiskLimits, RiskVerdict
from app.models.risk import RiskAssessment

router = APIRouter(prefix="/risk", tags=["risk"])
SessionDep = Annotated[Session, Depends(get_session)]


class EvaluateRequest(BaseModel):
    intent: OrderIntent
    market: MarketSnapshot
    portfolio: PortfolioState


class KillSwitchRequest(BaseModel):
    on: bool
    reason: str = Field(min_length=3, max_length=500)
    actor: str = Field("operator", max_length=64)


class PortfolioRiskRequest(BaseModel):
    portfolio: PortfolioState
    betas: dict[str, float] = Field(default_factory=dict)


def _returns(keys: list[str]):
    return service.history_returns(CandleLake(get_settings().data_dir), keys)


@router.get("/state")
def state(session: SessionDep):
    st = service.get_state(session)
    return {
        "kill_switch": st.kill_switch,
        "reason": st.reason,
        "changed_by": st.changed_by,
        "updated_at": st.updated_at,
        "limits": st.limits,
    }


@router.post("/kill-switch")
def kill_switch(req: KillSwitchRequest, session: SessionDep):
    st = service.set_kill_switch(session, req.on, req.reason, req.actor)
    return {"kill_switch": st.kill_switch, "reason": st.reason}


@router.put("/limits")
def put_limits(limits: RiskLimits, session: SessionDep):
    return service.set_limits(session, limits, "operator").limits


@router.post("/evaluate", response_model=RiskVerdict)
def evaluate(req: EvaluateRequest, session: SessionDep):
    keys = sorted({req.intent.instrument_key, *[p.instrument_key for p in req.portfolio.positions]})
    rets = _returns(keys)
    return service.evaluate_and_log(
        session, req.intent, req.market, req.portfolio, rets if not rets.empty else None
    )


@router.post("/portfolio")
def portfolio_risk(req: PortfolioRiskRequest, session: SessionDep):
    st = service.get_state(session)
    keys = [p.instrument_key for p in req.portfolio.positions if p.quantity]
    rets = _returns(keys) if keys else None
    try:
        return service.portfolio_risk(req.portfolio, rets, req.betas, st.limits["var_confidence"])
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc


@router.get("/assessments")
def assessments(session: SessionDep, limit: int = 50):
    rows = session.scalars(select(RiskAssessment).order_by(RiskAssessment.id.desc()).limit(min(limit, 500)))
    return [
        {
            "id": r.id,
            "intent_id": r.intent_id,
            "instrument_key": r.instrument_key,
            "approved": r.approved,
            "quantity": r.quantity,
            "reasons": r.verdict.get("reasons"),
            "created_at": r.created_at,
        }
        for r in rows
    ]

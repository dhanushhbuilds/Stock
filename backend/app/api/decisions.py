"""Decision engine API (Engine 6). Produces explainable BUY/SELL/HOLD/NO_TRADE; never places orders."""

from datetime import UTC, datetime
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.db import get_session
from app.engines.decision import service
from app.models.decision import DecisionRecord

router = APIRouter(prefix="/decisions", tags=["decisions"])
SessionDep = Annotated[Session, Depends(get_session)]


@router.post("/run")
def run(
    session: SessionDep,
    pipeline: Literal["swing", "intraday"] = "swing",
    as_of: datetime | None = None,
    symbols: str | None = None,
):
    syms = [s.strip().upper() for s in symbols.split(",")] if symbols else None
    if pipeline == "swing":
        decisions, err = service.run_swing(session, get_settings(), as_of, syms)
    else:
        if as_of is None:
            raise HTTPException(
                422, "intraday runs are historical replays: pass as_of (live feed not connected)"
            )
        if as_of.tzinfo is None:
            raise HTTPException(422, "as_of must include a timezone")
        decisions, err = service.run_intraday_replay(session, get_settings(), as_of, syms)
    if err:
        raise HTTPException(409, err)
    return {"summary": service.summarize(decisions), "decisions": [d.to_dict() for d in decisions]}


@router.get("")
def list_decisions(
    session: SessionDep,
    symbol: str | None = None,
    action: str | None = None,
    limit: int = Query(100, ge=1, le=1000),
):
    stmt = select(DecisionRecord).order_by(DecisionRecord.created_at.desc())
    if symbol:
        stmt = stmt.where(DecisionRecord.symbol == symbol.upper())
    if action:
        stmt = stmt.where(DecisionRecord.action == action.upper())
    return [r.explanation for r in session.scalars(stmt.limit(limit))]


@router.get("/regime")
def regime():
    """Current rule-based market regime from NIFTY 50 trend and India VIX percentile (latest completed session)."""
    import pandas as pd

    from app.engines.data.storage import CandleLake

    now = pd.Timestamp.now(tz="Asia/Kolkata").tz_localize(None)
    return service.market_regime(CandleLake(get_settings().data_dir), now)


@router.get("/health")
def decision_health():
    return {
        "live_trading_enabled": get_settings().live_trading_enabled,
        "orders_placed_by_this_engine": 0,
        "now": datetime.now(UTC).isoformat(),
    }

"""Market-data read API (Engine 1)."""

from datetime import date, datetime
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.db import get_session
from app.engines.data.instruments import MappingError, resolve
from app.engines.data.service import lake_for, universe_members
from app.models.data import CandleFile, DataQualityReport, Instrument

router = APIRouter(prefix="/data", tags=["data"])
SessionDep = Annotated[Session, Depends(get_session)]
TimeframeQ = Literal["1minute", "5minute", "1day"]


class InstrumentOut(BaseModel):
    instrument_key: str
    segment: str
    trading_symbol: str
    name: str
    isin: str | None
    lot_size: int | None
    tick_size_paise: float | None


class CoverageOut(BaseModel):
    instrument_key: str
    timeframe: str
    files: int
    rows: int
    first_ts: datetime
    last_ts: datetime
    quality_passed: bool | None
    quality_checked_at: datetime | None


class MemberOut(BaseModel):
    symbol: str
    company_name: str
    industry: str
    instrument_key: str
    sector_index_key: str | None
    as_of: date


class CandleOut(BaseModel):
    ts: datetime
    open: float
    high: float
    low: float
    close: float
    volume: int


class CandlesResponse(BaseModel):
    instrument_key: str
    trading_symbol: str
    timeframe: str
    count: int
    truncated: bool
    candles: list[CandleOut]


@router.get("/universe", response_model=list[MemberOut])
def get_universe(session: SessionDep):
    return [MemberOut.model_validate(m, from_attributes=True) for m in universe_members(session)]


@router.get("/instruments", response_model=list[InstrumentOut])
def search_instruments(
    session: SessionDep,
    q: str = "",
    segment: Literal["NSE_EQ", "NSE_INDEX"] | None = None,
    limit: int = Query(50, ge=1, le=500),
):
    stmt = select(Instrument)
    if segment:
        stmt = stmt.where(Instrument.segment == segment)
    if q:
        like = f"%{q}%"
        stmt = stmt.where(or_(Instrument.trading_symbol.ilike(like), Instrument.name.ilike(like)))
    rows = session.scalars(stmt.order_by(Instrument.trading_symbol).limit(limit))
    return [InstrumentOut.model_validate(r, from_attributes=True) for r in rows]


@router.get("/coverage", response_model=list[CoverageOut])
def coverage(session: SessionDep):
    agg = session.execute(
        select(
            CandleFile.instrument_key,
            CandleFile.timeframe,
            func.count(),
            func.sum(CandleFile.rows),
            func.min(CandleFile.first_ts),
            func.max(CandleFile.last_ts),
        )
        .group_by(CandleFile.instrument_key, CandleFile.timeframe)
        .order_by(CandleFile.instrument_key, CandleFile.timeframe)
    ).all()
    latest = {}
    for r in session.scalars(select(DataQualityReport).order_by(DataQualityReport.generated_at)):
        latest[(r.instrument_key, r.timeframe)] = r
    out = []
    for key, tf, files, rows, first, last in agg:
        q = latest.get((key, tf))
        out.append(
            CoverageOut(
                instrument_key=key,
                timeframe=tf,
                files=files,
                rows=int(rows),
                first_ts=first,
                last_ts=last,
                quality_passed=q.passed if q else None,
                quality_checked_at=q.generated_at if q else None,
            )
        )
    return out


@router.get("/quality/{instrument:path}")
def quality(instrument: str, session: SessionDep, timeframe: TimeframeQ = "1day"):
    inst = _resolve(session, instrument)
    r = session.scalars(
        select(DataQualityReport)
        .filter_by(instrument_key=inst.instrument_key, timeframe=timeframe)
        .order_by(DataQualityReport.generated_at.desc())
    ).first()
    if r is None:
        raise HTTPException(404, "no quality report yet")
    return {"generated_at": r.generated_at, "passed": r.passed, **r.summary}


@router.get("/candles/{instrument:path}", response_model=CandlesResponse)
def candles(
    instrument: str,
    session: SessionDep,
    timeframe: TimeframeQ = "1day",
    start: date | None = None,
    end: date | None = None,
    limit: int = Query(2000, ge=1, le=20000),
):
    if start and end and start > end:
        raise HTTPException(422, "start must be <= end")
    inst = _resolve(session, instrument)
    lake = lake_for(get_settings())
    df = lake.read(timeframe, inst.instrument_key, start=start, end=f"{end} 23:59:59" if end else None)
    truncated = len(df) > limit
    df = df.tail(limit)  # most recent `limit` bars
    rows = [
        CandleOut(
            ts=r.ts.to_pydatetime(), open=r.open, high=r.high, low=r.low, close=r.close, volume=int(r.volume)
        )
        for r in df.itertuples()
    ]
    return CandlesResponse(
        instrument_key=inst.instrument_key,
        trading_symbol=inst.trading_symbol,
        timeframe=timeframe,
        count=len(rows),
        truncated=truncated,
        candles=rows,
    )


def _resolve(session: Session, instrument: str) -> Instrument:
    try:
        return resolve(session, instrument)
    except MappingError as exc:
        raise HTTPException(404, str(exc)) from exc

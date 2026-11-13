"""News intelligence API (Engine 3)."""

from datetime import UTC, datetime
from functools import lru_cache
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.audit import record
from app.core.config import get_settings
from app.core.db import get_session
from app.engines.data.instruments import MappingError, resolve
from app.engines.news import service
from app.engines.news.nlp import FinBERT
from app.engines.news.sources import SOURCES, SourceError, fetch
from app.models.news import NewsItem

router = APIRouter(prefix="/news", tags=["news"])
SessionDep = Annotated[Session, Depends(get_session)]


@lru_cache
def finbert() -> FinBERT:
    return FinBERT(get_settings().artifacts_dir / "hf")


def get_sentiment_model():
    return finbert()


@router.post("/ingest/{source}")
def ingest(source: str, session: SessionDep, model: Annotated[FinBERT, Depends(get_sentiment_model)]):
    if source not in SOURCES:
        raise HTTPException(404, f"unknown source; available: {sorted(SOURCES)}")
    try:
        items = fetch(source)
    except SourceError as exc:
        record(session, "news", "source_failed", {"source": source, "error": str(exc)})
        raise HTTPException(502, str(exc)) from exc
    stats = service.ingest(session, items, service.build_mapper(session), model)
    record(session, "news", "ingested", {"source": source, **stats})
    return stats


@router.get("")
def list_news(
    session: SessionDep,
    symbol: str | None = None,
    event: str | None = None,
    limit: int = Query(50, ge=1, le=500),
):
    stmt = select(NewsItem).where(NewsItem.duplicate_of.is_(None)).order_by(NewsItem.usable_from.desc())
    if event:
        stmt = stmt.where(NewsItem.event_type == event)
    if symbol:
        stmt = stmt.where(NewsItem.symbols.contains([symbol.upper()]))
    return [
        {
            "id": r.id,
            "source": r.source,
            "title": r.title,
            "url": r.url,
            "published_at": r.published_at,
            "usable_from": r.usable_from,
            "timestamp_status": r.timestamp_status,
            "symbols": r.symbols,
            "event_type": r.event_type,
            "importance": r.importance,
            "sentiment": r.sentiment_label,
            "sentiment_score": r.sentiment_score,
        }
        for r in session.scalars(stmt.limit(limit))
    ]


@router.get("/signal/{instrument:path}")
def signal(instrument: str, session: SessionDep, as_of: datetime | None = None):
    try:
        inst = resolve(session, instrument)
    except MappingError as exc:
        raise HTTPException(404, str(exc)) from exc
    as_of = as_of or datetime.now(UTC)
    if as_of.tzinfo is None:
        raise HTTPException(422, "as_of must include a timezone")
    return service.signal_for(session, inst.instrument_key, as_of)

"""News ingestion pipeline and point-in-time news signals (Engine 3)."""

import math
from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.logging import get_logger
from app.engines.news import nlp
from app.engines.news.sources import SOURCES, RawItem
from app.models.data import Instrument, UniverseMember
from app.models.news import NewsItem

log = get_logger(__name__)
FUTURE_TOLERANCE = timedelta(minutes=5)  # publisher clock skew allowed

# Common short names used in filings/news that differ from the master's legal name.
# Ambiguous short names ("Reliance", "HDFC", "Tata", "Bajaj", "Adani") are deliberately NOT aliased.
ALIASES = {
    "HDFC Bank": "HDFCBANK",
    "Infosys": "INFY",
    "Reliance Industries": "RELIANCE",
    "SBI": "SBIN",
    "State Bank of India": "SBIN",
    "Airtel": "BHARTIARTL",
    "L&T": "LT",
    "Larsen & Toubro": "LT",
    "Bajaj Finance": "BAJFINANCE",
    "ITC": "ITC",
    "Maruti": "MARUTI",
    "HUL": "HINDUNILVR",
}


def build_mapper(session: Session) -> nlp.EntityMapper:
    sector = {m.instrument_key: m.sector_index_key for m in session.scalars(select(UniverseMember))}
    ents = [
        nlp.Entity(i.instrument_key, i.trading_symbol, i.name, sector.get(i.instrument_key))
        for i in session.scalars(select(Instrument).where(Instrument.segment == "NSE_EQ"))
    ]
    return nlp.EntityMapper(ents, ALIASES)


def validate_timestamp(published: datetime | None, ingested: datetime) -> tuple[str, datetime]:
    if published is None:
        return "missing", ingested
    if published > ingested + FUTURE_TOLERANCE:
        return "future_rejected", published
    return "ok", max(published, ingested)


def ingest(
    session: Session,
    items: list[RawItem],
    mapper: nlp.EntityMapper,
    sentiment: nlp.SentimentModel | None,
    now: datetime | None = None,
) -> dict:
    now = now or datetime.now(UTC)
    stats = {
        "received": len(items),
        "inserted": 0,
        "duplicates": 0,
        "near_duplicates": 0,
        "future_rejected": 0,
        "missing_timestamp": 0,
        "mapped_to_instrument": 0,
    }
    fresh: list[tuple[RawItem, NewsItem]] = []
    seen_uids = set(session.scalars(select(NewsItem.uid)))
    recent = list(session.scalars(select(NewsItem).where(NewsItem.ingested_at >= now - timedelta(days=2))))
    for it in items:
        uid = nlp.content_hash(it.source, it.title, it.published_raw)
        if uid in seen_uids:
            stats["duplicates"] += 1
            continue
        seen_uids.add(uid)
        status, usable = validate_timestamp(it.published_at, now)
        stats["future_rejected"] += status == "future_rejected"
        stats["missing_timestamp"] += status == "missing"
        scope = SOURCES[it.source].scope if it.source in SOURCES else "market"
        if scope == "company":
            # The filer is explicit: map it or leave unmapped. Never fall back to fuzzy mentions (that tagged
            # "Reliance Mutual Fund" NAV filings as RELIANCE on live data).
            issuer = mapper.issuer(it.company, it.symbol_hint)
            ents = [issuer] if issuer else []
        else:
            issuer, ents = None, mapper.mentions(f"{it.title} {it.body}")
        event, importance = nlp.classify_event(f"{it.title} {it.body} {it.extra.get('subject', '')}")
        row = NewsItem(
            uid=uid,
            source=it.source,
            scope=scope,
            title=it.title[:2000],
            body=it.body[:8000],
            url=it.url,
            published_at=it.published_at,
            ingested_at=now,
            usable_from=usable,
            timestamp_status=status,
            instrument_keys=[e.instrument_key for e in ents],
            symbols=[e.symbol for e in ents],
            direct_issuer=issuer is not None,
            event_type=event,
            importance=importance,
        )
        dup = next(
            (
                r
                for r in recent
                if r.source == it.source
                and r.symbols == row.symbols
                and nlp.near_duplicate(r.title, row.title)
            ),
            None,
        )
        stats["mapped_to_instrument"] += bool(ents)
        session.add(row)
        if dup is not None:
            session.flush()  # the original may be new in this batch: ensure it has an id before linking
            row.duplicate_of = dup.id
            stats["near_duplicates"] += 1
        recent.append(row)
        fresh.append((it, row))
    session.flush()
    to_score = [
        (it, r) for it, r in fresh if r.timestamp_status != "future_rejected" and r.duplicate_of is None
    ]
    if sentiment is not None and to_score:
        probs = sentiment.predict([f"{it.title}. {it.body}"[:1000] for it, _ in to_score])
        for (_, r), p in zip(to_score, probs, strict=True):
            r.sentiment_probs, r.sentiment_model = p, sentiment.version
            r.sentiment_label = max(p, key=p.get)
            r.sentiment_score = nlp.sentiment_score(p)
    session.commit()
    stats["inserted"] = len(fresh)
    stats["sentiment_scored"] = len(to_score) if sentiment is not None else 0
    return stats


def signal_for(
    session: Session,
    instrument_key: str,
    as_of: datetime,
    lookback_h: float = 72.0,
    half_life_h: float = 24.0,
) -> dict:
    """Point-in-time aggregate: only items with usable_from <= as_of. Market/regulatory items apply to every
    stock with lower relevance. Returns a neutral, zero-confidence signal when nothing qualifies."""
    rows = session.scalars(
        select(NewsItem).where(
            NewsItem.usable_from <= as_of,
            NewsItem.usable_from > as_of - timedelta(hours=lookback_h),
            NewsItem.timestamp_status != "future_rejected",
            NewsItem.duplicate_of.is_(None),
            NewsItem.sentiment_score.is_not(None),
        )
    ).all()
    contrib, wsum, items = 0.0, 0.0, []
    for r in rows:
        direct = instrument_key in (r.instrument_keys or [])
        if not direct and r.scope == "company":
            continue
        rel = nlp.relevance(r.scope, r.direct_issuer and direct, int(direct))
        w = r.importance * rel * nlp.freshness(r.usable_from, as_of, half_life_h)
        if w <= 0:
            continue
        contrib += r.sentiment_score * w
        wsum += w
        items.append(
            {
                "id": r.id,
                "title": r.title[:160],
                "event": r.event_type,
                "sentiment": r.sentiment_score,
                "weight": round(w, 4),
                "usable_from": r.usable_from.isoformat(),
            }
        )
    items.sort(key=lambda x: -x["weight"])
    return {
        "instrument_key": instrument_key,
        "as_of": as_of.isoformat(),
        "items": len(items),
        "sentiment": contrib / wsum if wsum else 0.0,  # weighted mean in [-1, 1]
        "impact": math.tanh(contrib),  # magnitude grows with more/stronger/fresher items
        "confidence": 1 - math.exp(-wsum),  # 0 when no evidence
        "top": items[:5],
    }

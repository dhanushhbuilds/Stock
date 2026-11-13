"""News engine: parsing real feed formats, timestamp validation, entity mapping (incl. live-found regressions),
classification, dedup, point-in-time signals, FinBERT schema."""

from datetime import UTC, datetime, timedelta

import httpx
import pytest

from app.engines.news import nlp, service
from app.engines.news.sources import IST, SourceError, fetch, parse_rss, parse_time

NSE_XML = b"""<rss xmlns:atom="http://www.w3.org/2005/Atom" version="2.0"><channel><title>x</title>
<item><title>Reliance Industries Limited</title>
<link>https://nsearchives.nseindia.com/corporate/RELIANCE_13112026101500_Results.pdf</link>
<description>Reliance Industries Limited has informed the Exchange about Financial Results |SUBJECT: Financial Result Updates</description>
<pubDate>13-Nov-2026 10:15:00</pubDate></item>
<item><title>Reliance Mutual Fund - Reliance Interval Fund - QIF</title>
<link>https://nsearchives.nseindia.com/corporate/xbrl/NAV_1.xml</link>
<description>Reliance Mutual Fund has informed the Exchange about Declaration of NAV |SUBJECT: Declaration of NAV</description>
<pubDate>13-Nov-2026 10:16:00</pubDate></item>
<item><title>Infosys Limited</title><link>https://nsearchives.nseindia.com/corporate/xbrl/X.xml</link>
<description>Infosys Limited has informed the Exchange about Buyback |SUBJECT: Buy back</description>
<pubDate>13-Nov-2026 11:00:00</pubDate></item>
<item><title>Unknown Smallcap Limited</title><link>https://x/y.pdf</link>
<description>has informed |SUBJECT: Updates</description><pubDate></pubDate></item>
</channel></rss>"""

RBI_XML = """﻿<?xml version="1.0" encoding="utf-8"?><rss version="2.0"><channel><title>PRESS RELEASES FROM RBI</title>
<item><title>Monetary Policy Statement: Reserve Bank of India keeps repo rate unchanged</title>
<description>&lt;table&gt;&lt;tr&gt;&lt;td&gt;The Reserve Bank of India today...&lt;/td&gt;&lt;/tr&gt;&lt;/table&gt;</description>
<link>https://www.rbi.org.in/x</link><pubDate>Fri, 13 Nov 2026 10:20:00</pubDate></item>
</channel></rss>""".encode()

ENTS = [
    nlp.Entity("NSE_EQ|INE002A01018", "RELIANCE", "RELIANCE INDUSTRIES LTD"),
    nlp.Entity("NSE_EQ|INE009A01021", "INFY", "INFOSYS LIMITED"),
    nlp.Entity("NSE_EQ|INE084A01016", "BANKINDIA", "BANK OF INDIA"),
    nlp.Entity("NSE_EQ|INE040A01034", "HDFCBANK", "HDFC BANK LTD"),
    nlp.Entity("NSE_EQ|INE036D01028", "KARURVYSYA", "KARUR VYSYA BANK LTD"),
]


@pytest.fixture
def mapper():
    return nlp.EntityMapper(ENTS, service.ALIASES)


# ---------- sources ----------


def test_parse_nse_feed_extracts_issuer_symbol_subject_time():
    items = parse_rss("nse_announcements", NSE_XML)
    assert len(items) == 4
    r = items[0]
    assert r.company == "Reliance Industries Limited" and r.symbol_hint == "RELIANCE"
    assert r.extra["subject"] == "Financial Result Updates"
    assert r.published_at == datetime(2026, 11, 13, 10, 15, tzinfo=IST)
    assert items[3].published_at is None


def test_parse_rbi_feed_with_bom_and_html():
    (it,) = parse_rss("rbi_press", RBI_XML)
    assert "<" not in it.body and it.published_at == datetime(2026, 11, 13, 10, 20, tzinfo=IST)


@pytest.mark.parametrize(
    "raw,expect",
    [
        ("13-Nov-2026 13:08:37", datetime(2026, 11, 13, 13, 8, 37, tzinfo=IST)),
        ("Fri, 13 Nov 2026 10:20:00", datetime(2026, 11, 13, 10, 20, tzinfo=IST)),
        ("13 Nov 2026 12:00:05 +0530", datetime(2026, 11, 13, 12, 0, 5, tzinfo=IST)),
        ("12 Nov, 2026 +0530", datetime(2026, 11, 12, 0, 0, tzinfo=IST)),  # SEBI date-only format
        ("Fri, 13 Nov 2026 04:50:00 GMT", datetime(2026, 11, 13, 10, 20, tzinfo=IST)),
        ("garbage", None),
        ("", None),
    ],
)
def test_time_formats(raw, expect):
    assert parse_time(raw) == expect


def test_invalid_sources_rejected():
    with pytest.raises(SourceError, match="invalid XML"):
        parse_rss("x", b"<rss><channel><item>")
    with pytest.raises(SourceError, match="not an RSS"):
        parse_rss("x", b"<html><body>blocked</body></html>")
    with pytest.raises(SourceError, match="HTTP 403"):
        fetch("nse_announcements", transport=httpx.MockTransport(lambda r: httpx.Response(403)))
    with pytest.raises(SourceError, match="unknown source"):
        fetch("twitter")


# ---------- entity mapping (regressions from live data) ----------


def test_issuer_by_symbol_then_name(mapper):
    assert mapper.issuer("Whatever", "INFY").symbol == "INFY"
    assert mapper.issuer("Reliance Industries Limited", None).symbol == "RELIANCE"
    assert mapper.issuer("Reliance Mutual Fund", None) is None


def test_reserve_bank_of_india_is_not_bank_of_india(mapper):
    assert mapper.mentions("The Reserve Bank of India keeps repo rate unchanged") == []
    assert [e.symbol for e in mapper.mentions("Bank of India reports Q2 profit")] == ["BANKINDIA"]


def test_multiword_names_matched_single_words_never(mapper):
    assert {e.symbol for e in mapper.mentions("HDFC Bank and Karur Vysya Bank results")} == {
        "HDFCBANK",
        "KARURVYSYA",
    }
    assert mapper.mentions("A bank and a finance company") == []
    # Conservative by design: single words (incl. bare tickers like ITC/LT that collide with ordinary words) are
    # never matched in free text; company filings are mapped by their explicit issuer instead.
    assert mapper.mentions("INFY ADR rises; Infosys up") == []


# ---------- classification ----------


@pytest.mark.parametrize(
    "text,event",
    [
        ("Financial Results for Q2FY27", "earnings"),
        ("Board approves buy back of shares", "buyback"),
        ("Declaration of NAV", "routine_disclosure"),
        ("Scheme of Amalgamation", "merger"),
        ("Monetary Policy Statement repo rate", "macro"),
        ("Resignation of CFO", "management_change"),
        ("Bags order worth Rs 500 crore", "contract"),
        ("Spurt in Volume", "market_activity"),
        ("NCLT admits insolvency petition", "legal"),
        ("Something unrelated", "other"),
    ],
)
def test_event_classification(text, event):
    assert nlp.classify_event(text)[0] == event


# ---------- ingestion: dedup, timestamps, sentiment schema ----------


class StubSentiment:
    version = "stub-1"

    def predict(self, texts):
        out = []
        for t in texts:
            pos = 0.8 if ("Buy back" in t or "Result" in t) else 0.1
            out.append({"positive": pos, "negative": 0.1, "neutral": 1 - pos - 0.1})
        return out


NOW = datetime(2026, 11, 13, 6, 0, tzinfo=UTC)  # 11:30 IST


@pytest.mark.integration
def test_ingest_dedups_maps_validates_and_scores(db, mapper):
    items = parse_rss("nse_announcements", NSE_XML)
    st = service.ingest(db, items, mapper, StubSentiment(), now=NOW)
    assert st["inserted"] == 4 and st["missing_timestamp"] == 1 and st["mapped_to_instrument"] == 2
    again = service.ingest(db, parse_rss("nse_announcements", NSE_XML), mapper, StubSentiment(), now=NOW)
    assert again["duplicates"] == 4 and again["inserted"] == 0
    from app.models.news import NewsItem

    rows = {r.title.split(":")[0]: r for r in db.query(NewsItem)}
    rel = rows["Reliance Industries Limited"]
    assert rel.symbols == ["RELIANCE"] and rel.direct_issuer and rel.event_type == "earnings"
    assert rows["Reliance Mutual Fund - Reliance Interval Fund - QIF"].symbols == []  # live regression
    assert abs(sum(rel.sentiment_probs.values()) - 1) < 1e-9 and -1 <= rel.sentiment_score <= 1
    assert rel.usable_from == NOW  # ingested after publication -> usable from ingestion time
    assert rows["Unknown Smallcap Limited"].timestamp_status == "missing"


@pytest.mark.integration
def test_future_dated_items_rejected_and_never_scored(db, mapper):
    xml = NSE_XML.replace(b"13-Nov-2026 11:00:00", b"14-Nov-2026 11:00:00")
    st = service.ingest(db, parse_rss("nse_announcements", xml), mapper, StubSentiment(), now=NOW)
    assert st["future_rejected"] == 1
    from app.models.news import NewsItem

    infy = db.query(NewsItem).filter(NewsItem.symbols.contains(["INFY"])).one()
    assert infy.timestamp_status == "future_rejected" and infy.sentiment_score is None


@pytest.mark.integration
def test_near_duplicate_linked_and_not_scored(db, mapper):
    xml = NSE_XML.replace(
        b"</channel>",
        b"""<item><title>Infosys Limited</title><link>x</link>
<description>Infosys Limited has informed the Exchange about Buyback |SUBJECT: Buy back</description>
<pubDate>13-Nov-2026 11:00:05</pubDate></item></channel>""",
    )
    st = service.ingest(db, parse_rss("nse_announcements", xml), mapper, StubSentiment(), now=NOW)
    assert st["near_duplicates"] == 1
    from app.models.news import NewsItem

    dup = db.query(NewsItem).filter(NewsItem.duplicate_of.is_not(None)).one()
    assert dup.sentiment_score is None and db.get(NewsItem, dup.duplicate_of).symbols == ["INFY"]


# ---------- point-in-time signal ----------


@pytest.mark.integration
def test_signal_is_point_in_time(db, mapper):
    service.ingest(db, parse_rss("nse_announcements", NSE_XML), mapper, StubSentiment(), now=NOW)
    key = "NSE_EQ|INE002A01018"
    before = service.signal_for(db, key, NOW - timedelta(minutes=1))
    assert before["items"] == 0 and before["sentiment"] == 0.0 and before["confidence"] == 0.0
    at = service.signal_for(db, key, NOW)
    assert at["items"] == 1 and at["sentiment"] == pytest.approx(0.7) and at["confidence"] > 0
    later = service.signal_for(db, key, NOW + timedelta(hours=24))
    assert later["impact"] < at["impact"]  # freshness decay (half-life 24h)
    assert service.signal_for(db, key, NOW + timedelta(hours=100))["items"] == 0  # outside lookback
    other = service.signal_for(db, "NSE_EQ|INE040A01034", NOW)  # HDFCBANK: company news of others ignored
    assert other["items"] == 0


@pytest.mark.integration
def test_market_news_applies_to_all_stocks(db, mapper):
    service.ingest(db, parse_rss("rbi_press", RBI_XML), mapper, StubSentiment(), now=NOW)
    sig = service.signal_for(db, "NSE_EQ|INE040A01034", NOW)
    assert sig["items"] == 1 and sig["top"][0]["event"] == "macro"


def test_freshness_and_relevance():
    t = datetime(2026, 1, 1, tzinfo=UTC)
    assert nlp.freshness(t, t) == 1.0 and nlp.freshness(t, t + timedelta(hours=24)) == pytest.approx(0.5)
    assert nlp.freshness(t + timedelta(hours=1), t) == 0.0  # future relative to as_of
    assert nlp.relevance("company", True, 1) == 1.0 and nlp.relevance("market", False, 0) == 0.4


# ---------- real FinBERT (slow; downloads/loads the safetensors weights once) ----------


@pytest.mark.slow
def test_finbert_real_model_schema_and_direction(tmp_path):
    from app.core.config import get_settings

    fb = nlp.FinBERT(get_settings().artifacts_dir / "hf")
    p = fb.predict(["Net profit rises 40% beating estimates", "Company defaults on loan repayment"])
    assert all(set(x) == {"positive", "negative", "neutral"} and abs(sum(x.values()) - 1) < 1e-4 for x in p)
    assert nlp.sentiment_score(p[0]) > 0.5 and nlp.sentiment_score(p[1]) < -0.5

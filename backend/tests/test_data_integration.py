"""Data engine against the real test Postgres + Redis, with Upstox HTTP served by fixtures."""

import gzip
import json
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

import httpx
import pytest
from sqlalchemy import select

from app.core.config import get_settings
from app.engines.data import instruments as ins
from app.engines.data.downloader import HistoricalDownloader
from app.engines.data.ratelimit import MultiWindowLimiter
from app.engines.data.storage import CandleLake
from app.engines.data.upstox import auth
from app.engines.data.upstox.client import UpstoxAuthError, UpstoxClient
from app.models.data import BrokerToken, CandleFile, DownloadChunk, Instrument, UniverseMember
from tests.fixtures.upstox_fake import FakeUpstox

pytestmark = pytest.mark.integration
FIXTURE = Path(__file__).parent / "fixtures" / "NSE_master_subset.json.gz"
REL = "NSE_EQ|INE002A01018"


def _seed_master(db):
    rows = ins.parse_master(FIXTURE.read_bytes())
    ins.upsert_instruments(db, rows)
    return rows


def _downloader(db, lake_dir, fake, overlap=7):
    client = UpstoxClient(
        "https://api.upstox.com",
        MultiWindowLimiter([(10_000, 1.0)]),
        transport=fake.transport(),
        max_retries=2,
        sleep=lambda s: None,
    )
    lake = CandleLake(lake_dir, db)
    return HistoricalDownloader(db, client, lake, overlap_days=overlap), lake, client


# ---------- instrument master + universe ----------


def test_parse_master_keeps_only_equities_and_indices():
    rows = ins.parse_master(FIXTURE.read_bytes())
    raw = json.loads(gzip.decompress(FIXTURE.read_bytes()))
    assert len(raw) > len(rows)  # F&O and non-EQ series dropped
    assert {r["segment"] for r in rows} == {"NSE_EQ", "NSE_INDEX"}
    assert all(r["instrument_type"] == "EQ" for r in rows if r["segment"] == "NSE_EQ")


def test_upsert_is_idempotent(db):
    rows = _seed_master(db)
    _seed_master(db)
    assert db.query(Instrument).count() == len(rows)


def test_universe_maps_all_50_by_isin(db):
    _seed_master(db)
    members = ins.map_universe(db)
    assert len(members) == 50
    rel = db.scalars(select(UniverseMember).filter_by(symbol="RELIANCE")).one()
    assert rel.instrument_key == REL and rel.sector_index_key == "NSE_INDEX|NIFTY OIL AND GAS"
    assert {m.symbol for m in members} >= {"RELIANCE", "HDFCBANK", "INFY"}


def test_universe_mapping_rejects_symbol_mismatch(db):
    _seed_master(db)
    db.get(Instrument, REL).trading_symbol = "RELIANCEX"
    db.commit()
    with pytest.raises(ins.MappingError, match="RELIANCE: master trading_symbol is RELIANCEX"):
        ins.map_universe(db)


def test_universe_mapping_rejects_missing_isin(db):
    _seed_master(db)
    db.delete(db.get(Instrument, REL))
    db.commit()
    with pytest.raises(ins.MappingError, match="INE002A01018 not in instrument master"):
        ins.map_universe(db)


def test_resolve_never_invents_keys(db):
    _seed_master(db)
    assert ins.resolve(db, "infy").instrument_key == "NSE_EQ|INE009A01021"
    assert ins.resolve(db, "NSE_INDEX|Nifty 50").segment == "NSE_INDEX"
    with pytest.raises(ins.MappingError):
        ins.resolve(db, "NOTASTOCK")
    with pytest.raises(ins.MappingError):
        ins.resolve(db, "NSE_EQ|INE000000000")


# ---------- downloader ----------


def test_full_download_batches_by_month(db, lake_dir):
    fake = FakeUpstox()
    dl, lake, client = _downloader(db, lake_dir, fake)
    r = dl.download(REL, "1minute", date(2024, 1, 15), date(2024, 3, 10))
    assert (r.chunks_planned, r.chunks_fetched, r.chunks_failed) == (3, 3, 0)
    expected_days = sum(
        1
        for i in range((date(2024, 3, 10) - date(2024, 1, 15)).days + 1)
        if (date(2024, 1, 15) + timedelta(i)).weekday() < 5
    )
    assert r.rows_stored == expected_days * 375
    assert client.requests_made == 3
    assert db.query(DownloadChunk).filter_by(status="done").count() == 3
    files = db.scalars(select(CandleFile).filter_by(instrument_key=REL)).all()
    assert len(files) == 1 and files[0].rows == r.rows_stored and len(files[0].sha256) == 64


def test_resume_retries_failed_chunk(db, lake_dir):
    fake = FakeUpstox()
    fake.fail = lambda req: (
        httpx.Response(503) if "/2024-02-29/2024-02-01" in req.url.raw_path.decode() else None
    )
    dl, lake, _ = _downloader(db, lake_dir, fake)
    r1 = dl.download(REL, "1minute", date(2024, 1, 1), date(2024, 3, 31))
    assert (r1.chunks_fetched, r1.chunks_failed) == (2, 1)
    failed = db.scalars(select(DownloadChunk).filter_by(status="failed")).one()
    assert (failed.from_date, failed.to_date, failed.attempts) == (date(2024, 2, 1), date(2024, 2, 29), 1)

    fake.fail = lambda req: None  # provider recovers
    fake.requests.clear()
    r2 = dl.download(REL, "1minute", date(2024, 1, 1), date(2024, 3, 31))
    assert r2.chunks_retried == 1 and r2.chunks_failed == 0
    assert any("/2024-02-29/2024-02-01" in q.url.raw_path.decode() for q in fake.requests)
    assert db.query(DownloadChunk).filter_by(status="failed").count() == 0
    df = lake.read("1minute", REL)
    assert df["ts"].dt.month.unique().tolist() == [1, 2, 3]


def test_incremental_fetches_only_overlap_and_adds_no_duplicates(db, lake_dir):
    fake = FakeUpstox()
    dl, lake, _ = _downloader(db, lake_dir, fake, overlap=3)
    dl.download(REL, "1minute", date(2024, 1, 1), date(2024, 2, 15))
    before = len(lake.read("1minute", REL))
    fake.requests.clear()
    r = dl.download(REL, "1minute", date(2024, 1, 1), date(2024, 2, 20))
    assert len(fake.requests) == 1
    assert "/2024-02-20/2024-02-12" in fake.requests[0].url.raw_path.decode()  # last day 02-15 minus 3 days
    df = lake.read("1minute", REL)
    assert df["ts"].is_unique and len(df) == before + 3 * 375  # Feb 16 (Fri), 19, 20
    assert not r.drift_detected


def test_adjustment_drift_triggers_full_refresh(db, lake_dir):
    dl, lake, _ = _downloader(db, lake_dir, FakeUpstox(scale=1.0))
    dl.download(REL, "1day", date(2024, 1, 1), date(2024, 6, 28))
    old = lake.read("1day", REL)
    # Provider now returns prices halved (e.g. a 1:1 bonus applied retroactively).
    dl2, lake2, _ = _downloader(db, lake_dir, FakeUpstox(scale=0.5))
    r = dl2.download(REL, "1day", date(2024, 1, 1), date(2024, 7, 5))
    assert r.drift_detected and r.full_refresh
    new = lake2.read("1day", REL)
    assert len(new) == len(old) + 5
    assert new["close"].iloc[0] == pytest.approx(old["close"].iloc[0] * 0.5, rel=1e-3)


def test_auth_error_stops_and_is_checkpointed(db, lake_dir):
    fake = FakeUpstox()
    fake.fail = lambda req: httpx.Response(401)
    dl, _, _ = _downloader(db, lake_dir, fake)
    with pytest.raises(UpstoxAuthError):
        dl.download(REL, "1day", date(2024, 1, 1), date(2024, 1, 31))
    assert db.scalars(select(DownloadChunk)).one().last_error == "auth"


def test_empty_response_recorded_as_empty(db, lake_dir):
    dl, lake, _ = _downloader(db, lake_dir, FakeUpstox())
    r = dl.download(REL, "1minute", date(2024, 6, 1), date(2024, 6, 2))  # weekend only
    assert r.chunks_empty == 1 and r.rows_stored == 0
    assert db.scalars(select(DownloadChunk)).one().status == "empty"


# ---------- OAuth state + token store ----------


def test_oauth_state_is_single_use():
    from app.core.redis import get_redis

    r = get_redis()
    st = auth.new_state(r)
    assert auth.consume_state(r, st) is True
    assert auth.consume_state(r, st) is False
    assert auth.consume_state(r, None) is False
    assert auth.consume_state(r, "forged") is False


def test_token_store_encrypts_and_expires(db):
    s = get_settings()
    store = auth.TokenStore(db, s)
    issued = datetime(2026, 11, 13, 14, 0, tzinfo=UTC)  # 19:30 IST
    store.save("secret-access-token", "U123", now=issued)
    row = db.scalars(select(BrokerToken)).one()
    assert "secret-access-token" not in row.token_encrypted
    assert store.access_token(now=issued + timedelta(hours=1)) == "secret-access-token"
    assert store.access_token(now=datetime(2026, 11, 13, 22, 1, tzinfo=UTC)) is None  # past 03:30 IST


def test_new_token_revokes_previous(db):
    store = auth.TokenStore(db, get_settings())
    store.save("a", "U1")
    store.save("b", "U1")
    assert store.access_token() == "b"
    assert db.query(BrokerToken).filter_by(revoked=True).count() == 1


def test_exchange_code_posts_documented_form(monkeypatch):
    s = get_settings().model_copy(
        update={
            "upstox_api_key": "key",
            "upstox_api_secret": "sec",
            "upstox_redirect_uri": "http://localhost:8000/cb",
        }
    )
    s = s.model_copy(
        update={
            k: __import__("pydantic").SecretStr(v)
            for k, v in (("upstox_api_key", "key"), ("upstox_api_secret", "sec"))
        }
    )
    seen = {}

    def h(req: httpx.Request):
        seen["path"], seen["ct"], seen["body"] = (
            req.url.path,
            req.headers["content-type"],
            req.content.decode(),
        )
        return httpx.Response(200, json={"access_token": "AT", "user_id": "U1"})

    body = auth.exchange_code(s, "CODE", transport=httpx.MockTransport(h))
    assert body["access_token"] == "AT"
    assert seen["path"] == "/v2/login/authorization/token"
    assert seen["ct"] == "application/x-www-form-urlencoded"
    for part in ("code=CODE", "client_id=key", "client_secret=sec", "grant_type=authorization_code"):
        assert part in seen["body"]
    url = auth.authorize_url(s, "STATE")
    assert url.startswith(auth.AUTHORIZE_URL) and "response_type=code" in url and "state=STATE" in url

    with pytest.raises(auth.OAuthError):
        auth.exchange_code(s, "CODE", transport=httpx.MockTransport(lambda r: httpx.Response(400, json={})))

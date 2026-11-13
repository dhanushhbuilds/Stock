from datetime import date
from pathlib import Path

import pytest

from app.core.config import get_settings
from app.engines.data import instruments as ins
from app.engines.data.candles import parse_candles
from app.engines.data.service import run_quality
from app.engines.data.storage import CandleLake
from app.models import AuditEvent
from tests.fixtures.upstox_fake import daily_candle, trading_days

pytestmark = pytest.mark.integration
FIXTURE = Path(__file__).parent / "fixtures" / "NSE_master_subset.json.gz"
REL = "NSE_EQ|INE002A01018"


@pytest.fixture
def seeded(db):
    ins.upsert_instruments(db, ins.parse_master(FIXTURE.read_bytes()))
    ins.map_universe(db)
    lake = CandleLake(get_settings().data_dir, db)
    lake.delete("1day", REL)
    days = trading_days(date(2024, 1, 1), date(2024, 3, 29))
    lake.write(parse_candles([daily_candle(d) for d in days]), "1day", REL)
    return db, lake, days


def test_universe_endpoint(client, seeded):
    r = client.get("/api/v1/data/universe")
    assert r.status_code == 200 and len(r.json()) == 50
    assert {"symbol": "INFY", "instrument_key": "NSE_EQ|INE009A01021"}.items() <= next(
        m for m in r.json() if m["symbol"] == "INFY"
    ).items()


def test_instrument_search(client, seeded):
    r = client.get("/api/v1/data/instruments", params={"q": "nifty bank", "segment": "NSE_INDEX"})
    assert [x["instrument_key"] for x in r.json()] == ["NSE_INDEX|Nifty Bank"]


def test_candles_by_symbol_and_key(client, seeded):
    _, _, days = seeded
    a = client.get("/api/v1/data/candles/RELIANCE", params={"timeframe": "1day"}).json()
    b = client.get(f"/api/v1/data/candles/{REL}", params={"timeframe": "1day"}).json()
    assert a == b and a["count"] == len(days) and a["truncated"] is False
    assert a["candles"][0]["ts"].startswith("2024-01-01T00:00:00+05:30")


def test_candles_range_and_limit(client, seeded):
    r = client.get(
        "/api/v1/data/candles/RELIANCE", params={"start": "2024-02-01", "end": "2024-02-29", "limit": 5}
    ).json()
    assert r["count"] == 5 and r["truncated"] is True
    assert r["candles"][-1]["ts"].startswith("2024-02-29")


def test_candles_errors(client, seeded):
    assert client.get("/api/v1/data/candles/NOTREAL").status_code == 404
    assert client.get("/api/v1/data/candles/RELIANCE", params={"timeframe": "7minute"}).status_code == 422
    assert (
        client.get(
            "/api/v1/data/candles/RELIANCE", params={"start": "2024-03-01", "end": "2024-02-01"}
        ).status_code
        == 422
    )


def test_coverage_and_quality(client, seeded):
    db, lake, days = seeded
    assert client.get(f"/api/v1/data/quality/{REL}").status_code == 404
    cov = [c for c in client.get("/api/v1/data/coverage").json() if c["instrument_key"] == REL][0]
    assert cov["rows"] == len(days) and cov["quality_passed"] is None
    run_quality(db, lake, REL, "1day", set(days))
    q = client.get(f"/api/v1/data/quality/{REL}").json()
    assert q["passed"] is True and q["rows"] == len(days)
    cov = [c for c in client.get("/api/v1/data/coverage").json() if c["instrument_key"] == REL][0]
    assert cov["quality_passed"] is True


def test_upstox_status_and_login_without_credentials(client, db):
    st = client.get("/api/v1/auth/upstox/status").json()
    assert st == {
        "configured": False,
        "connected": False,
        "broker_user_id": None,
        "expires_at": None,
        "historical_data_requires_token": False,
    }
    assert client.get("/api/v1/auth/upstox/login", follow_redirects=False).status_code == 503


def test_callback_rejects_forged_state_and_audits(client, db):
    r = client.get(
        "/api/v1/auth/upstox/callback", params={"code": "x", "state": "forged"}, follow_redirects=False
    )
    assert r.status_code == 303 and r.headers["location"].endswith("/settings?upstox=invalid_state")
    ev = db.query(AuditEvent).filter_by(event_type="upstox_oauth_rejected").one()
    assert ev.payload == {"reason": "invalid_state"}


def test_ml_and_strategy_read_endpoints(client, db):
    assert client.get("/api/v1/ml/models").json() == []
    assert client.get("/api/v1/ml/experiments/nope").status_code == 404
    names = {s["name"] for s in client.get("/api/v1/strategies").json()}
    assert len(names) == 10 and {"ema_crossover", "opening_range_breakout"} <= names
    r = client.get("/api/v1/strategies/report")
    assert r.status_code in (200, 404)
    if r.status_code == 200:
        assert "_benchmark_equal_weight_buy_hold" in r.json()


def test_openapi_documents_every_engine(client):
    paths = client.get("/api/openapi.json").json()["paths"]
    for prefix in ("/api/v1/data/", "/api/v1/ml/", "/api/v1/news", "/api/v1/strategies", "/api/v1/risk/",
                   "/api/v1/decisions", "/api/v1/health"):
        assert any(p.startswith(prefix) for p in paths), prefix

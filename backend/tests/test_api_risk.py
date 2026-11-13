from datetime import UTC, datetime

import pytest

from app.models import AuditEvent, RiskAssessment

pytestmark = pytest.mark.integration


def _req(**intent_kw):
    now = datetime.now(UTC).isoformat()
    return {
        "intent": {
            "intent_id": "t-1",
            "instrument_key": "NSE_EQ|INE002A01018",
            "side": "BUY",
            "product": "INTRADAY",
            "entry_price": 1000,
            "stop_price": 990,
            "confidence": 0.6,
            "created_at": now,
            **intent_kw,
        },
        "market": {"instrument_key": "NSE_EQ|INE002A01018", "last_price": 1000, "atr": 5, "data_ts": now},
        "portfolio": {"equity": 1e6, "cash": 1e6, "start_of_day_equity": 1e6, "peak_equity": 1e6},
    }


def test_evaluate_logs_every_decision(client, db):
    r = client.post("/api/v1/risk/evaluate", json=_req())
    assert r.status_code == 200 and r.json()["approved"] is True and r.json()["quantity"] == 100
    r2 = client.post("/api/v1/risk/evaluate", json=_req(confidence=0.1))
    assert r2.json()["approved"] is False
    rows = db.query(RiskAssessment).order_by(RiskAssessment.id).all()
    assert [x.approved for x in rows] == [True, False]
    assert db.query(AuditEvent).filter_by(event_type="order_rejected").count() == 1


def test_kill_switch_blocks_then_releases(client, db):
    assert client.post("/api/v1/risk/kill-switch", json={"on": True, "reason": "test halt"}).json()[
        "kill_switch"
    ]
    v = client.post("/api/v1/risk/evaluate", json=_req()).json()
    assert v["approved"] is False and any("kill_switch_off" in r for r in v["reasons"])
    assert client.get("/api/v1/risk/state").json()["kill_switch"] is True
    client.post("/api/v1/risk/kill-switch", json={"on": False, "reason": "resume"})
    assert client.post("/api/v1/risk/evaluate", json=_req()).json()["approved"] is True
    assert db.query(AuditEvent).filter_by(event_type="kill_switch_on").count() == 1


def test_limits_update_validated_and_applied(client, db):
    assert client.put("/api/v1/risk/limits", json={"risk_per_trade_pct": 0.5}).status_code == 422  # > 5%
    lim = client.put("/api/v1/risk/limits", json={"min_confidence": 0.7}).json()
    assert lim["min_confidence"] == 0.7
    assert client.post("/api/v1/risk/evaluate", json=_req()).json()["approved"] is False


def test_invalid_payloads_rejected(client, db):
    bad = _req()
    bad["market"]["last_price"] = "NaN"
    assert client.post("/api/v1/risk/evaluate", json=bad).status_code == 422
    assert client.post("/api/v1/risk/evaluate", json=_req(side="SELL", product="DELIVERY")).status_code == 422

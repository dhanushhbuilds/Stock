import pytest
import redis

pytestmark = pytest.mark.integration


def test_liveness(client):
    r = client.get("/api/v1/health")
    assert r.status_code == 200 and r.json() == {"status": "ok"}


def test_readiness_reports_real_db_and_redis(client):
    r = client.get("/api/v1/health/ready")
    body = r.json()
    assert r.status_code == 200, body
    assert body["status"] == "ok"
    assert body["checks"]["database"]["status"] == "ok"
    assert body["checks"]["database"]["detail"].startswith("migration=")
    assert body["checks"]["redis"]["status"] == "ok"
    assert body["live_trading_enabled"] is False
    assert body["checks"]["upstox"]["status"] in {"ok", "not_configured"}


def test_readiness_degrades_when_redis_down(client, monkeypatch):
    dead = redis.Redis.from_url("redis://localhost:1/0", socket_connect_timeout=0.2)
    monkeypatch.setattr("app.api.health.get_redis", lambda: dead)
    r = client.get("/api/v1/health/ready")
    assert r.status_code == 503
    assert r.json()["status"] == "degraded"
    assert r.json()["checks"]["redis"]["status"] == "error"


def test_request_id_propagated(client):
    r = client.get("/api/v1/health", headers={"x-request-id": "abc123"})
    assert r.headers["x-request-id"] == "abc123"


def test_cors_allows_frontend_origin(client):
    r = client.options(
        "/api/v1/health", headers={"Origin": "http://localhost:5173", "Access-Control-Request-Method": "GET"}
    )
    assert r.headers.get("access-control-allow-origin") == "http://localhost:5173"


def test_unknown_route_404(client):
    assert client.get("/api/v1/nope").status_code == 404


def test_validation_error_with_exception_context_is_422_not_500(client):
    """Regression: a pydantic validator raising ValueError put an exception object into errors(); the handler
    crashed with 500 while serialising it."""
    r = client.post(
        "/api/v1/risk/evaluate", json={"intent": {}, "market": {"last_price": "NaN"}, "portfolio": {}}
    )
    assert r.status_code == 422 and r.json()["error"] == "validation_error"

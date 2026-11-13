import pytest
from pydantic import ValidationError

from app.core.config import Settings

BASE = dict(postgres_user="u", postgres_password="p", postgres_db="d", jwt_secret="x" * 40)


def make(**kw) -> Settings:
    return Settings(_env_file=None, **{**BASE, **kw})


def test_cors_origins_comma_separated():
    assert make(cors_origins="http://a:1, http://b:2").cors_origins == ["http://a:1", "http://b:2"]


def test_live_trading_cannot_be_enabled():
    with pytest.raises(ValidationError, match="LIVE_TRADING_ENABLED"):
        make(live_trading_enabled=True)


def test_short_jwt_secret_rejected():
    with pytest.raises(ValidationError, match="JWT_SECRET"):
        make(jwt_secret="short")


def test_empty_upstox_credentials_mean_not_configured():
    s = make(upstox_api_key="", upstox_api_secret="", upstox_redirect_uri="http://x")
    assert s.upstox_api_key is None
    assert s.upstox_configured is False


def test_secrets_not_in_repr():
    s = make(postgres_password="hunter2-secret")
    assert "hunter2-secret" not in repr(s)
    assert "hunter2-secret" in s.database_url()  # only revealed where actually needed

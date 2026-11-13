"""Test setup: run against a dedicated `astraquant_test` database and Redis db 15, never the dev data."""

import os
import tempfile

TEST_DB = os.environ.get("TEST_POSTGRES_DB", "astraquant_test")  # each parallel track uses its own
os.environ["POSTGRES_DB"] = TEST_DB
os.environ["APP_ENV"] = "test"
os.environ["REDIS_URL"] = os.environ.get("TEST_REDIS_URL", "redis://localhost:6380/15")
os.environ["DATA_DIR"] = tempfile.mkdtemp(prefix="astraquant-test-lake-")  # never the real lake
os.environ["ARTIFACTS_DIR"] = tempfile.mkdtemp(prefix="astraquant-test-artifacts-")  # never the real registry
os.environ["TOKEN_ENCRYPTION_KEY"] = "dGVzdC1rZXktdGVzdC1rZXktdGVzdC1rZXktdGVzdDA="  # test-only Fernet key
for _k in ("UPSTOX_API_KEY", "UPSTOX_API_SECRET"):
    os.environ[_k] = ""

import pytest  # noqa: E402
from alembic import command  # noqa: E402
from alembic.config import Config  # noqa: E402
from sqlalchemy import create_engine, text  # noqa: E402

from app.core.config import BACKEND_DIR, get_settings  # noqa: E402


def alembic_config() -> Config:
    cfg = Config(str(BACKEND_DIR / "alembic.ini"))
    cfg.set_main_option("script_location", str(BACKEND_DIR / "alembic"))
    cfg.attributes["url"] = get_settings().database_url(TEST_DB)
    cfg.attributes["configure_logger"] = False
    return cfg


@pytest.fixture(scope="session", autouse=True)
def test_database():
    s = get_settings()
    admin = create_engine(s.database_url("postgres"), isolation_level="AUTOCOMMIT")
    with admin.connect() as c:
        c.execute(text(f"DROP DATABASE IF EXISTS {TEST_DB} WITH (FORCE)"))
        c.execute(text(f"CREATE DATABASE {TEST_DB}"))
    admin.dispose()
    command.upgrade(alembic_config(), "head")
    yield
    from app.core.db import get_engine

    get_engine().dispose()


@pytest.fixture
def client():
    from fastapi.testclient import TestClient

    from app.main import create_app

    with TestClient(create_app()) as c:
        yield c


DATA_TABLES = (
    "universe_members",
    "instruments",
    "broker_tokens",
    "download_chunks",
    "candle_files",
    "data_quality_reports",
    "audit_events",
    "risk_state",
    "risk_assessments",
    "news_items",
    "decisions",
)


@pytest.fixture
def db():
    """A session on the test DB with all data tables emptied first."""
    from app.core.db import get_session

    session = next(get_session())
    session.execute(text(f"TRUNCATE {', '.join(DATA_TABLES)} RESTART IDENTITY CASCADE"))
    session.commit()
    yield session
    session.close()


@pytest.fixture
def lake_dir(tmp_path):
    return tmp_path / "lake"

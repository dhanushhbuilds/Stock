"""Test setup: run against a dedicated `astraquant_test` database and Redis db 15, never the dev data."""

import os

os.environ["POSTGRES_DB"] = "astraquant_test"
os.environ["APP_ENV"] = "test"
os.environ["REDIS_URL"] = os.environ.get("TEST_REDIS_URL", "redis://localhost:6380/15")

import pytest  # noqa: E402
from alembic import command  # noqa: E402
from alembic.config import Config  # noqa: E402
from sqlalchemy import create_engine, text  # noqa: E402

from app.core.config import BACKEND_DIR, get_settings  # noqa: E402

TEST_DB = "astraquant_test"


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

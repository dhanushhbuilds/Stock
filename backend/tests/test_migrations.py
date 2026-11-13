import pytest
from alembic import command
from alembic.autogenerate import compare_metadata
from alembic.migration import MigrationContext
from sqlalchemy import create_engine, inspect

import app.models  # noqa: F401
from app.core.db import Base
from tests.conftest import alembic_config

pytestmark = pytest.mark.integration


def _engine():
    return create_engine(alembic_config().attributes["url"])


def test_models_match_migrations():
    eng = _engine()
    with eng.connect() as conn:
        diff = compare_metadata(MigrationContext.configure(conn), Base.metadata)
    eng.dispose()
    assert diff == [], f"ORM models and migrations differ: {diff}"


def test_downgrade_then_upgrade_roundtrip():
    cfg = alembic_config()
    command.downgrade(cfg, "base")
    eng = _engine()
    assert "audit_events" not in inspect(eng).get_table_names()
    command.upgrade(cfg, "head")
    assert "audit_events" in inspect(eng).get_table_names()
    eng.dispose()

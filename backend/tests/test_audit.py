import pytest
from sqlalchemy import select

from app.core.audit import record
from app.core.db import get_session
from app.models import AuditEvent

pytestmark = pytest.mark.integration


def test_audit_event_persisted_and_scrubbed():
    session = next(get_session())
    ev = record(session, "system", "test_event", {"note": "hi", "api_secret": "must-not-store"})
    row = session.scalars(select(AuditEvent).where(AuditEvent.id == ev.id)).one()
    assert row.payload == {"note": "hi", "api_secret": "[REDACTED]"}
    assert row.ts is not None
    session.close()

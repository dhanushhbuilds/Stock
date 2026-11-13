"""Helper for writing audit events."""

from typing import Any

from sqlalchemy.orm import Session

from app.core.logging import _scrub, get_logger
from app.models.audit import AuditEvent

log = get_logger(__name__)


def record(
    session: Session, engine: str, event_type: str, payload: dict[str, Any], actor: str = "system"
) -> AuditEvent:
    """Persist an audit event (secrets scrubbed) and commit."""
    ev = AuditEvent(engine=engine, event_type=event_type, actor=actor, payload=_scrub(payload))
    session.add(ev)
    session.commit()
    log.info("audit", engine=engine, event_type=event_type, audit_id=ev.id)
    return ev

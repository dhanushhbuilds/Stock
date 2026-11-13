"""Upstox OAuth endpoints. The access token never leaves the backend."""

from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import RedirectResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.core.audit import record
from app.core.config import get_settings
from app.core.db import get_session
from app.core.redis import get_redis
from app.engines.data.upstox import auth

router = APIRouter(prefix="/auth/upstox", tags=["auth"])
SessionDep = Annotated[Session, Depends(get_session)]


class UpstoxStatus(BaseModel):
    configured: bool
    connected: bool
    broker_user_id: str | None = None
    expires_at: datetime | None = None
    historical_data_requires_token: bool = (
        False  # verified 2026-11-13: V3 historical candles work without one
    )


@router.get("/status", response_model=UpstoxStatus)
def status(session: SessionDep):
    s = get_settings()
    cur = auth.TokenStore(session, s).current() if s.token_encryption_key else None
    return UpstoxStatus(
        configured=s.upstox_configured,
        connected=cur is not None,
        broker_user_id=cur.broker_user_id if cur else None,
        expires_at=cur.expires_at if cur else None,
    )


@router.get("/login")
def login():
    s = get_settings()
    if not s.upstox_configured:
        raise HTTPException(503, "Upstox API key/secret/redirect URI not configured in .env")
    return RedirectResponse(auth.authorize_url(s, auth.new_state(get_redis())), status_code=307)


@router.get("/callback")
def callback(session: SessionDep, code: str | None = None, state: str | None = None):
    s = get_settings()
    back = f"{s.frontend_url}/settings"
    if not auth.consume_state(get_redis(), state):
        record(session, "data", "upstox_oauth_rejected", {"reason": "invalid_state"})
        return RedirectResponse(f"{back}?upstox=invalid_state", status_code=303)
    if not code:
        return RedirectResponse(f"{back}?upstox=missing_code", status_code=303)
    try:
        body = auth.exchange_code(s, code)
        row = auth.TokenStore(session, s).save(body["access_token"], body.get("user_id"))
    except auth.OAuthError as exc:
        record(session, "data", "upstox_oauth_failed", {"error": str(exc)})
        return RedirectResponse(f"{back}?upstox=failed", status_code=303)
    record(
        session,
        "data",
        "upstox_connected",
        {"broker_user_id": row.broker_user_id, "expires_at": row.expires_at.isoformat()},
    )
    return RedirectResponse(f"{back}?upstox=connected", status_code=303)

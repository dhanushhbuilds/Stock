"""Liveness and readiness endpoints."""

import time
from typing import Literal

from fastapi import APIRouter, Response
from pydantic import BaseModel
from sqlalchemy import text

from app import __version__
from app.core.config import get_settings
from app.core.db import get_engine
from app.core.redis import get_redis

router = APIRouter(tags=["system"])


class Check(BaseModel):
    status: Literal["ok", "error", "not_configured"]
    latency_ms: float | None = None
    detail: str | None = None


class Readiness(BaseModel):
    status: Literal["ok", "degraded"]
    version: str
    env: str
    live_trading_enabled: bool
    checks: dict[str, Check]


def _timed(fn) -> Check:
    t0 = time.perf_counter()
    try:
        detail = fn()
        return Check(status="ok", latency_ms=round((time.perf_counter() - t0) * 1000, 2), detail=detail)
    except Exception as exc:  # report, never raise from a health check
        return Check(
            status="error", latency_ms=round((time.perf_counter() - t0) * 1000, 2), detail=type(exc).__name__
        )


def _db() -> str:
    with get_engine().connect() as conn:
        rev = conn.execute(text("select version_num from alembic_version")).scalar_one_or_none()
    return f"migration={rev}"


def _redis() -> str:
    get_redis().ping()
    return "pong"


@router.get("/health")
def liveness() -> dict[str, str]:
    return {"status": "ok"}


@router.get("/health/ready", response_model=Readiness)
def readiness(response: Response) -> Readiness:
    s = get_settings()
    checks = {
        "database": _timed(_db),
        "redis": _timed(_redis),
        "upstox": Check(
            status="ok" if s.upstox_configured else "not_configured",
            detail=None if s.upstox_configured else "UPSTOX_API_KEY/SECRET missing",
        ),
    }
    core_ok = checks["database"].status == "ok" and checks["redis"].status == "ok"
    if not core_ok:
        response.status_code = 503
    return Readiness(
        status="ok" if core_ok else "degraded",
        version=__version__,
        env=s.app_env,
        live_trading_enabled=s.live_trading_enabled,
        checks=checks,
    )

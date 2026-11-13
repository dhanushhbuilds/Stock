"""FastAPI application factory."""

import time
import uuid

import structlog
from fastapi import FastAPI, Request
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app import __version__
from app.api import data, decisions, health, ml, news, risk, signal_lab, upstox_auth
from app.core.config import get_settings
from app.core.logging import configure_logging, get_logger

log = get_logger("http")


def create_app() -> FastAPI:
    s = get_settings()
    configure_logging(s.log_level, json=s.app_env != "development")

    app = FastAPI(
        title="AstraQuant X-2026 API",
        version=__version__,
        docs_url="/api/docs",
        openapi_url="/api/openapi.json",
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=s.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.middleware("http")
    async def request_context(request: Request, call_next):
        rid = request.headers.get("x-request-id") or uuid.uuid4().hex[:16]
        structlog.contextvars.bind_contextvars(request_id=rid)
        t0 = time.perf_counter()
        try:
            response = await call_next(request)
        finally:
            structlog.contextvars.clear_contextvars()
        ms = round((time.perf_counter() - t0) * 1000, 2)
        response.headers["x-request-id"] = rid
        log.info(
            "request",
            method=request.method,
            path=request.url.path,
            status=response.status_code,
            duration_ms=ms,
            request_id=rid,
        )
        return response

    @app.exception_handler(RequestValidationError)
    async def validation_error(_req: Request, exc: RequestValidationError):
        # errors() can contain exception objects in "ctx"; encode them as strings instead of crashing with a 500.
        detail = jsonable_encoder(exc.errors(), custom_encoder={Exception: str})
        return JSONResponse(status_code=422, content={"error": "validation_error", "detail": detail})

    @app.exception_handler(Exception)
    async def unhandled(_req: Request, exc: Exception):
        log.exception("unhandled_error", error=type(exc).__name__)
        return JSONResponse(status_code=500, content={"error": "internal_error"})

    app.include_router(health.router, prefix="/api/v1")
    app.include_router(data.router, prefix="/api/v1")
    app.include_router(upstox_auth.router, prefix="/api/v1")
    app.include_router(risk.router, prefix="/api/v1")
    app.include_router(news.router, prefix="/api/v1")
    app.include_router(decisions.router, prefix="/api/v1")
    app.include_router(ml.router, prefix="/api/v1")
    app.include_router(signal_lab.router, prefix="/api/v1")
    return app


app = create_app()

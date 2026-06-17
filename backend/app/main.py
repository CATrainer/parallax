"""Parallax API — app factory, router mounting, CORS, global error handling (§8, BUILD_SPEC).

Every response is the standard envelope (§8.1). The global exception handler returns a clean
``err("INTERNAL", ...)`` with no stack and no PII (§12). In ``local`` we optionally create tables
on startup for convenience; production uses Alembic.
"""
from __future__ import annotations

import os
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.core.config import settings
from app.core.db import Base, engine
from app.core.logging import configure_logging, get_logger
from app.schemas.common import err

# Importing the models module ensures all tables register on Base.metadata.
import app.models.entities  # noqa: F401

from app.api.routers import (
    auth as auth_router,
    briefings as briefings_router,
    broker as broker_router,
    patch as patch_router,
    search as search_router,
    sites as sites_router,
    usage as usage_router,
    validate as validate_router,
    watchlist as watchlist_router,
)

log = get_logger("parallax.main")


@asynccontextmanager
async def lifespan(app: FastAPI):
    configure_logging()
    log.info("parallax_startup", environment=settings.environment, data_mode=settings.data_mode)
    # Idempotent schema + extension bootstrap. Safe on a greenfield single-host launch (§3.2);
    # Alembic remains the source of truth for evolving the schema later (`alembic upgrade head`).
    try:
        from sqlalchemy import text

        async with engine.begin() as conn:
            # Extensions the schema relies on (pg_trgm for fuzzy search; postgis for geom).
            await conn.execute(text("CREATE EXTENSION IF NOT EXISTS postgis"))
            await conn.execute(text("CREATE EXTENSION IF NOT EXISTS pg_trgm"))
            await conn.run_sync(Base.metadata.create_all)
        log.info("schema_ensured")
    except Exception:  # noqa: BLE001 — never block startup on this bootstrap path
        log.warning("schema_bootstrap_skipped")
    yield
    log.info("parallax_shutdown")


def _cors_origins() -> list[str]:
    # "*" for local dev + an optional deployed frontend (e.g. the Vercel URL) via env.
    origins = ["*"]
    extra = os.getenv("FRONTEND_ORIGIN") or os.getenv("NEXT_PUBLIC_APP_URL")
    if extra and extra not in origins:
        origins.append(extra)
    return origins


def create_app() -> FastAPI:
    app = FastAPI(title="Parallax API", version="1.0.0", lifespan=lifespan)

    app.add_middleware(
        CORSMiddleware,
        allow_origins=_cors_origins(),
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # ── routers, all under /api ──
    api_prefix = "/api"
    for module in (
        auth_router,
        search_router,
        sites_router,
        briefings_router,
        validate_router,
        patch_router,
        watchlist_router,
        usage_router,
        broker_router,
    ):
        app.include_router(module.router, prefix=api_prefix)

    @app.get("/api/health")
    async def health():  # noqa: ANN202
        return ok_health()

    # ── error handling: always the envelope, never a stack or PII ──
    @app.exception_handler(StarletteHTTPException)
    async def http_exc_handler(_request: Request, exc: StarletteHTTPException):
        # Auth/credit deps raise HTTPException whose detail is already an envelope dict.
        if isinstance(exc.detail, dict) and "ok" in exc.detail:
            return JSONResponse(status_code=exc.status_code, content=exc.detail)
        message = exc.detail if isinstance(exc.detail, str) else "Request could not be completed."
        return JSONResponse(
            status_code=exc.status_code,
            content=err(f"HTTP_{exc.status_code}", message),
        )

    @app.exception_handler(RequestValidationError)
    async def validation_exc_handler(_request: Request, _exc: RequestValidationError):
        # Do not echo the raw error (may carry submitted PII) — state the next step only.
        return JSONResponse(
            status_code=422,
            content=err("INVALID_INPUT", "Some fields were missing or malformed. Check and retry."),
        )

    @app.exception_handler(Exception)
    async def unhandled_exc_handler(_request: Request, _exc: Exception):
        log.warning("unhandled_exception")  # no PII, no stack to the client
        return JSONResponse(
            status_code=500,
            content=err("INTERNAL", "Something went wrong on our side. Try again shortly."),
        )

    return app


def ok_health() -> dict:
    from app.schemas.common import ok

    return ok({"status": "ok"})


app = create_app()

"""Somnus — Sleep Optimization App. FastAPI application entry point."""

import math
import os
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, Response
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.trustedhost import TrustedHostMiddleware
from fastapi.responses import JSONResponse

from backend.config import codespaces_hosts, settings
from backend.database import init_db
from backend.routers import (
    analysis,
    daily_log,
    dashboard,
    export,
    oura,
    recommendations,
    reports,
    supplements,
)
from backend.routers import settings as settings_router
from backend.schemas import HealthResponse

VERSION = "0.1.1"


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Application startup and shutdown lifecycle."""
    init_db()
    yield


app = FastAPI(
    title="Somnus",
    description="Sleep optimization API — track habits, import Oura data, analyze what works",
    version=VERSION,
    lifespan=lifespan,
)


# Pydantic's 422 detail echoes the offending input; a non-finite float there
# (e.g. 1e309 -> inf, rejected by allow_inf_nan=False fields) is not JSON
# serializable, so the default handler would crash while RENDERING the 422
# (#161 Lane 3a round-3 delta). Sanitize non-finite floats to their repr so
# the 422 is always deliverable. Behavior is otherwise identical to FastAPI's
# default (same shape, same status).
@app.exception_handler(RequestValidationError)
async def _validation_error_handler(_request: Request, exc: RequestValidationError) -> Response:
    def _safe(value: object) -> object:
        if isinstance(value, float) and not math.isfinite(value):
            return repr(value)
        if isinstance(value, dict):
            return {k: _safe(v) for k, v in value.items()}
        if isinstance(value, list):
            return [_safe(v) for v in value]
        return value

    errors = [{k: _safe(v) for k, v in err.items()} for err in exc.errors()]
    return JSONResponse(status_code=422, content={"detail": jsonable_encoder(errors)})


app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# T-01 (docs/THREAT_MODEL.md): reject non-loopback Host headers to defend the
# unauthenticated localhost API against DNS rebinding / cross-origin reachability.
# Added last so it is the outermost middleware and bad hosts are rejected first.
# codespaces_hosts() appends the forwarded Codespaces host in dev (empty in prod).
app.add_middleware(
    TrustedHostMiddleware,
    allowed_hosts=list(dict.fromkeys(settings.allowed_hosts + codespaces_hosts())),
)


app.include_router(daily_log.router)
app.include_router(settings_router.router)
app.include_router(export.router)
app.include_router(oura.router)
app.include_router(dashboard.router)
app.include_router(analysis.router)
app.include_router(recommendations.router)
app.include_router(reports.router)
app.include_router(supplements.router)

if os.environ.get("SOMNUS_TESTING") == "1":
    from backend.routers.testing import router as testing_router

    app.include_router(testing_router)


@app.get("/api/health", response_model=HealthResponse)
async def health_check() -> HealthResponse:
    """Health check endpoint."""
    return HealthResponse(status="ok", version=VERSION)

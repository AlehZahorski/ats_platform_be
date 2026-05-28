import logging
from contextlib import asynccontextmanager
from datetime import UTC, datetime

from fastapi import FastAPI, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware
from sqlalchemy import update

from app.api.router import api_router
from app.core.rate_limit import limiter

logger = logging.getLogger(__name__)
from app.core.config import settings
from app.core.database import engine, Base, AsyncSessionLocal
from app.core.enums import CVParseStatus
from app.core.exceptions import DomainException
from app.core.i18n import detect_language, set_language, t
from app.modules.applications.models import CVParseJob


# ---------------------------------------------------------------------------
# Lifespan
# ---------------------------------------------------------------------------
@asynccontextmanager
async def lifespan(app: FastAPI):
    # M1 (audit_backend_code): protect startup with try/except so a transient
    # DB blip during boot doesn't crash the worker before the lifespan even
    # yields, and guarantee `engine.dispose()` runs via try/finally — the old
    # version would skip the dispose if the app raised mid-request lifecycle.
    try:
        async with AsyncSessionLocal() as db:
            await db.execute(
                update(CVParseJob)
                .where(CVParseJob.status.in_([CVParseStatus.extracting, CVParseStatus.parsing]))
                .values(
                    status=CVParseStatus.failed,
                    error_message=t("server.restart_retry"),
                    completed_at=datetime.now(UTC),
                )
            )
            await db.commit()
    except Exception:
        logger.exception("Lifespan startup task failed — continuing without retry-cleanup")
    try:
        yield
    finally:
        await engine.dispose()


# ---------------------------------------------------------------------------
# Application factory
# ---------------------------------------------------------------------------
def create_app() -> FastAPI:
    app = FastAPI(
        title=settings.app_name,
        version="1.0.0",
        description="Multi-tenant SaaS Applicant Tracking System API",
        docs_url="/docs" if not settings.is_production else None,
        redoc_url="/redoc" if not settings.is_production else None,
        openapi_url="/openapi.json" if not settings.is_production else None,
        lifespan=lifespan,
    )

    # -----------------------------------------------------------------------
    # Language — set per-request language contextvar from Accept-Language / cookie / ?lang=
    # -----------------------------------------------------------------------
    @app.middleware("http")
    async def language_middleware(request: Request, call_next):
        set_language(detect_language(request))
        return await call_next(request)

    # -----------------------------------------------------------------------
    # CORS — must be added BEFORE other middleware so it runs on errors too
    # -----------------------------------------------------------------------
    # F-H3 (audit_api): CORS spec forbids the literal "*" wildcard when
    # ``allow_credentials=True`` — Starlette echoes it back but strict browsers
    # reject the response. Switch to explicit method/header allowlists. The
    # origin list now comes from ``settings.allowed_cors_origins`` so staging
    # domains can be added via the ``CORS_EXTRA_ORIGINS`` env var (F-M10).
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.allowed_cors_origins,
        allow_credentials=True,
        allow_methods=["GET", "POST", "PATCH", "PUT", "DELETE", "OPTIONS"],
        allow_headers=[
            "Authorization",
            "Content-Type",
            "X-Request-Id",
            "Idempotency-Key",
            "Accept",
            "Accept-Language",
        ],
        expose_headers=["Content-Disposition", "X-Request-Id"],
        max_age=600,
    )

    # -----------------------------------------------------------------------
    # Rate limiting
    # -----------------------------------------------------------------------
    app.state.limiter = limiter
    app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
    app.add_middleware(SlowAPIMiddleware)

    # -----------------------------------------------------------------------
    # Static file serving
    # -----------------------------------------------------------------------
    import os
    os.makedirs(settings.cv_upload_dir, exist_ok=True)
    app.mount(
        "/uploads",
        StaticFiles(directory=settings.upload_dir),
        name="uploads",
    )

    # -----------------------------------------------------------------------
    # Routers
    # -----------------------------------------------------------------------
    app.include_router(api_router)

    # -----------------------------------------------------------------------
    # Health / readiness / version probes
    # -----------------------------------------------------------------------
    # `/health` is the cheap liveness probe — never touches DB so it stays
    # responsive during DB outages and avoids restart loops.
    # L2 (audit_backend_code): tags here are noise — endpoint is hidden from
    # the OpenAPI schema, so the tag never surfaces in Swagger.
    @app.get("/health", include_in_schema=False)
    async def health() -> dict:
        return {"status": "ok", "env": settings.app_env}

    # F-M1 (audit_api): `/ready` is the readiness probe — pings DB so a pod
    # that loses its DB connection is taken out of the load-balancer rotation
    # without being killed. Different from `/health` on purpose.
    @app.get("/ready", include_in_schema=False)
    async def ready() -> JSONResponse:
        from sqlalchemy import text
        try:
            async with AsyncSessionLocal() as db:
                await db.execute(text("SELECT 1"))
            return JSONResponse(status_code=200, content={"status": "ready"})
        except Exception as exc:  # noqa: BLE001 — readiness must never crash
            logger.warning("Readiness probe failed: %s", exc)
            return JSONResponse(
                status_code=503,
                content={"status": "not_ready", "reason": "database_unavailable"},
            )

    # F-L7 (audit_api): operational endpoint for "which build is on prod?".
    # Values come from env vars set by the CI/CD pipeline; sensible defaults
    # avoid breaking local dev.
    import os
    @app.get("/version", include_in_schema=False)
    async def version() -> dict:
        return {
            "version": "1.0.0",
            "commit": os.environ.get("GIT_COMMIT", "unknown"),
            "build_time": os.environ.get("BUILD_TIME", "unknown"),
            "env": settings.app_env,
        }

    # F-10: dedicated LLM-health probe. Reports the breaker state (no live
    # ping to Anthropic — that would itself be a paid call).
    @app.get("/health/llm", include_in_schema=False)
    async def llm_health() -> dict:
        from app.services.llm.circuit import default_breaker
        return {
            "llm_enabled": settings.llm_enabled,
            "breaker_open": default_breaker.is_open(),
        }

    # -----------------------------------------------------------------------
    # Domain exception handler — converts DomainException subclasses to JSON
    # -----------------------------------------------------------------------
    @app.exception_handler(DomainException)
    async def domain_exception_handler(request: Request, exc: DomainException) -> JSONResponse:
        return JSONResponse(
            status_code=exc.status_code,
            content={"detail": exc.detail},
        )

    # -----------------------------------------------------------------------
    # Fallback handler — always return JSON, always log the error
    # -----------------------------------------------------------------------
    @app.exception_handler(Exception)
    async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
        logger.exception("Unhandled exception on %s %s", request.method, request.url)
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content={"detail": t("errors.unexpected")},
        )

    return app


app = create_app()

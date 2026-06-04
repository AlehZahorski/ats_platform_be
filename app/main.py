import logging
from contextlib import asynccontextmanager
from datetime import UTC, datetime

from fastapi import FastAPI, Request, status
from fastapi.exceptions import RequestValidationError
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
from app.core.database import AsyncSessionLocal, engine
from app.core.enums import CVParseStatus
from app.core.exceptions import DomainException
from app.core.i18n import detect_language, set_language, t
from app.core.logging_utils import (
    configure_log_format,
    install_root_filters,
    new_request_id,
    request_id_ctx,
)
from app.modules.applications.models import CVParseJob

# audit_logging_monitoring F-03 / F-17: filters live on the root logger so
# every child logger (uvicorn, sqlalchemy, ours) emits ``request_id`` and
# goes through PII redaction. Called at import time so we don't lose the
# first few startup lines.
install_root_filters()
# Faza 4: opt into structured JSON logs via LOG_FORMAT=json (text by default).
configure_log_format(settings.log_format)


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

    # audit_szybkosci: pre-warm the asyncpg connection pool so the first user
    # requests don't pay the TCP + auth + SET handshake (typically 5-20ms per
    # cold connection). We open + ping a small batch concurrently — if a
    # single connection fails (DB momentarily unavailable mid-boot) the
    # warmup is silently abandoned; lazy connect will still work on first
    # real request.
    try:
        import asyncio as _asyncio

        from sqlalchemy import text as _text

        async def _ping():
            async with AsyncSessionLocal() as s:
                await s.execute(_text("SELECT 1"))

        warmup_target = min(3, settings.db_pool_size)
        await _asyncio.gather(*(_ping() for _ in range(warmup_target)))
        logger.info("DB pool pre-warmed with %d connections", warmup_target)
    except Exception:
        logger.warning(
            "DB pool pre-warm skipped — first request will pay cold-connect cost", exc_info=True
        )

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
    # Request-ID middleware — audit_logging_monitoring F-03. Honour an
    # inbound ``X-Request-ID`` (so the frontend / Caddy can correlate),
    # otherwise mint a fresh one. The id is exposed on the response so the
    # browser can show it in error toasts and is propagated to every log
    # record via the contextvar-backed filter installed at module import.
    # -----------------------------------------------------------------------
    @app.middleware("http")
    async def request_id_middleware(request: Request, call_next):
        incoming = request.headers.get("X-Request-ID")
        rid = incoming if incoming and len(incoming) <= 64 else new_request_id()
        token = request_id_ctx.set(rid)
        try:
            response = await call_next(request)
        finally:
            request_id_ctx.reset(token)
        response.headers["X-Request-ID"] = rid
        return response

    # -----------------------------------------------------------------------
    # Language — set per-request language contextvar from Accept-Language / cookie / ?lang=
    # -----------------------------------------------------------------------
    @app.middleware("http")
    async def language_middleware(request: Request, call_next):
        set_language(detect_language(request))
        return await call_next(request)

    # -----------------------------------------------------------------------
    # Cache-Control for public, anonymous-readable GETs — audit_performance
    # B-12. Cheap to serve from a CDN edge cache; private/authenticated paths
    # are skipped so per-user data never lands in a shared cache.
    # -----------------------------------------------------------------------
    _PUBLIC_CACHE_PREFIXES = (
        "/api/v1/jobs/public",
        "/api/v1/companies/public",
        "/api/v1/articles/public",
    )

    @app.middleware("http")
    async def public_cache_headers_middleware(request: Request, call_next):
        response = await call_next(request)
        if (
            request.method == "GET"
            and any(request.url.path.startswith(p) for p in _PUBLIC_CACHE_PREFIXES)
            and response.status_code < 400
            and "cache-control" not in {k.lower() for k in response.headers}
        ):
            # 60s edge cache + 5-minute stale-while-revalidate gives CDN/Caddy
            # an easy time without making content noticeably stale.
            response.headers["Cache-Control"] = (
                "public, max-age=60, s-maxage=300, stale-while-revalidate=60"
            )
        return response

    # -----------------------------------------------------------------------
    # Security headers — audit_security H. Caddy can also set these at the
    # edge, but having FastAPI emit them as a safety net means a misrouted
    # request (e.g. direct hit on the container by an internal scanner)
    # still gets the protections.
    # -----------------------------------------------------------------------
    @app.middleware("http")
    async def security_headers_middleware(request: Request, call_next):
        response = await call_next(request)
        headers = response.headers
        # Clickjacking, MIME sniffing, referer leakage.
        headers.setdefault("X-Content-Type-Options", "nosniff")
        headers.setdefault("X-Frame-Options", "DENY")
        headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
        # Disable the loudest browser features the app does not use.
        headers.setdefault(
            "Permissions-Policy",
            "camera=(), microphone=(), geolocation=(), payment=()",
        )
        # HSTS only in production — in dev we still serve over http://localhost.
        if settings.is_production:
            headers.setdefault(
                "Strict-Transport-Security",
                "max-age=31536000; includeSubDomains; preload",
            )
        return response

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

    # audit_logging_monitoring F-15: log every 429 with the client / path
    # so brute-force or scraping attempts are visible. The default slowapi
    # handler just returns a 429 silently, which made these incidents
    # impossible to detect after the fact.
    async def _logged_rate_limit_handler(request: Request, exc: RateLimitExceeded):
        from slowapi.util import get_remote_address

        logger.warning(
            "Rate limit exceeded path=%s ip=%s detail=%s",
            request.url.path,
            get_remote_address(request),
            getattr(exc, "detail", ""),
        )
        return _rate_limit_exceeded_handler(request, exc)

    app.add_exception_handler(RateLimitExceeded, _logged_rate_limit_handler)
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
    # audit_security L: `/health` no longer reveals the deploy environment —
    # was a small information-disclosure that helped attackers fingerprint
    # which infra they had landed on. K8s probes only need `status: ok`.
    @app.get("/health", include_in_schema=False)
    async def health() -> dict:
        return {"status": "ok"}

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
    # 422 logger — default FastAPI returns the error JSON to the client but
    # never logs it server-side, so backend logs only show "INFO ... 422" with
    # zero hint why. This handler keeps the standard 422 response (same body,
    # same status) but also writes a single WARNING line with the validation
    # details + offending input, so we can debug failing autosaves/imports
    # without attaching a debugger.
    @app.exception_handler(RequestValidationError)
    async def request_validation_handler(
        request: Request, exc: RequestValidationError
    ) -> JSONResponse:
        try:
            body_preview = exc.body if isinstance(exc.body, (str, bytes)) else None
            if isinstance(body_preview, bytes):
                body_preview = body_preview.decode("utf-8", errors="replace")
            if isinstance(body_preview, str) and len(body_preview) > 2000:
                body_preview = body_preview[:2000] + "…[truncated]"
        except Exception:
            body_preview = "<unreadable>"
        import sys

        msg = (
            f"[422] {request.method} {request.url.path} :: "
            f"errors={exc.errors()} body={body_preview}"
        )
        print(msg, file=sys.stderr, flush=True)
        logger.warning(msg)
        return JSONResponse(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            content={"detail": exc.errors(), "body": exc.body},
        )

    @app.exception_handler(DomainException)
    async def domain_exception_handler(request: Request, exc: DomainException) -> JSONResponse:
        import sys

        print(
            f"[DomainException {exc.status_code}] {request.method} {request.url.path} :: {exc.detail!r}",
            file=sys.stderr,
            flush=True,
        )
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

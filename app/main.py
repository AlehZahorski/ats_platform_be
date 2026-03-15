from contextlib import asynccontextmanager
import traceback

from fastapi import FastAPI, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware
from slowapi.util import get_remote_address

from app.core.config import settings
from app.core.database import engine, Base

# ---------------------------------------------------------------------------
# Rate limiter
# ---------------------------------------------------------------------------
limiter = Limiter(key_func=get_remote_address, default_limits=["200/minute"])


# ---------------------------------------------------------------------------
# Lifespan
# ---------------------------------------------------------------------------
@asynccontextmanager
async def lifespan(app: FastAPI):
    yield
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
    # CORS — must be added BEFORE other middleware so it runs on errors too
    # -----------------------------------------------------------------------
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[
            "http://localhost:3000",
            "http://127.0.0.1:3000",
            settings.frontend_url,
        ],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
        expose_headers=["*"],
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
    from app.modules.auth.router import router as auth_router
    from app.modules.companies.router import router as companies_router
    from app.modules.users.router import router as users_router
    from app.modules.jobs.router import router as jobs_router
    from app.modules.forms.router import router as forms_router
    from app.modules.applications.router import router as applications_router
    from app.modules.pipeline.router import router as pipeline_router
    from app.modules.notes.router import router as notes_router
    from app.modules.tags.router import router as tags_router
    from app.modules.audit.router import router as audit_router

    API_V1 = "/api/v1"

    app.include_router(auth_router,         prefix=f"{API_V1}/auth",         tags=["Auth"])
    app.include_router(companies_router,    prefix=f"{API_V1}/company",      tags=["Company"])
    app.include_router(users_router,        prefix=f"{API_V1}/users",        tags=["Users"])
    app.include_router(jobs_router,         prefix=f"{API_V1}/jobs",         tags=["Jobs"])
    app.include_router(forms_router,        prefix=f"{API_V1}/forms",        tags=["Forms"])
    app.include_router(applications_router, prefix=f"{API_V1}/applications", tags=["Applications"])
    app.include_router(pipeline_router,     prefix=f"{API_V1}/pipeline",     tags=["Pipeline"])
    app.include_router(notes_router,        prefix=f"{API_V1}/notes",        tags=["Notes"])
    app.include_router(tags_router,         prefix=f"{API_V1}/tags",         tags=["Tags"])
    app.include_router(audit_router,        prefix=f"{API_V1}/audit",        tags=["Audit"])

    # -----------------------------------------------------------------------
    # Health check
    # -----------------------------------------------------------------------
    @app.get("/health", tags=["Health"], include_in_schema=False)
    async def health() -> dict:
        return {"status": "ok", "env": settings.app_env}

    # -----------------------------------------------------------------------
    # Global exception handler — always return JSON, always log the error
    # -----------------------------------------------------------------------
    @app.exception_handler(Exception)
    async def unhandled_exception_handler(request: Request, exc: Exception):
        # Always print the real error to terminal
        traceback.print_exc()
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content={"detail": str(exc)},
        )

    return app


app = create_app()
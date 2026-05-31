from collections.abc import AsyncGenerator

from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase

from app.core.config import settings


# ---------------------------------------------------------------------------
# Engine
# ---------------------------------------------------------------------------
def _connect_args() -> dict:
    """audit_performance B-09: per-session Postgres settings applied at every
    new connection. ``statement_timeout`` caps any single query so a runaway
    SELECT can't tie up a pool slot indefinitely;
    ``idle_in_transaction_session_timeout`` reclaims slots if a worker forgets
    to commit. asyncpg only honours these via the ``server_settings`` mapping.
    Both knobs are bypassed for SQLite (used in unit tests).
    """
    if settings.database_url.startswith("sqlite"):
        return {}
    return {
        "server_settings": {
            "statement_timeout": str(settings.db_statement_timeout_ms),
            "idle_in_transaction_session_timeout": str(settings.db_idle_in_transaction_timeout_ms),
            "application_name": settings.app_name or "wakanta-api",
        }
    }


# audit_performance B-06: pool size + overflow + timeout + recycle are now
# env-driven (see app.core.config) so the same image scales from local dev
# (10/20) to a multi-worker prod deploy (e.g. 20/10 per worker).
engine = create_async_engine(
    settings.database_url,
    echo=settings.debug,
    pool_pre_ping=True,
    pool_size=settings.db_pool_size,
    max_overflow=settings.db_max_overflow,
    pool_timeout=settings.db_pool_timeout,
    pool_recycle=settings.db_pool_recycle,
    connect_args=_connect_args(),
)

# ---------------------------------------------------------------------------
# Session factory
# ---------------------------------------------------------------------------
AsyncSessionLocal = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,  # avoid lazy-load errors after commit
    autocommit=False,
    autoflush=False,
)


# ---------------------------------------------------------------------------
# Declarative base — imported by all models
# ---------------------------------------------------------------------------
class Base(DeclarativeBase):
    pass


# ---------------------------------------------------------------------------
# FastAPI dependency
# ---------------------------------------------------------------------------
async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """
    Yield an async database session scoped to a single request.
    Session is committed on success and rolled back on error.
    """
    async with AsyncSessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()

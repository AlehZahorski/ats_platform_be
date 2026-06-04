"""Pytest configuration and shared test fixtures.

Faza 0 (plan-naprawy): tests run against a REAL PostgreSQL 16, not in-memory
SQLite. This removes the ``@compiles(JSONB, "sqlite")`` shim and the whole
class of "green on SQLite, red on Postgres" bugs (JSONB, CHECK constraints,
trigram/GIN indexes, cascades behave for real). See docs/adr/0001-*.md.

Database resolution (in order):
  1. ``TEST_DATABASE_URL`` env var (preferred in CI — a ``postgres:16``
     service container), or
  2. ``DATABASE_URL`` env var if it already points at Postgres, or
  3. an ephemeral ``postgres:16-alpine`` started via testcontainers
     (local-dev fallback — requires a running Docker daemon).

Schema is built once per session via ``alembic upgrade head`` (so migrations
themselves are exercised). Per-test isolation uses a connection-bound outer
transaction rolled back after each test (``join_transaction_mode=
"create_savepoint"`` lets the app's own ``commit()`` calls run as savepoints),
plus a TRUNCATE safety net that clears any rows committed out-of-band by
background tasks using the app's own engine.
"""

from __future__ import annotations

import asyncio
import atexit
import os
import subprocess
import sys
from collections.abc import AsyncGenerator
from pathlib import Path

# ---------------------------------------------------------------------------
# Resolve the test database URL and export it BEFORE importing the app — the
# app builds its async engine at import time from ``settings.database_url``,
# so it must already point at the test database for background-task sessions
# (which use the app engine) to hit the same place as the test session.
# ---------------------------------------------------------------------------
_BACKEND_DIR = Path(__file__).resolve().parent.parent

_pg_container = None
_test_db_url = os.getenv("TEST_DATABASE_URL") or os.getenv("DATABASE_URL")

if not _test_db_url or "postgresql" not in _test_db_url:
    # Local-dev fallback: spin up a throwaway Postgres 16 via testcontainers.
    from testcontainers.postgres import PostgresContainer

    _pg_container = PostgresContainer("postgres:16-alpine", driver="asyncpg")
    _pg_container.start()
    atexit.register(_pg_container.stop)
    _test_db_url = _pg_container.get_connection_url()

os.environ["DATABASE_URL"] = _test_db_url
# The app's Settings require these; provide deterministic test defaults so a
# bare ``pytest`` (no .env) still imports cleanly.
os.environ.setdefault("SECRET_KEY", "test-secret-key-not-for-production")
os.environ.setdefault("JWT_SECRET", "test-jwt-secret-not-for-production")

import pytest  # noqa: E402
import pytest_asyncio  # noqa: E402
from httpx import ASGITransport, AsyncClient  # noqa: E402
from sqlalchemy import text  # noqa: E402
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine  # noqa: E402

from app.core.database import Base, get_db  # noqa: E402
from app.main import app  # noqa: E402

# Dedicated engine for the test fixtures (separate pool from the app engine,
# same database).
test_engine = create_async_engine(_test_db_url, echo=False, future=True)


@pytest.fixture(scope="session")
def event_loop():
    # One shared loop for the whole session so asyncpg connections (which are
    # event-loop-bound) created in session-scoped fixtures stay usable in
    # function-scoped fixtures and tests.
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()


@pytest_asyncio.fixture(scope="session", autouse=True)
async def _setup_schema():
    """Build the schema once per session by running the real migrations."""
    env = os.environ.copy()
    env["DATABASE_URL"] = _test_db_url
    result = subprocess.run(
        [sys.executable, "-m", "alembic", "upgrade", "head"],
        cwd=str(_BACKEND_DIR),
        env=env,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        raise RuntimeError(
            "alembic upgrade head failed during test setup:\n"
            f"STDOUT:\n{result.stdout}\nSTDERR:\n{result.stderr}"
        )
    yield
    await test_engine.dispose()


# All app tables, child-before-parent order reversed by TRUNCATE ... CASCADE.
_ALL_TABLES = ", ".join(f'"{t.name}"' for t in Base.metadata.sorted_tables)


@pytest_asyncio.fixture(autouse=True)
async def _truncate_after():
    """Safety net: wipe any rows committed outside the per-test transaction.

    The per-test ``db_session`` rolls back its own transaction, so data created
    through it never persists. But code paths that open their own
    ``AsyncSessionLocal`` (e.g. background CV-parse / automation tasks) commit
    on the app engine and would leak across tests. TRUNCATE ... CASCADE after
    each test guarantees a clean slate regardless.
    """
    yield
    if not _ALL_TABLES:
        return
    async with test_engine.begin() as conn:
        await conn.execute(text(f"TRUNCATE {_ALL_TABLES} RESTART IDENTITY CASCADE"))


@pytest.fixture(autouse=True)
def _isolate_external_effects():
    """Keep tests off real external systems.

    1. SMTP — mailer._send_smtp short-circuits when settings.smtp_host is empty,
       so every send_* helper becomes a no-op and auth flows that send a
       verification email don't raise against whatever host .env points at.
    2. Rate limiter — disable slowapi; rate limiting is not what these tests
       exercise.
    3. app_env — pinned to "staging" so the real email-verification gate is
       exercised (development auto-verifies new signups).
    """
    from app.core.config import settings
    from app.core.rate_limit import limiter

    original_host = settings.smtp_host
    original_limiter = limiter.enabled
    original_env = settings.app_env
    settings.smtp_host = ""
    limiter.enabled = False
    settings.app_env = "staging"
    yield
    settings.smtp_host = original_host
    limiter.enabled = original_limiter
    settings.app_env = original_env


@pytest_asyncio.fixture
async def db_session() -> AsyncGenerator[AsyncSession, None]:
    """A session bound to a single connection wrapped in a transaction that is
    always rolled back, so each test starts from a clean state. The app's own
    ``commit()`` calls run as savepoints inside the outer transaction.
    """
    conn = await test_engine.connect()
    trans = await conn.begin()
    session = AsyncSession(
        bind=conn,
        expire_on_commit=False,
        join_transaction_mode="create_savepoint",
    )
    try:
        yield session
    finally:
        await session.close()
        if trans.is_active:
            await trans.rollback()
        await conn.close()


@pytest_asyncio.fixture
async def client(db_session: AsyncSession) -> AsyncGenerator[AsyncClient, None]:
    async def override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = override_get_db

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        yield ac

    app.dependency_overrides.clear()

"""
Pytest configuration and shared test fixtures.
"""
from __future__ import annotations

import asyncio
from collections.abc import AsyncGenerator
from typing import Any

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.ext.compiler import compiles

from app.core.database import Base, get_db
from app.main import app

# ---------------------------------------------------------------------------
# Postgres JSONB on SQLite — models use the PG-specific JSONB type, but the
# test engine is SQLite, whose compiler has no `visit_JSONB` and bails out of
# `create_all` with a CompileError. Teach the SQLite dialect to render JSONB
# as plain JSON (functionally equivalent for our test assertions) so the
# schema can be created. Production still uses real Postgres JSONB.
# ---------------------------------------------------------------------------
@compiles(JSONB, "sqlite")
def _compile_jsonb_as_json_on_sqlite(type_, compiler, **kw):  # noqa: ANN001
    return "JSON"


# ---------------------------------------------------------------------------
# In-memory SQLite for tests (swap to test PG if needed)
# ---------------------------------------------------------------------------
TEST_DB_URL = "sqlite+aiosqlite:///:memory:"

test_engine = create_async_engine(TEST_DB_URL, echo=False)
TestSessionLocal = async_sessionmaker(
    bind=test_engine, class_=AsyncSession, expire_on_commit=False
)


@pytest.fixture(scope="session")
def event_loop():
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()


@pytest_asyncio.fixture(scope="session", autouse=True)
async def setup_db():
    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield
    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)


@pytest.fixture(autouse=True)
def _isolate_external_effects():
    """Keep tests off real external systems.

    1. SMTP — mailer._smtp_send short-circuits when settings.smtp_host is empty
       (see its docstring). Blanking it makes every send_* helper a no-op, so
       auth flows that send verification emails don't raise SMTPDataError
       against whatever host .env points at.
    2. Rate limiter — disable slowapi for tests. The installed slowapi/limits
       pair raises AttributeError ('RateLimitItemPerMinute' has no 'key_for')
       on hit(); rate limiting is not what these tests exercise, so turn it off.
    """
    from app.core.config import settings
    from app.core.rate_limit import limiter

    original_host = settings.smtp_host
    original_limiter = limiter.enabled
    original_env = settings.app_env
    settings.smtp_host = ""
    limiter.enabled = False
    # app_env defaults to "development", which auto-verifies new signups
    # (see AuthService.signup_company). Tests must exercise the real verify
    # gate, so pin a non-dev env for the suite.
    settings.app_env = "staging"
    yield
    settings.smtp_host = original_host
    limiter.enabled = original_limiter
    settings.app_env = original_env


@pytest_asyncio.fixture
async def db_session() -> AsyncGenerator[AsyncSession, None]:
    async with TestSessionLocal() as session:
        yield session


@pytest_asyncio.fixture
async def client(db_session: AsyncSession) -> AsyncGenerator[AsyncClient, None]:
    async def override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = override_get_db

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as ac:
        yield ac

    app.dependency_overrides.clear()

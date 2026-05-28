"""Alembic environment — async SQLAlchemy support."""
from __future__ import annotations

import asyncio
import importlib
import logging
import pkgutil
from logging.config import fileConfig

from alembic import context
from sqlalchemy import pool
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import async_engine_from_config

import app.modules  # noqa: F401 — package needed for walk_packages
from app.core.config import settings
from app.core.database import Base  # noqa: F401

# ---------------------------------------------------------------------------
# L6 (audit_backend_code): auto-discover every `models.py` under app.modules
# instead of maintaining the import list by hand. Missing a new module used
# to silently produce "no changes" autogenerate runs; now adding a module is
# enough — env.py picks it up. Extra modules with sibling files like
# `analysis_models.py` are discovered via the `_extra_model_modules` suffix
# list.
# ---------------------------------------------------------------------------
_alembic_log = logging.getLogger("alembic.env")
_extra_model_module_suffixes = ("models", "analysis_models")

for module_info in pkgutil.walk_packages(app.modules.__path__, prefix="app.modules."):
    short_name = module_info.name.rsplit(".", 1)[-1]
    if short_name in _extra_model_module_suffixes:
        try:
            importlib.import_module(module_info.name)
        except Exception as exc:  # noqa: BLE001 — env.py must never crash on optional modules
            _alembic_log.warning("Alembic skipped %s: %s", module_info.name, exc)

config = context.config
config.set_main_option("sqlalchemy.url", settings.database_url)

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def run_migrations_offline() -> None:
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def do_run_migrations(connection: Connection) -> None:
    context.configure(connection=connection, target_metadata=target_metadata)
    with context.begin_transaction():
        context.run_migrations()


async def run_async_migrations() -> None:
    connectable = async_engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    async with connectable.connect() as connection:
        await connection.run_sync(do_run_migrations)
    await connectable.dispose()


def run_migrations_online() -> None:
    asyncio.run(run_async_migrations())


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()

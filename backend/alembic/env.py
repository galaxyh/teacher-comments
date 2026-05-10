"""Alembic environment — async-aware, reads URL from app.config.Settings.

Per ARCH-001 §2.3 and §6.5: Alembic runs migrations against the same SQLAlchemy
metadata used by the app. Importing `app.models` triggers all model module imports
(see app/models/__init__.py), giving autogenerate full visibility.
"""

from __future__ import annotations

import asyncio
from logging.config import fileConfig

from sqlalchemy import pool
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import async_engine_from_config

from alembic import context
from app import models  # noqa: F401  — register all model classes on Base.metadata
from app.config import get_settings
from app.db.session import Base

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# Wire DATABASE_URL from Settings (single source of truth; ARCH-001 §6.2).
config.set_main_option("sqlalchemy.url", get_settings().database_url)

target_metadata = Base.metadata


def run_migrations_offline() -> None:
    """Generate SQL without DB connection (useful for review)."""
    context.configure(
        url=config.get_main_option("sqlalchemy.url"),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        render_as_batch=True,  # SQLite needs batch mode for ALTER
    )
    with context.begin_transaction():
        context.run_migrations()


def do_run_migrations(connection: Connection) -> None:
    context.configure(
        connection=connection,
        target_metadata=target_metadata,
        render_as_batch=True,
    )
    with context.begin_transaction():
        context.run_migrations()


async def run_migrations_online() -> None:
    connectable = async_engine_from_config(
        config.get_section(config.config_ini_section) or {},
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    # Set SQLite PRAGMAs OUTSIDE any transaction context — PRAGMA journal_mode=WAL
    # silently fails inside an open transaction. WAL is a DB-header setting that
    # persists once set; subsequent app connections see WAL automatically.
    async with connectable.connect() as connection:
        if connection.dialect.name == "sqlite":
            await connection.exec_driver_sql("PRAGMA journal_mode=WAL")
            await connection.exec_driver_sql("PRAGMA foreign_keys=ON")
            await connection.exec_driver_sql("PRAGMA synchronous=NORMAL")
        await connection.run_sync(do_run_migrations)
        # Explicit commit — `engine.connect()` is begin-on-exit-rollback by default
        # in SQLAlchemy 2.0 async. Without this, alembic_version updates are silently
        # dropped on dispose. (Standard sync alembic env.py works because the sync
        # connection auto-commits in non-transactional DDL mode; the async wrapper
        # does not propagate this autocommit behaviour through run_sync.)
        await connection.commit()
    await connectable.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    asyncio.run(run_migrations_online())

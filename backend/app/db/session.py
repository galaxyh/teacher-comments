"""Async SQLAlchemy session for SQLite WAL (D16).

Reads bypass DBWriteQueue and use short-lived sessions per request (ARCH-001 §6.5).
Writes MUST go through `app.db.write_queue.DBWriteQueue.submit()`.

Lessons-learned/database.md and architecture.md inform two design choices:
1. WAL mode + foreign_keys ON set via SQLite event listener (one-time per connection)
2. Single async engine per process; the write queue serialises actual writes
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Any

from sqlalchemy import event
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase

from app.config import get_settings


class Base(DeclarativeBase):
    """Single declarative base; all ORM models inherit from this."""


def _create_engine() -> AsyncEngine:
    settings = get_settings()
    engine = create_async_engine(
        settings.database_url,
        echo=False,
        pool_pre_ping=True,
    )

    # PRAGMA WAL + foreign_keys on every new connection. Idempotent: SQLite caches the
    # journal_mode setting per DB file, but setting it on connection is cheap and ensures
    # fresh DBs (tests, container restarts) always get WAL.
    @event.listens_for(engine.sync_engine, "connect")
    def _set_sqlite_pragmas(dbapi_conn: Any, _conn_record: Any) -> None:
        cur = dbapi_conn.cursor()
        try:
            cur.execute("PRAGMA journal_mode=WAL")
            cur.execute("PRAGMA foreign_keys=ON")
            cur.execute("PRAGMA synchronous=NORMAL")  # WAL-safe; faster than FULL
            cur.execute("PRAGMA busy_timeout=5000")    # 5s instead of immediate-fail
        finally:
            cur.close()

    return engine


# Lazy singletons — env vars must be readable when the engine is built. Tests reset these
# via reset_engine_cache() so per-test SQLite paths actually take effect.
_engine: AsyncEngine | None = None
_session_local: async_sessionmaker[AsyncSession] | None = None


def get_engine() -> AsyncEngine:
    """Engine accessor — used by Alembic env.py, lifespan startup, and write queue."""
    global _engine
    if _engine is None:
        _engine = _create_engine()
    return _engine


def get_sessionmaker() -> async_sessionmaker[AsyncSession]:
    global _session_local
    if _session_local is None:
        _session_local = async_sessionmaker(
            get_engine(), expire_on_commit=False, class_=AsyncSession
        )
    return _session_local


async def get_session() -> AsyncIterator[AsyncSession]:
    """FastAPI dependency for read-only sessions.

    Writes still go through DBWriteQueue. Routers use this only for queries.
    """
    async with get_sessionmaker()() as session:
        yield session


async def reset_engine_cache() -> None:
    """Test-only — drop cached engine so next access uses current env vars.

    Production code never calls this. Tests use it after `monkeypatch.setenv`.
    """
    global _engine, _session_local
    if _engine is not None:
        await _engine.dispose()
    _engine = None
    _session_local = None



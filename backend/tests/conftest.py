"""Test fixtures.

Each test gets isolated env via tmp_path-backed SQLite DB. The Settings cache is
explicitly cleared per test so env-var overrides take effect; same pattern for the
encryption cipher cache (see services/encryption.py reset_cipher_cache).
"""

from __future__ import annotations

import asyncio
import base64
import os
from collections.abc import AsyncIterator, Iterator
from pathlib import Path

import pytest

from app.config import get_settings


def _set_test_env(tmp_path: Path) -> None:
    """Populate env vars with deterministic test values."""
    test_key = base64.b64encode(b"\x00" * 32).decode()  # zero-key OK for tests
    os.environ.update(
        {
            "DATABASE_URL": f"sqlite+aiosqlite:///{tmp_path / 'test.db'}",
            "GOOGLE_CLIENT_ID": "test-client-id",
            "GOOGLE_CLIENT_SECRET": "test-client-secret",
            "PUBLIC_BASE_URL": "http://test.local",
            "OPENROUTER_API_KEY": "sk-or-test",
            "PII_ENCRYPTION_KEY": test_key,
            "OAUTH_TOKEN_ENCRYPTION_KEY": test_key,
            "SESSION_SECRET_KEY": test_key,
            "LOG_LEVEL": "WARNING",
        }
    )


@pytest.fixture
def isolated_env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[Path]:
    """Per-test env reset — clears Settings, cipher, engine, and queue caches.

    Each test gets:
    - Fresh Settings (env vars rebound)
    - Fresh AES cipher (key may differ)
    - Fresh DB engine (DATABASE_URL points at tmp_path)
    - Fresh DBWriteQueue (asyncio.Queue not bound to a stale loop)
    """
    from app.db import session as db_session
    from app.db import write_queue as wq
    from app.services import encryption
    from app.services import sse_publisher as sse

    _set_test_env(tmp_path)
    get_settings.cache_clear()
    encryption.reset_cipher_cache()
    wq.reset_write_queue_cache()
    sse.reset_sse_publisher_cache()
    asyncio.get_event_loop_policy().new_event_loop().run_until_complete(
        db_session.reset_engine_cache()
    )
    yield tmp_path
    get_settings.cache_clear()
    encryption.reset_cipher_cache()
    wq.reset_write_queue_cache()
    sse.reset_sse_publisher_cache()
    asyncio.get_event_loop_policy().new_event_loop().run_until_complete(
        db_session.reset_engine_cache()
    )


@pytest.fixture
async def write_queue() -> AsyncIterator:
    """Spin up a DBWriteQueue with isolated lifecycle.

    Note: this fixture relies on `isolated_env` having configured the DB URL via env.
    Tests that need both must depend on `isolated_env` first.
    """
    # Local import — needs env vars set before module-level engine creation
    from app.db.write_queue import DBWriteQueue

    queue = DBWriteQueue()
    queue.start()
    try:
        yield queue
    finally:
        await queue.stop()


# Pytest-asyncio default configuration — every async test is automatically wrapped
@pytest.fixture(scope="session")
def event_loop_policy() -> asyncio.AbstractEventLoopPolicy:
    return asyncio.DefaultEventLoopPolicy()

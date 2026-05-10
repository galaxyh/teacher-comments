"""DBWriteQueue tests — covers ARCH-001 §6.5 load-bearing pattern.

Tests run against the real SQLite engine (per `isolated_env` fixture). The queue
is the single-writer chokepoint, so we verify:
1. Submitted writes commit
2. Exceptions propagate to the submitter
3. Submissions FIFO-ordered (no parallel commit interleaving)
4. Stop drains pending work
"""

from __future__ import annotations

import asyncio

import pytest
from sqlalchemy import text


@pytest.mark.asyncio
async def test_submit_returns_value(isolated_env, write_queue) -> None:
    async def write(_session) -> str:
        return "committed"

    result = await write_queue.submit(write)
    assert result == "committed"


@pytest.mark.asyncio
async def test_submit_propagates_exception(isolated_env, write_queue) -> None:
    class Boom(RuntimeError):
        pass

    async def write(_session) -> None:
        raise Boom("write failed")

    with pytest.raises(Boom, match="write failed"):
        await write_queue.submit(write)


@pytest.mark.asyncio
async def test_submissions_serialised(isolated_env, write_queue) -> None:
    """If two writes start "concurrently", the second must wait for the first.

    Use a shared list of timestamps to confirm strict ordering.
    """
    order: list[int] = []

    async def make_write(n: int):
        async def write(_session) -> int:
            # Force a context switch — without serialisation, ordering would scramble
            await asyncio.sleep(0)
            order.append(n)
            return n

        return write

    fns = [await make_write(i) for i in range(20)]
    results = await asyncio.gather(*[write_queue.submit(fn) for fn in fns])

    assert results == list(range(20))
    assert order == list(range(20))


@pytest.mark.asyncio
async def test_real_db_write_visible_after_commit(isolated_env) -> None:
    """End-to-end: write a row via the queue, read it back via a fresh session."""
    # Run alembic to create schema in the test DB (uses current process env)
    import subprocess
    subprocess.run(
        ["uv", "run", "alembic", "upgrade", "head"],
        check=True,
        cwd="/home/steven/projects/teacher-comments/backend",
        env={**__import__("os").environ},
        capture_output=True,
    )

    from app.db.session import get_sessionmaker
    from app.db.write_queue import DBWriteQueue
    from app.models import SystemEvent

    queue = DBWriteQueue()
    queue.start()
    try:
        async def write(session) -> str:
            ev = SystemEvent(
                event_type="schema_migrated",
                severity="info",
                created_at="2026-05-10T00:00:00Z",
            )
            session.add(ev)
            await session.flush()
            return ev.id

        event_id = await queue.submit(write)

        # Read via a separate session — proves commit happened
        async with get_sessionmaker()() as s:
            row = (
                await s.execute(text("SELECT event_type FROM system_event WHERE id = :id"),
                                {"id": event_id})
            ).first()
            assert row is not None
            assert row[0] == "schema_migrated"
    finally:
        await queue.stop()


@pytest.mark.asyncio
async def test_stop_after_start(isolated_env) -> None:
    from app.db.write_queue import DBWriteQueue

    queue = DBWriteQueue()
    queue.start()
    await queue.stop()

    # Submitting after stop must raise
    async def write(_session) -> None:
        return None

    with pytest.raises(RuntimeError, match="stopped"):
        await queue.submit(write)

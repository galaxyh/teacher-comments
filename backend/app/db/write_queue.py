"""Single-writer serialisation queue for SQLite WAL (ARCH-001 §6.5).

Why a queue: SQLite WAL allows concurrent readers but only one writer. Without
serialisation we hit `database is locked` errors under any non-trivial concurrency.
The queue trades ~5ms latency per write for elimination of the lock-contention class
entirely.

Every service that writes goes through `submit(write_fn)`. `write_fn` is a callable
that receives an `AsyncSession`, performs writes, and returns a value. The drain task
commits exactly once per submission (transactional integrity per submit).

Lessons-learned/architecture.md "Decouple Pipelines by Resource Type" applies:
the queue itself is a separate event-loop task, decoupling writers from readers.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Awaitable, Callable
from typing import TypeVar

from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_sessionmaker

T = TypeVar("T")
WriteFn = Callable[[AsyncSession], Awaitable[T]]

logger = logging.getLogger(__name__)


class DBWriteQueue:
    """Single-task drain over an asyncio.Queue.

    Lifecycle is managed by `app.core.lifespan` — call `start()` on FastAPI startup,
    `stop()` on shutdown.
    """

    def __init__(self) -> None:
        self._queue: asyncio.Queue[
            tuple[WriteFn, asyncio.Future] | None
        ] = asyncio.Queue()
        self._task: asyncio.Task | None = None
        self._stopped = False

    def start(self) -> None:
        if self._task is not None:
            raise RuntimeError("DBWriteQueue already started")
        self._task = asyncio.create_task(self._drain(), name="db-write-queue-drain")
        logger.info("DBWriteQueue started")

    async def stop(self, *, drain_timeout: float = 5.0) -> None:
        if self._task is None:
            return
        self._stopped = True
        await self._queue.put(None)  # sentinel to break the loop
        try:
            await asyncio.wait_for(self._task, timeout=drain_timeout)
        except TimeoutError:
            logger.warning(
                "DBWriteQueue drain did not finish in %.1fs — cancelling", drain_timeout
            )
            self._task.cancel()
        self._task = None
        logger.info("DBWriteQueue stopped")

    async def submit(self, write_fn: WriteFn[T]) -> T:
        """Enqueue a write callable. Resolves with the function's return value."""
        if self._stopped:
            raise RuntimeError("DBWriteQueue is stopped; cannot accept writes")
        future: asyncio.Future[T] = asyncio.get_running_loop().create_future()
        await self._queue.put((write_fn, future))
        return await future

    @property
    def depth(self) -> int:
        """Queue depth — exposed for /readyz observability."""
        return self._queue.qsize()

    async def _drain(self) -> None:
        """Drain loop. One session held for the whole drain (commit per submission)."""
        async with get_sessionmaker()() as session:
            while True:
                item = await self._queue.get()
                if item is None:  # shutdown sentinel
                    break
                write_fn, future = item
                try:
                    result = await write_fn(session)
                    await session.commit()
                    if not future.done():
                        future.set_result(result)
                except Exception as exc:
                    await session.rollback()
                    if not future.done():
                        future.set_exception(exc)
                    logger.exception("DBWriteQueue write failed: %s", exc)


# Module-level singleton — wired into lifespan + injected via Depends().
_queue: DBWriteQueue | None = None


def get_write_queue() -> DBWriteQueue:
    """Accessor for the process-wide queue. Created on first access."""
    global _queue
    if _queue is None:
        _queue = DBWriteQueue()
    return _queue


def reset_write_queue_cache() -> None:
    """Test-only — drop the cached queue so the next test gets a fresh one bound to its loop.

    Production code never calls this. Without it, the cached `asyncio.Queue` is bound to
    the first event loop, and subsequent loops (separate TestClient instances) hit
    ``RuntimeError: bound to a different event loop``.
    """
    global _queue
    _queue = None

"""FastAPI lifespan — startup/shutdown hooks (per ARCH-001 §6.5)."""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.db.write_queue import get_write_queue

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Process-wide startup/shutdown.

    Order matters: start the write queue before any code path that might submit to it.
    On shutdown, drain in reverse order with bounded timeout.
    """
    queue = get_write_queue()
    queue.start()

    # TODO(walking-skeleton): startup stale-recovery — reset any state='processing' rows
    # back to state='pending' so a previous interrupted batch resumes cleanly. Tracked
    # in PRD §13 implementation TODOs.

    logger.info("Application started")
    try:
        yield
    finally:
        await queue.stop()
        logger.info("Application stopped")

"""System-health endpoints — /healthz (liveness), /readyz (readiness)."""

from __future__ import annotations

from fastapi import APIRouter, Depends, status
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_session
from app.db.write_queue import get_write_queue

router = APIRouter(tags=["system"])


@router.get("/healthz", status_code=status.HTTP_200_OK)
async def healthz() -> dict[str, str]:
    """Liveness — returns 200 if the process is up. No deps checked."""
    return {"status": "ok"}


@router.get("/readyz", status_code=status.HTTP_200_OK)
async def readyz(session: AsyncSession = Depends(get_session)) -> dict[str, object]:
    """Readiness — checks DB reachable, write queue running, surfaces queue depth."""
    db_ok = False
    try:
        await session.execute(text("SELECT 1"))
        db_ok = True
    except Exception:  # noqa: BLE001 — readiness check intentionally swallows
        db_ok = False

    queue = get_write_queue()
    return {
        "status": "ok" if db_ok else "degraded",
        "checks": {
            "db": db_ok,
            "write_queue_depth": queue.depth,
        },
    }

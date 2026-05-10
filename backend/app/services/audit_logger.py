"""Audit logging for non-LLM events (D-2026-05-10-05 / system_event table).

Every `log_event` writes one row through the DBWriteQueue. Critical events
(`pii_leakage_detected`) ALSO log to stderr via structlog as a backup channel —
if the DB itself is the failure cause, we still get a record in container logs.

Per ARCH-001 §4.1, AuditLogger is a service-layer component that other services
call directly (no router). Routers don't audit; they delegate to a service that
does the work + emits the event.
"""

from __future__ import annotations

import json
import logging
from typing import Literal

from sqlalchemy.ext.asyncio import AsyncSession

from app.db.write_queue import DBWriteQueue
from app.models import SystemEvent

logger = logging.getLogger(__name__)

EventType = Literal[
    "oauth_login",
    "oauth_logout",
    "oauth_revoked",
    "attestation_signed",
    "attestation_invalidated",
    "key_rotated",
    "schema_migrated",
    "batch_started",
    "batch_completed",
    "batch_failed",
    "pii_leakage_detected",
]
Severity = Literal["info", "warning", "critical"]


class AuditLogger:
    def __init__(self, db_write_queue: DBWriteQueue) -> None:
        self._queue = db_write_queue

    async def log_event(
        self,
        event_type: EventType,
        *,
        teacher_id: str | None = None,
        severity: Severity = "info",
        payload: dict | None = None,
    ) -> None:
        """Persist one system_event row.

        For `pii_leakage_detected` we also emit a stderr log line — that's our
        backup channel if the DB write itself fails (per security.md "boundary
        firing is a real incident" anti-pattern guidance: never silently lose).
        """
        if event_type == "pii_leakage_detected":
            logger.critical(
                "pii_leakage_detected teacher_id=%s payload=%s",
                teacher_id,
                payload,
            )

        async def write(session: AsyncSession) -> None:
            ev = SystemEvent(
                teacher_id=teacher_id,
                event_type=event_type,
                severity=severity,
                payload_json=json.dumps(payload, ensure_ascii=False) if payload else None,
            )
            session.add(ev)

        await self._queue.submit(write)

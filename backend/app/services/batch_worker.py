"""BatchWorker — multi-file processing orchestrator (DESIGN-001 §4.6).

Walking-skeleton scope:
- start_job creates a batch_job row, picks all files for a semester with state in
  (pending, reprocess_pending), spawns ONE background task with Semaphore(N) to
  process them concurrently.
- Per-file failure mapping (per D-2026-05-10-04 / architecture.md):
  - UnsupportedFormatError / DocumentExtractionError → state='unprocessable' (terminal)
  - LLMRateLimitError / LLMTimeoutError → state='failed' (retriable; teacher manual retry)
  - LLMQuotaExceededError → pause batch (state='paused')
- Each file event published on `batch:<id>` topic for SSE subscribers.
- recover_stale_jobs runs in lifespan startup to reset 'processing' rows that
  were interrupted (process restart mid-batch).

Out of scope for Phase 5alt (deferred to 5alt-2):
- Auto-retry with exponential backoff inside the worker (currently lets `failed`
  rows wait for manual retry)
- Multi-job concurrency (only one active batch_job per teacher in V1; queueing
  not implemented)
- decision-driven `reprocess_pending` overwrite/keep prompts (Phase 5alt-2 — for
  now reprocess_pending rows are processed regardless)
"""

from __future__ import annotations

import asyncio
import json
import logging
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import Settings
from app.core.exceptions import (
    DocumentExtractionError,
    DriveError,
    LLMQuotaExhaustedError,
    LLMRateLimitError,
    LLMTimeoutError,
    UnsupportedFormatError,
)
from app.db.session import get_sessionmaker
from app.db.write_queue import DBWriteQueue
from app.models import BatchJob, DriveFile, ProcessedArtifact
from app.models._helpers import gen_uuid, utcnow_iso
from app.services.audit_logger import AuditLogger
from app.services.processing_pipeline import ProcessingPipeline
from app.services.sse_publisher import SSEPublisher

logger = logging.getLogger(__name__)


@dataclass
class BatchSnapshot:
    batch_job_id: str
    status: str
    total: int
    completed: int
    failed: int
    total_cost_usd: float | None
    started_at: str
    finished_at: str | None


class BatchWorker:
    def __init__(
        self,
        *,
        settings: Settings,
        pipeline: ProcessingPipeline,
        db_write_queue: DBWriteQueue,
        sse: SSEPublisher,
        audit: AuditLogger,
    ) -> None:
        self._settings = settings
        self._pipeline = pipeline
        self._queue = db_write_queue
        self._sse = sse
        self._audit = audit
        # batch_job_id → asyncio.Event for soft cancellation
        self._cancellations: dict[str, asyncio.Event] = {}
        # batch_job_id → background task handle (kept so the GC doesn't collect mid-run)
        self._background: dict[str, asyncio.Task] = {}

    # ── Public surface ──────────────────────────────────────────

    async def start_job(
        self, *, teacher_id: str, semester_label: str
    ) -> str:
        """Create batch_job, schedule processing, return batch_job_id.

        Picks files for `semester_label` with state in (pending, reprocess_pending);
        marks each as 'processing'; spawns the worker task; returns immediately.
        """
        # Find candidate artifacts (we work at the artifact level — one per drive_file)
        candidates = await self._collect_candidates(
            teacher_id=teacher_id, semester_label=semester_label
        )
        total = len(candidates)
        batch_id = gen_uuid()

        async def insert_job(session: AsyncSession) -> str:
            session.add(
                BatchJob(
                    id=batch_id,
                    teacher_id=teacher_id,
                    semester_label=semester_label,
                    status="running" if total > 0 else "completed",
                    total=total,
                    completed=0,
                    failed=0,
                    started_at=utcnow_iso(),
                    finished_at=utcnow_iso() if total == 0 else None,
                )
            )
            return batch_id
        await self._queue.submit(insert_job)

        await self._audit.log_event(
            "batch_started",
            teacher_id=teacher_id,
            payload={"batch_job_id": batch_id, "semester": semester_label, "total": total},
        )

        if total == 0:
            await self._sse.publish(
                f"batch:{batch_id}",
                _event(batch_id, "completed", total=0, completed=0, failed=0),
            )
            return batch_id

        cancel = asyncio.Event()
        self._cancellations[batch_id] = cancel
        task = asyncio.create_task(
            self._run(
                teacher_id=teacher_id,
                batch_job_id=batch_id,
                drive_file_ids=candidates,
                cancel=cancel,
            ),
            name=f"batch-{batch_id}",
        )
        self._background[batch_id] = task
        # Detach completion → cleanup
        task.add_done_callback(lambda _t: self._background.pop(batch_id, None))
        return batch_id

    async def cancel_job(self, *, batch_job_id: str) -> None:
        """Soft cancel — in-flight files finish; no new files picked."""
        ev = self._cancellations.get(batch_job_id)
        if ev is not None:
            ev.set()

    async def get_status(self, *, batch_job_id: str) -> BatchSnapshot | None:
        async with get_sessionmaker()() as session:
            row = await session.get(BatchJob, batch_job_id)
        if row is None:
            return None
        return BatchSnapshot(
            batch_job_id=row.id,
            status=row.status,
            total=row.total,
            completed=row.completed,
            failed=row.failed,
            total_cost_usd=row.total_cost_usd,
            started_at=row.started_at,
            finished_at=row.finished_at,
        )

    async def recover_stale_jobs(self) -> int:
        """Reset state='processing' rows back to 'pending'. Run from lifespan startup.

        Conservative: doesn't time-gate (5-minute filter from DESIGN-001 §4.6 is
        Phase 5alt-2 — for V1 walking skeleton any 'processing' on startup is stale
        because there's no other process running).
        """
        async def reset(session: AsyncSession) -> int:
            stale = (
                await session.execute(
                    select(ProcessedArtifact).where(
                        ProcessedArtifact.state == "processing"
                    )
                )
            ).scalars().all()
            for row in stale:
                row.state = "pending"
            return len(stale)
        return await self._queue.submit(reset)

    # ── Internals ────────────────────────────────────────────────

    async def _collect_candidates(
        self, *, teacher_id: str, semester_label: str
    ) -> list[str]:
        """Return drive_file ids that need processing.

        Includes drive_files where:
        - No artifact yet (implicit 'pending'), OR
        - Artifact in state 'pending' or 'reprocess_pending'
        """
        async with get_sessionmaker()() as session:
            files = (
                await session.execute(
                    select(DriveFile).where(
                        DriveFile.teacher_id == teacher_id,
                        DriveFile.semester_label == semester_label,
                        DriveFile.deleted_at.is_(None),
                    )
                )
            ).scalars().all()
            artifacts_by_df = {
                a.drive_file_id: a
                for a in (
                    await session.execute(
                        select(ProcessedArtifact).where(
                            ProcessedArtifact.drive_file_id.in_([f.id for f in files])
                        )
                    )
                ).scalars()
            }

        out: list[str] = []
        for f in files:
            a = artifacts_by_df.get(f.id)
            if a is None or a.state in ("pending", "reprocess_pending"):
                out.append(f.id)
        return out

    async def _run(
        self,
        *,
        teacher_id: str,
        batch_job_id: str,
        drive_file_ids: list[str],
        cancel: asyncio.Event,
    ) -> None:
        """Worker entrypoint — Semaphore-bounded concurrent processing."""
        semaphore = asyncio.Semaphore(self._settings.batch_worker_concurrency)
        completed = 0
        failed = 0
        total_cost = 0.0
        paused = False

        async def process_one(drive_file_id: str) -> tuple[bool, float, str | None]:
            """Returns (success, cost_usd, terminal_or_failed_reason)."""
            if cancel.is_set():
                return False, 0.0, "cancelled"

            # Mark 'processing'
            async def to_processing(session: AsyncSession) -> None:
                await self._upsert_artifact_state(
                    session, drive_file_id=drive_file_id, state="processing"
                )
            await self._queue.submit(to_processing)

            # Look up the row (need DriveFile object for pipeline)
            async with get_sessionmaker()() as session:
                drive_file = await session.get(DriveFile, drive_file_id)
            if drive_file is None:
                return False, 0.0, "drive_file_missing"

            try:
                async with semaphore:
                    result = await self._pipeline.process(
                        teacher_id=teacher_id, drive_file=drive_file
                    )
            except (UnsupportedFormatError, DocumentExtractionError) as exc:
                await self._mark_unprocessable(
                    drive_file_id=drive_file_id, reason=str(exc)
                )
                return False, 0.0, "unprocessable"
            except (LLMRateLimitError, LLMTimeoutError, DriveError) as exc:
                await self._mark_failed(
                    drive_file_id=drive_file_id, reason=str(exc)
                )
                return False, 0.0, "failed"
            except LLMQuotaExhaustedError as exc:
                logger.warning("Quota exhausted; pausing batch %s: %s", batch_job_id, exc)
                # Reset to pending so we resume cleanly later
                await self._mark_pending(drive_file_id=drive_file_id)
                return False, 0.0, "quota_paused"

            # Success — persist the artifact with full result
            await self._mark_processed(drive_file_id=drive_file_id, result=result)
            return True, float(result.llm_cost_usd), None

        for df_id in drive_file_ids:
            if cancel.is_set():
                break
            ok, cost, reason = await process_one(df_id)
            if reason == "quota_paused":
                paused = True
                break
            if ok:
                completed += 1
                total_cost += cost
            else:
                failed += 1

            # Update batch_job counters + publish progress
            await self._update_batch_progress(
                batch_job_id=batch_job_id,
                completed=completed,
                failed=failed,
                total_cost=total_cost,
            )
            await self._sse.publish(
                f"batch:{batch_job_id}",
                _event(
                    batch_job_id,
                    state="running",
                    total=len(drive_file_ids),
                    completed=completed,
                    failed=failed,
                    last_event={"drive_file_id": df_id, "ok": ok, "reason": reason},
                ),
            )

        # Finalise
        if cancel.is_set():
            final_status = "cancelled"
        elif paused:
            final_status = "failed"
        else:
            final_status = "completed"

        await self._finalise_batch(
            batch_job_id=batch_job_id,
            status=final_status,
            total_cost=total_cost,
        )
        await self._sse.publish(
            f"batch:{batch_job_id}",
            _event(
                batch_job_id,
                state=final_status,
                total=len(drive_file_ids),
                completed=completed,
                failed=failed,
            ),
        )
        await self._audit.log_event(
            "batch_completed" if final_status == "completed" else "batch_failed",
            teacher_id=teacher_id,
            payload={
                "batch_job_id": batch_job_id,
                "completed": completed,
                "failed": failed,
                "status": final_status,
            },
        )
        self._cancellations.pop(batch_job_id, None)

    # ── DB helpers (all funnelled through DBWriteQueue) ─────────

    @staticmethod
    async def _upsert_artifact_state(
        session: AsyncSession, *, drive_file_id: str, state: str
    ) -> None:
        existing = (
            await session.execute(
                select(ProcessedArtifact).where(
                    ProcessedArtifact.drive_file_id == drive_file_id,
                    ProcessedArtifact.artifact_type == "markdown_summary",
                )
            )
        ).scalar_one_or_none()
        if existing is None:
            session.add(
                ProcessedArtifact(
                    id=gen_uuid(),
                    drive_file_id=drive_file_id,
                    artifact_type="markdown_summary",
                    state=state,
                )
            )
        else:
            existing.state = state

    async def _mark_processed(self, *, drive_file_id: str, result) -> None:
        async def update(session: AsyncSession) -> None:
            existing = (
                await session.execute(
                    select(ProcessedArtifact).where(
                        ProcessedArtifact.drive_file_id == drive_file_id,
                        ProcessedArtifact.artifact_type == "markdown_summary",
                    )
                )
            ).scalar_one_or_none()
            if existing is None:
                session.add(
                    ProcessedArtifact(
                        id=gen_uuid(),
                        drive_file_id=drive_file_id,
                        artifact_type="markdown_summary",
                        state="processed",
                        content_markdown=result.content_markdown,
                        source_content_hash=result.content_hash,
                        llm_tier=result.llm_tier.value,
                        llm_model=result.llm_model,
                        llm_cost_usd=float(result.llm_cost_usd),
                        processed_at=utcnow_iso(),
                    )
                )
            else:
                existing.state = "processed"
                existing.content_markdown = result.content_markdown
                existing.source_content_hash = result.content_hash
                existing.llm_tier = result.llm_tier.value
                existing.llm_model = result.llm_model
                existing.llm_cost_usd = float(result.llm_cost_usd)
                existing.processed_at = utcnow_iso()
                existing.failure_reason = None
            # Update drive_file content_hash too
            df = await session.get(DriveFile, drive_file_id)
            if df is not None:
                df.content_hash = result.content_hash
        await self._queue.submit(update)

    async def _mark_unprocessable(self, *, drive_file_id: str, reason: str) -> None:
        async def update(session: AsyncSession) -> None:
            existing = (
                await session.execute(
                    select(ProcessedArtifact).where(
                        ProcessedArtifact.drive_file_id == drive_file_id,
                        ProcessedArtifact.artifact_type == "markdown_summary",
                    )
                )
            ).scalar_one_or_none()
            if existing is None:
                session.add(
                    ProcessedArtifact(
                        id=gen_uuid(),
                        drive_file_id=drive_file_id,
                        artifact_type="markdown_summary",
                        state="unprocessable",
                        failure_reason=reason,
                    )
                )
            else:
                existing.state = "unprocessable"
                existing.failure_reason = reason
        await self._queue.submit(update)

    async def _mark_failed(self, *, drive_file_id: str, reason: str) -> None:
        async def update(session: AsyncSession) -> None:
            existing = (
                await session.execute(
                    select(ProcessedArtifact).where(
                        ProcessedArtifact.drive_file_id == drive_file_id,
                        ProcessedArtifact.artifact_type == "markdown_summary",
                    )
                )
            ).scalar_one_or_none()
            if existing is None:
                session.add(
                    ProcessedArtifact(
                        id=gen_uuid(),
                        drive_file_id=drive_file_id,
                        artifact_type="markdown_summary",
                        state="failed",
                        failure_reason=reason,
                        retry_count=1,
                    )
                )
            else:
                existing.state = "failed"
                existing.failure_reason = reason
                existing.retry_count = (existing.retry_count or 0) + 1
        await self._queue.submit(update)

    async def _mark_pending(self, *, drive_file_id: str) -> None:
        async def update(session: AsyncSession) -> None:
            await self._upsert_artifact_state(
                session, drive_file_id=drive_file_id, state="pending"
            )
        await self._queue.submit(update)

    async def _update_batch_progress(
        self,
        *,
        batch_job_id: str,
        completed: int,
        failed: int,
        total_cost: float,
    ) -> None:
        async def update(session: AsyncSession) -> None:
            row = await session.get(BatchJob, batch_job_id)
            if row is not None:
                row.completed = completed
                row.failed = failed
                row.total_cost_usd = total_cost
        await self._queue.submit(update)

    async def _finalise_batch(
        self, *, batch_job_id: str, status: str, total_cost: float
    ) -> None:
        async def update(session: AsyncSession) -> None:
            row = await session.get(BatchJob, batch_job_id)
            if row is not None:
                row.status = status
                row.total_cost_usd = total_cost
                row.finished_at = utcnow_iso()
        await self._queue.submit(update)


def _event(
    batch_job_id: str,
    state: str,
    *,
    total: int = 0,
    completed: int = 0,
    failed: int = 0,
    last_event: dict | None = None,
) -> dict:
    return {
        "batch_job_id": batch_job_id,
        "state": state,
        "total": total,
        "completed": completed,
        "failed": failed,
        "last_event": last_event,
    }


# Module singleton — wired via DI in routers
_worker: BatchWorker | None = None


def get_batch_worker_factory():
    """Returns a callable a router uses with Depends to construct a worker.

    We can't keep the BatchWorker as a process-wide singleton because
    `pipeline` and `audit` depend on per-request dependencies. Instead each
    /batch/* request constructs a fresh worker with the same singletons
    underneath (queue, SSE publisher).
    """
    return _worker

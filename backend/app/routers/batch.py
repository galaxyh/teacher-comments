"""Batch routes — start, cancel, status, SSE events."""

from __future__ import annotations

import asyncio
import logging

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import StreamingResponse

from app.adapters.openrouter_client import OpenRouterClient
from app.config import Settings, get_settings
from app.db.write_queue import DBWriteQueue, get_write_queue
from app.models import Teacher
from app.routers.auth import get_auth_service, get_current_teacher
from app.schemas.batch import (
    BatchStatusResponse,
    StartBatchRequest,
    StartBatchResponse,
)
from app.services.audit_logger import AuditLogger
from app.services.auth_service import AuthService
from app.services.batch_worker import BatchWorker
from app.services.llm_service import LLMService
from app.services.pii_anonymizer import PIIAnonymizer
from app.services.processing_pipeline import ProcessingPipeline
from app.services.sse_publisher import SSEPublisher, get_sse_publisher

logger = logging.getLogger(__name__)
router = APIRouter(tags=["batch"])


def get_batch_worker(
    settings: Settings = Depends(get_settings),
    queue: DBWriteQueue = Depends(get_write_queue),
    sse: SSEPublisher = Depends(get_sse_publisher),
    auth: AuthService = Depends(get_auth_service),
) -> BatchWorker:
    """Compose pipeline + worker. Tests override at this seam."""
    from app.adapters.document_extractors import build_default_registry
    from app.adapters.drive_client import DriveClient

    audit = AuditLogger(queue)
    anonymizer = PIIAnonymizer(db_write_queue=queue)
    openrouter = OpenRouterClient(
        api_key=settings.openrouter_api_key.get_secret_value(),
        base_url=settings.openrouter_base_url,
    )
    llm = LLMService(
        settings=settings,
        anonymizer=anonymizer,
        openrouter=openrouter,
        audit=audit,
        db_write_queue=queue,
    )

    async def drive_client_factory(*, teacher_id: str) -> DriveClient:
        creds = await auth.get_credentials(teacher_id=teacher_id)
        return DriveClient(creds)

    pipeline = ProcessingPipeline(
        drive_client_factory=drive_client_factory,
        extractors=build_default_registry(),
        llm=llm,
    )
    return BatchWorker(
        settings=settings,
        pipeline=pipeline,
        db_write_queue=queue,
        sse=sse,
        audit=audit,
    )


@router.post("/batch/start", response_model=StartBatchResponse, status_code=status.HTTP_202_ACCEPTED)
async def start_batch(
    body: StartBatchRequest,
    teacher: Teacher = Depends(get_current_teacher),
    worker: BatchWorker = Depends(get_batch_worker),
) -> StartBatchResponse:
    batch_id = await worker.start_job(
        teacher_id=teacher.id, semester_label=body.semester_label
    )
    snapshot = await worker.get_status(batch_job_id=batch_id)
    assert snapshot is not None
    return StartBatchResponse(
        batch_job_id=batch_id, total=snapshot.total, status=snapshot.status
    )


@router.post("/batch/{batch_job_id}/cancel", status_code=status.HTTP_202_ACCEPTED)
async def cancel_batch(
    batch_job_id: str,
    teacher: Teacher = Depends(get_current_teacher),
    worker: BatchWorker = Depends(get_batch_worker),
) -> dict[str, str]:
    snapshot = await worker.get_status(batch_job_id=batch_job_id)
    if snapshot is None:
        raise HTTPException(status_code=404, detail={"reason": "batch_not_found"})
    await worker.cancel_job(batch_job_id=batch_job_id)
    return {"status": "cancelling"}


@router.get("/batch/{batch_job_id}/status", response_model=BatchStatusResponse)
async def get_status(
    batch_job_id: str,
    teacher: Teacher = Depends(get_current_teacher),
    worker: BatchWorker = Depends(get_batch_worker),
) -> BatchStatusResponse:
    snapshot = await worker.get_status(batch_job_id=batch_job_id)
    if snapshot is None:
        raise HTTPException(status_code=404, detail={"reason": "batch_not_found"})
    return BatchStatusResponse(**snapshot.__dict__)


@router.get("/batch/{batch_job_id}/events")
async def stream_events(
    batch_job_id: str,
    teacher: Teacher = Depends(get_current_teacher),
    sse: SSEPublisher = Depends(get_sse_publisher),
) -> StreamingResponse:
    """Server-Sent Events stream for batch progress.

    Per ARCH-001 §3.2 — each `data: {...}\\n\\n` is one BatchJobUpdate. Late
    subscribers miss earlier events; combine with /batch/{id}/status to fetch
    the current snapshot on connect.
    """
    topic = f"batch:{batch_job_id}"

    async def event_stream():
        # Send a leading retry hint so reconnects use 5s instead of browser default
        yield b"retry: 5000\n\n"
        async for event in sse.subscribe(topic):
            yield SSEPublisher.format_sse(event)
            # If terminal state, end the stream
            if event.get("state") in ("completed", "failed", "cancelled"):
                return

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",  # disable proxy buffering (nginx etc.)
        },
    )

"""Single-file processing route — Phase 4b walking-skeleton verifier.

`POST /file/{drive_file_id}/process` runs the full pipeline (download → extract →
LLM summarise → restore) synchronously and persists a processed_artifact row.
The async batch endpoint (`POST /batch/start`) is Phase 5 work.

`GET /file/{drive_file_id}/artifact` returns the latest artifact for a file —
used by the file-detail UI screen.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.adapters.document_extractors import build_default_registry
from app.adapters.drive_client import DriveClient
from app.config import Settings, get_settings
from app.core.exceptions import (
    DocumentExtractionError,
    DriveError,
    LLMRateLimitError,
    LLMTimeoutError,
    UnsupportedFormatError,
)
from app.db.session import get_session, get_sessionmaker
from app.db.write_queue import DBWriteQueue, get_write_queue
from app.models import DriveFile, ProcessedArtifact, Teacher
from app.models._helpers import gen_uuid, utcnow_iso
from app.routers.auth import get_auth_service, get_current_teacher
from app.schemas.files import ProcessedArtifactResponse, ProcessFileResponse
from app.services.audit_logger import AuditLogger
from app.services.auth_service import AuthService
from app.services.llm_service import LLMService
from app.services.pii_anonymizer import PIIAnonymizer
from app.services.processing_pipeline import ProcessingPipeline

logger = logging.getLogger(__name__)
router = APIRouter(tags=["files"])


# ── DI factory ────────────────────────────────────────────────────


def get_processing_pipeline(
    settings: Settings = Depends(get_settings),
    queue: DBWriteQueue = Depends(get_write_queue),
    auth: AuthService = Depends(get_auth_service),
) -> ProcessingPipeline:
    """Compose the pipeline + chokepoints. Tests override at the
    `dependency_overrides` level to inject fakes."""
    from app.adapters.openrouter_client import OpenRouterClient

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

    return ProcessingPipeline(
        drive_client_factory=drive_client_factory,
        extractors=build_default_registry(),
        llm=llm,
    )


# ── Routes ────────────────────────────────────────────────────────


@router.post("/file/{drive_file_id}/process", response_model=ProcessFileResponse)
async def process_file(
    drive_file_id: str,
    teacher: Teacher = Depends(get_current_teacher),
    pipeline: ProcessingPipeline = Depends(get_processing_pipeline),
    queue: DBWriteQueue = Depends(get_write_queue),
    session: AsyncSession = Depends(get_session),
) -> ProcessFileResponse:
    """Synchronously run the full pipeline for one drive_file row.

    For Phase 4b walking-skeleton verification. Production batches go through
    /batch/start (Phase 5).
    """
    # Look up drive_file
    drive_file = (
        await session.execute(
            select(DriveFile).where(
                DriveFile.id == drive_file_id,
                DriveFile.teacher_id == teacher.id,
            )
        )
    ).scalar_one_or_none()
    if drive_file is None:
        raise HTTPException(status_code=404, detail={"reason": "drive_file_not_found"})

    # Run pipeline. Map terminal vs retriable to HTTP semantics:
    # - UnsupportedFormatError / DocumentExtractionError → 415 (terminal)
    # - LLMRateLimitError / LLMTimeoutError → 503 (retriable; client should backoff)
    # - DriveError (Drive API outage) → 502
    try:
        result = await pipeline.process(teacher_id=teacher.id, drive_file=drive_file)
    except UnsupportedFormatError as exc:
        await _record_terminal_failure(
            queue=queue,
            drive_file_id=drive_file.id,
            failure_reason=str(exc),
        )
        raise HTTPException(
            status_code=415,
            detail={"reason": "unsupported_format", "message": str(exc)},
        ) from exc
    except DocumentExtractionError as exc:
        await _record_terminal_failure(
            queue=queue,
            drive_file_id=drive_file.id,
            failure_reason=str(exc),
        )
        raise HTTPException(
            status_code=415,
            detail={"reason": "extraction_failed", "message": str(exc)},
        ) from exc
    except (LLMRateLimitError, LLMTimeoutError) as exc:
        # Retriable — leave artifact in 'failed' if a row exists, else don't write
        raise HTTPException(
            status_code=503,
            detail={"reason": "llm_unavailable", "retry_after": 60, "message": str(exc)},
        ) from exc
    except DriveError as exc:
        raise HTTPException(
            status_code=502,
            detail={"reason": "drive_api_error", "message": str(exc)},
        ) from exc

    # Persist artifact + drive_file content_hash via DBWriteQueue
    artifact_id = await _upsert_artifact(
        queue=queue,
        drive_file_id=drive_file.id,
        result=result,
    )
    await _update_content_hash(
        queue=queue, drive_file_id=drive_file.id, content_hash=result.content_hash
    )

    # Re-read for response (after queue commit)
    async with get_sessionmaker()() as fresh:
        artifact = await fresh.get(ProcessedArtifact, artifact_id)
    assert artifact is not None

    return ProcessFileResponse(
        artifact=_to_response(artifact),
        cost_usd=float(result.llm_cost_usd),
        warnings=result.warnings,
    )


@router.get(
    "/file/{drive_file_id}/artifact", response_model=ProcessedArtifactResponse
)
async def get_artifact(
    drive_file_id: str,
    teacher: Teacher = Depends(get_current_teacher),
    session: AsyncSession = Depends(get_session),
) -> ProcessedArtifactResponse:
    drive_file = (
        await session.execute(
            select(DriveFile).where(
                DriveFile.id == drive_file_id,
                DriveFile.teacher_id == teacher.id,
            )
        )
    ).scalar_one_or_none()
    if drive_file is None:
        raise HTTPException(status_code=404, detail={"reason": "drive_file_not_found"})

    artifact = (
        await session.execute(
            select(ProcessedArtifact).where(
                ProcessedArtifact.drive_file_id == drive_file.id,
                ProcessedArtifact.artifact_type == "markdown_summary",
            )
        )
    ).scalar_one_or_none()
    if artifact is None:
        raise HTTPException(status_code=404, detail={"reason": "no_artifact_yet"})
    return _to_response(artifact)


# ── helpers ───────────────────────────────────────────────────────


async def _upsert_artifact(
    *,
    queue: DBWriteQueue,
    drive_file_id: str,
    result,  # ProcessingResult
) -> str:
    artifact_id = gen_uuid()

    async def upsert(session: AsyncSession) -> str:
        existing = (
            await session.execute(
                select(ProcessedArtifact).where(
                    ProcessedArtifact.drive_file_id == drive_file_id,
                    ProcessedArtifact.artifact_type == "markdown_summary",
                )
            )
        ).scalar_one_or_none()
        if existing is None:
            row = ProcessedArtifact(
                id=artifact_id,
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
            session.add(row)
            return artifact_id
        # Existing → UPDATE
        existing.state = "processed"
        existing.content_markdown = result.content_markdown
        existing.source_content_hash = result.content_hash
        existing.llm_tier = result.llm_tier.value
        existing.llm_model = result.llm_model
        existing.llm_cost_usd = float(result.llm_cost_usd)
        existing.processed_at = utcnow_iso()
        existing.failure_reason = None
        return existing.id

    return await queue.submit(upsert)


async def _update_content_hash(
    *, queue: DBWriteQueue, drive_file_id: str, content_hash: str
) -> None:
    async def update(session: AsyncSession) -> None:
        row = await session.get(DriveFile, drive_file_id)
        if row is not None:
            row.content_hash = content_hash

    await queue.submit(update)


async def _record_terminal_failure(
    *, queue: DBWriteQueue, drive_file_id: str, failure_reason: str
) -> None:
    """Mark/insert artifact as `unprocessable` (terminal — D-2026-05-10-04)."""
    async def upsert(session: AsyncSession) -> None:
        existing = (
            await session.execute(
                select(ProcessedArtifact).where(
                    ProcessedArtifact.drive_file_id == drive_file_id,
                    ProcessedArtifact.artifact_type == "markdown_summary",
                )
            )
        ).scalar_one_or_none()
        if existing is None:
            row = ProcessedArtifact(
                id=gen_uuid(),
                drive_file_id=drive_file_id,
                artifact_type="markdown_summary",
                state="unprocessable",
                failure_reason=failure_reason,
            )
            session.add(row)
        else:
            existing.state = "unprocessable"
            existing.failure_reason = failure_reason

    await queue.submit(upsert)


def _to_response(artifact: ProcessedArtifact) -> ProcessedArtifactResponse:
    return ProcessedArtifactResponse(
        id=artifact.id,
        drive_file_id=artifact.drive_file_id,
        artifact_type=artifact.artifact_type,
        state=artifact.state,
        content_markdown=artifact.content_markdown,
        llm_tier=artifact.llm_tier,
        llm_model=artifact.llm_model,
        llm_cost_usd=artifact.llm_cost_usd,
        processed_at=artifact.processed_at,
        teacher_edited_at=artifact.teacher_edited_at,
    )

"""Evaluation router — context fetch, generate, edit, get (PRD §3.2 Flow C)."""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException

from app.adapters.openrouter_client import OpenRouterClient
from app.config import Settings, get_settings
from app.core.exceptions import LLMRateLimitError, LLMTimeoutError, PIILeakageError
from app.db.write_queue import DBWriteQueue, get_write_queue
from app.models import Teacher
from app.routers.auth import get_current_teacher
from app.schemas.evaluation import (
    EditEvaluationRequest,
    EvaluationContextResponse,
    EvaluationResponse,
    GenerateEvaluationRequest,
)
from app.services.audit_logger import AuditLogger
from app.services.evaluation_generator import (
    EvaluationGenerator,
    NoArtifactsError,
)
from app.services.llm_service import LLMService
from app.services.pii_anonymizer import PIIAnonymizer

logger = logging.getLogger(__name__)
router = APIRouter(tags=["evaluation"])


def get_evaluation_generator(
    settings: Settings = Depends(get_settings),
    queue: DBWriteQueue = Depends(get_write_queue),
) -> EvaluationGenerator:
    """Compose EvaluationGenerator + LLMService chokepoint. Tests override this."""
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
    return EvaluationGenerator(llm=llm, db_write_queue=queue)


@router.get(
    "/eval/{semester_label}/{student_pseudo_id}/context",
    response_model=EvaluationContextResponse,
)
async def get_context(
    semester_label: str,
    student_pseudo_id: str,
    teacher: Teacher = Depends(get_current_teacher),
    gen: EvaluationGenerator = Depends(get_evaluation_generator),
) -> EvaluationContextResponse:
    """Pre-generation: list the artifact summaries the editor screen displays."""
    ctx = await gen.gather_context(
        teacher_id=teacher.id,
        semester_label=semester_label,
        pseudo_id=student_pseudo_id,
    )
    return EvaluationContextResponse(
        learning_summaries=ctx.learning_summaries,
        interaction_transcripts=ctx.interaction_transcripts,
        work_summaries=ctx.work_summaries,
    )


@router.post("/eval/generate", response_model=EvaluationResponse)
async def generate(
    body: GenerateEvaluationRequest,
    teacher: Teacher = Depends(get_current_teacher),
    gen: EvaluationGenerator = Depends(get_evaluation_generator),
) -> EvaluationResponse:
    try:
        generated = await gen.generate(
            teacher_id=teacher.id,
            semester_label=body.semester_label,
            pseudo_id=body.student_pseudo_id,
            seed_text=body.seed_text,
            style=body.style,
        )
    except NoArtifactsError as exc:
        # 412 Precondition Failed — the teacher hasn't processed this student's files yet
        raise HTTPException(
            status_code=412,
            detail={"reason": "no_artifacts", "message": str(exc)},
        ) from exc
    except (LLMRateLimitError, LLMTimeoutError) as exc:
        raise HTTPException(
            status_code=503,
            detail={"reason": "llm_unavailable", "retry_after": 60, "message": str(exc)},
        ) from exc
    except PIILeakageError as exc:
        # Boundary trip — internal bug. Don't leak details to client.
        raise HTTPException(
            status_code=500, detail={"reason": "pii_boundary_tripped"}
        ) from exc

    row = await gen.get(evaluation_id=generated.evaluation_id)
    assert row is not None
    return EvaluationResponse(
        id=row.id,
        teacher_id=row.teacher_id,
        semester_label=row.semester_label,
        student_pseudo_id=row.student_pseudo_id,
        seed_text=row.seed_text,
        style=row.style,  # type: ignore[arg-type]
        generated_text=row.generated_text,
        edited_text=row.edited_text,
        llm_model=row.llm_model,
        llm_cost_usd=row.llm_cost_usd,
        generated_at=row.generated_at,
        edited_at=row.edited_at,
    )


@router.put("/eval/{evaluation_id}", response_model=EvaluationResponse)
async def edit(
    evaluation_id: str,
    body: EditEvaluationRequest,
    teacher: Teacher = Depends(get_current_teacher),
    gen: EvaluationGenerator = Depends(get_evaluation_generator),
) -> EvaluationResponse:
    existing = await gen.get(evaluation_id=evaluation_id)
    if existing is None or existing.teacher_id != teacher.id:
        raise HTTPException(status_code=404, detail={"reason": "evaluation_not_found"})

    row = await gen.save_edit(
        evaluation_id=evaluation_id, edited_text=body.edited_text
    )
    return EvaluationResponse(
        id=row.id,
        teacher_id=row.teacher_id,
        semester_label=row.semester_label,
        student_pseudo_id=row.student_pseudo_id,
        seed_text=row.seed_text,
        style=row.style,  # type: ignore[arg-type]
        generated_text=row.generated_text,
        edited_text=row.edited_text,
        llm_model=row.llm_model,
        llm_cost_usd=row.llm_cost_usd,
        generated_at=row.generated_at,
        edited_at=row.edited_at,
    )


@router.get("/eval/{evaluation_id}", response_model=EvaluationResponse)
async def get_one(
    evaluation_id: str,
    teacher: Teacher = Depends(get_current_teacher),
    gen: EvaluationGenerator = Depends(get_evaluation_generator),
) -> EvaluationResponse:
    row = await gen.get(evaluation_id=evaluation_id)
    if row is None or row.teacher_id != teacher.id:
        raise HTTPException(status_code=404, detail={"reason": "evaluation_not_found"})
    return EvaluationResponse(
        id=row.id,
        teacher_id=row.teacher_id,
        semester_label=row.semester_label,
        student_pseudo_id=row.student_pseudo_id,
        seed_text=row.seed_text,
        style=row.style,  # type: ignore[arg-type]
        generated_text=row.generated_text,
        edited_text=row.edited_text,
        llm_model=row.llm_model,
        llm_cost_usd=row.llm_cost_usd,
        generated_at=row.generated_at,
        edited_at=row.edited_at,
    )

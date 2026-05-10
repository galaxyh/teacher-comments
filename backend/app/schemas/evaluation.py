"""Evaluation DTOs."""

from __future__ import annotations

from pydantic import BaseModel, Field

from app.services.evaluation_generator import EvaluationStyle


class EvaluationContextResponse(BaseModel):
    """Returned by GET /eval/{semester}/{pseudo_id}/context — what the editor screen
    shows the teacher before they type their seed."""

    learning_summaries: list[str]
    interaction_transcripts: list[str]
    work_summaries: list[str]


class GenerateEvaluationRequest(BaseModel):
    semester_label: str = Field(..., min_length=1)
    student_pseudo_id: str = Field(..., min_length=1)
    seed_text: str = Field(..., min_length=10, max_length=300)
    """30-100 chars suggested; we accept 10-300 to allow flexibility."""
    style: EvaluationStyle


class EvaluationResponse(BaseModel):
    id: str
    teacher_id: str
    semester_label: str
    student_pseudo_id: str
    seed_text: str
    style: EvaluationStyle
    generated_text: str
    edited_text: str | None
    llm_model: str | None
    llm_cost_usd: float | None
    generated_at: str
    edited_at: str | None


class EditEvaluationRequest(BaseModel):
    edited_text: str = Field(..., min_length=1)

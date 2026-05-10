"""File / artifact DTOs."""

from __future__ import annotations

from pydantic import BaseModel


class ProcessedArtifactResponse(BaseModel):
    """Subset of processed_artifact a router returns to the frontend.

    Excludes `failure_reason` / `retry_count` (operator-facing) — UI gets
    them via a separate admin endpoint when needed.
    """

    id: str
    drive_file_id: str
    artifact_type: str
    state: str
    content_markdown: str | None
    llm_tier: str | None
    llm_model: str | None
    llm_cost_usd: float | None
    processed_at: str | None
    teacher_edited_at: str | None


class ProcessFileResponse(BaseModel):
    """Returned by POST /file/{drive_file_id}/process — synchronous single-file.

    For batch processing (Phase 5), see /batch/start which returns 202 + SSE.
    """

    artifact: ProcessedArtifactResponse
    cost_usd: float
    warnings: list[str] = []

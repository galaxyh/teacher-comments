"""Batch DTOs."""

from __future__ import annotations

from pydantic import BaseModel, Field


class StartBatchRequest(BaseModel):
    semester_label: str = Field(..., min_length=1)


class StartBatchResponse(BaseModel):
    batch_job_id: str
    total: int
    status: str


class BatchStatusResponse(BaseModel):
    batch_job_id: str
    status: str
    total: int
    completed: int
    failed: int
    total_cost_usd: float | None
    started_at: str
    finished_at: str | None

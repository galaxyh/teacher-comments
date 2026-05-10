"""Batch job (PRD §4.2 / D4 batch processing)."""

from __future__ import annotations

from sqlalchemy import CheckConstraint, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.session import Base
from app.models._helpers import gen_uuid, utcnow_iso

BATCH_STATUSES = ("pending", "running", "completed", "failed", "cancelled")


class BatchJob(Base):
    __tablename__ = "batch_job"
    __table_args__ = (
        CheckConstraint(
            f"status IN ({', '.join(repr(s) for s in BATCH_STATUSES)})",
            name="ck_batch_status",
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=gen_uuid)
    teacher_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("teacher.id"), nullable=False, index=True
    )
    semester_label: Mapped[str] = mapped_column(String, nullable=False)

    status: Mapped[str] = mapped_column(String, nullable=False, default="pending")
    total: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    completed: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    failed: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    total_cost_usd: Mapped[float | None] = mapped_column(Float, nullable=True)

    decisions_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    error_summary: Mapped[str | None] = mapped_column(Text, nullable=True)

    started_at: Mapped[str] = mapped_column(String, default=utcnow_iso, nullable=False)
    finished_at: Mapped[str | None] = mapped_column(String, nullable=True)

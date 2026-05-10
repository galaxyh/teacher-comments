"""Semester evaluation — LLM draft + teacher edit (PRD §4.2, D12)."""

from __future__ import annotations

from sqlalchemy import (
    CheckConstraint,
    Float,
    ForeignKey,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.session import Base
from app.models._helpers import gen_uuid, utcnow_iso

EVAL_STYLES = ("formal", "encouraging", "objective")  # D12: replaces prior "neutral"


class SemesterEvaluation(Base):
    __tablename__ = "semester_evaluation"
    __table_args__ = (
        UniqueConstraint(
            "teacher_id",
            "semester_label",
            "student_pseudo_id",
            name="uq_eval_teacher_semester_student",
        ),
        CheckConstraint(
            f"style IN ({', '.join(repr(s) for s in EVAL_STYLES)})",
            name="ck_eval_style",
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=gen_uuid)
    teacher_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("teacher.id"), nullable=False, index=True
    )
    semester_label: Mapped[str] = mapped_column(String, nullable=False)
    student_pseudo_id: Mapped[str] = mapped_column(String, nullable=False)

    seed_text: Mapped[str] = mapped_column(Text, nullable=False)
    style: Mapped[str] = mapped_column(String, nullable=False)

    # generated_text holds the LLM draft (PII already restored for display).
    # edited_text is the teacher's final version. Audit trail preserved (ARCH-001 §3.3).
    generated_text: Mapped[str] = mapped_column(Text, nullable=False)
    edited_text: Mapped[str | None] = mapped_column(Text, nullable=True)

    llm_model: Mapped[str | None] = mapped_column(String, nullable=True)
    llm_cost_usd: Mapped[float | None] = mapped_column(Float, nullable=True)

    generated_at: Mapped[str] = mapped_column(String, default=utcnow_iso, nullable=False)
    edited_at: Mapped[str | None] = mapped_column(String, nullable=True)

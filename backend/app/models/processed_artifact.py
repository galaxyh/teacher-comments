"""Processed artifact + state machine (PRD §4.3, refined per D-2026-05-10-04)."""

from __future__ import annotations

from sqlalchemy import (
    CheckConstraint,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.session import Base
from app.models._helpers import gen_uuid

# Centralised state vocabulary — referenced by services (no string-typo drift).
ARTIFACT_STATES = (
    "pending",
    "processing",
    "processed",
    "teacher_edited",
    "reprocess_pending",
    "failed",          # retriable (D-2026-05-10-04)
    "unprocessable",   # terminal  (D-2026-05-10-04)
)
ARTIFACT_TYPES = ("markdown_summary", "transcript")


class ProcessedArtifact(Base):
    __tablename__ = "processed_artifact"
    __table_args__ = (
        UniqueConstraint(
            "drive_file_id", "artifact_type", name="uq_artifact_file_type"
        ),
        CheckConstraint(
            f"state IN ({', '.join(repr(s) for s in ARTIFACT_STATES)})",
            name="ck_artifact_state",
        ),
        CheckConstraint(
            f"artifact_type IN ({', '.join(repr(t) for t in ARTIFACT_TYPES)})",
            name="ck_artifact_type",
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=gen_uuid)
    drive_file_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("drive_file.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    artifact_type: Mapped[str] = mapped_column(String, nullable=False)
    state: Mapped[str] = mapped_column(String, nullable=False, default="pending", index=True)

    content_markdown: Mapped[str | None] = mapped_column(Text, nullable=True)
    source_content_hash: Mapped[str | None] = mapped_column(String, nullable=True)

    llm_tier: Mapped[str | None] = mapped_column(String, nullable=True)
    llm_model: Mapped[str | None] = mapped_column(String, nullable=True)
    llm_cost_usd: Mapped[float | None] = mapped_column(Float, nullable=True)

    processed_at: Mapped[str | None] = mapped_column(String, nullable=True)
    teacher_edited_at: Mapped[str | None] = mapped_column(String, nullable=True)

    failure_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    retry_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

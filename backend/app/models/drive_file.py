"""Drive file index (PRD §4.2)."""

from __future__ import annotations

from sqlalchemy import CheckConstraint, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db.session import Base
from app.models._helpers import gen_uuid, utcnow_iso


class DriveFile(Base):
    __tablename__ = "drive_file"
    __table_args__ = (
        UniqueConstraint("teacher_id", "drive_file_id", name="uq_drive_file_teacher_drive"),
        CheckConstraint(
            "category IN ('learning', 'interaction', 'work')",
            name="ck_drive_file_category",
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=gen_uuid)
    teacher_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("teacher.id"), nullable=False, index=True
    )

    drive_file_id: Mapped[str] = mapped_column(String, nullable=False)
    semester_label: Mapped[str] = mapped_column(String, nullable=False, index=True)
    student_pseudo_id: Mapped[str] = mapped_column(String, nullable=False, index=True)
    category: Mapped[str] = mapped_column(String, nullable=False)

    drive_path: Mapped[str] = mapped_column(String, nullable=False)
    filename: Mapped[str] = mapped_column(String, nullable=False)
    mime_type: Mapped[str] = mapped_column(String, nullable=False)
    size_bytes: Mapped[int | None] = mapped_column(Integer, nullable=True)
    drive_modified_at: Mapped[str] = mapped_column(String, nullable=False)
    content_hash: Mapped[str | None] = mapped_column(String, nullable=True)

    indexed_at: Mapped[str] = mapped_column(String, default=utcnow_iso, nullable=False)
    deleted_at: Mapped[str | None] = mapped_column(String, nullable=True)

"""PII anonymisation mapping (PRD §4.2, security.md "Anonymize-Restore Round-Trip")."""

from __future__ import annotations

from sqlalchemy import (
    CheckConstraint,
    ForeignKey,
    LargeBinary,
    String,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.session import Base
from app.models._helpers import gen_uuid, utcnow_iso

PII_TYPES = (
    "student_name",
    "student_id",
    "parent_name",
    "phone",
    "address",
    "email",
    "other_name",
    "other",
)


class PIIMapping(Base):
    __tablename__ = "pii_mapping"
    __table_args__ = (
        UniqueConstraint("teacher_id", "pseudonym", name="uq_pii_pseudonym"),
        UniqueConstraint(
            "teacher_id",
            "pii_type",
            "original_value_encrypted",
            name="uq_pii_value",
        ),
        CheckConstraint(
            f"pii_type IN ({', '.join(repr(t) for t in PII_TYPES)})",
            name="ck_pii_type",
        ),
        CheckConstraint("source IN ('auto', 'manual')", name="ck_pii_source"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=gen_uuid)
    teacher_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("teacher.id"), nullable=False, index=True
    )

    pii_type: Mapped[str] = mapped_column(String, nullable=False)
    original_value_encrypted: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)
    pseudonym: Mapped[str] = mapped_column(String, nullable=False, index=True)
    display_name: Mapped[str | None] = mapped_column(String, nullable=True)

    scope: Mapped[str] = mapped_column(String, default="global", nullable=False)
    source: Mapped[str] = mapped_column(String, default="auto", nullable=False)

    created_at: Mapped[str] = mapped_column(String, default=utcnow_iso, nullable=False)

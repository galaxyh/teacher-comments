"""Non-LLM audit events (D-2026-05-10-05).

Captures oauth_login / oauth_logout / oauth_revoked / attestation_signed /
attestation_invalidated / key_rotated / schema_migrated / batch_started /
batch_completed / batch_failed / pii_leakage_detected.

`pii_leakage_detected` is the critical alert channel — it must never be silently
lost (see security.md Layer 2 boundary check).
"""

from __future__ import annotations

from sqlalchemy import CheckConstraint, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.session import Base
from app.models._helpers import gen_uuid, utcnow_iso

EVENT_TYPES = (
    "oauth_login",
    "oauth_logout",
    "oauth_revoked",
    "attestation_signed",
    "attestation_invalidated",
    "key_rotated",
    "schema_migrated",
    "batch_started",
    "batch_completed",
    "batch_failed",
    "pii_leakage_detected",
)


class SystemEvent(Base):
    __tablename__ = "system_event"
    __table_args__ = (
        CheckConstraint(
            f"event_type IN ({', '.join(repr(t) for t in EVENT_TYPES)})",
            name="ck_system_event_type",
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=gen_uuid)
    # Nullable because some events fire before/after a teacher row exists
    # (e.g. very-first oauth_login pre-INSERT, schema_migrated)
    teacher_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("teacher.id"), nullable=True, index=True
    )

    event_type: Mapped[str] = mapped_column(String, nullable=False, index=True)
    severity: Mapped[str] = mapped_column(String, nullable=False, default="info")
    payload_json: Mapped[str | None] = mapped_column(Text, nullable=True)

    created_at: Mapped[str] = mapped_column(
        String, default=utcnow_iso, nullable=False, index=True
    )

"""Teacher account (PRD §4.2). D1: single-row schema for V1; structure preserved for V2."""

from __future__ import annotations

from sqlalchemy import LargeBinary, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.session import Base
from app.models._helpers import gen_uuid, utcnow_iso


class Teacher(Base):
    __tablename__ = "teacher"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=gen_uuid)
    google_sub: Mapped[str] = mapped_column(String, unique=True, nullable=False)
    email: Mapped[str] = mapped_column(String, nullable=False)

    drive_root_folder_id: Mapped[str | None] = mapped_column(String, nullable=True)
    oauth_refresh_token_encrypted: Mapped[bytes | None] = mapped_column(
        LargeBinary, nullable=True
    )

    # JSON blobs stored as TEXT — V1 doesn't need JSON1 querying
    folder_mapping: Mapped[str | None] = mapped_column(Text, nullable=True)
    llm_tier_config: Mapped[str | None] = mapped_column(Text, nullable=True)

    # D17 — onboarding attestation
    consent_attestation_at: Mapped[str | None] = mapped_column(String, nullable=True)
    consent_attestation_version: Mapped[str | None] = mapped_column(String, nullable=True)

    created_at: Mapped[str] = mapped_column(String, default=utcnow_iso, nullable=False)
    last_active_at: Mapped[str | None] = mapped_column(String, nullable=True)

"""initial schema — all 8 tables per PRD §4.2 + system_event (D-2026-05-10-05)

Revision ID: 20260510_0001
Revises:
Create Date: 2026-05-10
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260510_0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "teacher",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("google_sub", sa.String, nullable=False, unique=True),
        sa.Column("email", sa.String, nullable=False),
        sa.Column("drive_root_folder_id", sa.String),
        sa.Column("oauth_refresh_token_encrypted", sa.LargeBinary),
        sa.Column("folder_mapping", sa.Text),
        sa.Column("llm_tier_config", sa.Text),
        sa.Column("consent_attestation_at", sa.String),
        sa.Column("consent_attestation_version", sa.String),
        sa.Column("created_at", sa.String, nullable=False),
        sa.Column("last_active_at", sa.String),
    )

    op.create_table(
        "drive_file",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "teacher_id",
            sa.String(36),
            sa.ForeignKey("teacher.id"),
            nullable=False,
        ),
        sa.Column("drive_file_id", sa.String, nullable=False),
        sa.Column("semester_label", sa.String, nullable=False),
        sa.Column("student_pseudo_id", sa.String, nullable=False),
        sa.Column("category", sa.String, nullable=False),
        sa.Column("drive_path", sa.String, nullable=False),
        sa.Column("filename", sa.String, nullable=False),
        sa.Column("mime_type", sa.String, nullable=False),
        sa.Column("size_bytes", sa.Integer),
        sa.Column("drive_modified_at", sa.String, nullable=False),
        sa.Column("content_hash", sa.String),
        sa.Column("indexed_at", sa.String, nullable=False),
        sa.Column("deleted_at", sa.String),
        sa.UniqueConstraint(
            "teacher_id", "drive_file_id", name="uq_drive_file_teacher_drive"
        ),
        sa.CheckConstraint(
            "category IN ('learning', 'interaction', 'work')",
            name="ck_drive_file_category",
        ),
    )
    op.create_index("ix_drive_file_teacher_id", "drive_file", ["teacher_id"])
    op.create_index("ix_drive_file_semester", "drive_file", ["semester_label"])
    op.create_index("ix_drive_file_student", "drive_file", ["student_pseudo_id"])

    op.create_table(
        "processed_artifact",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "drive_file_id",
            sa.String(36),
            sa.ForeignKey("drive_file.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("artifact_type", sa.String, nullable=False),
        sa.Column("state", sa.String, nullable=False),
        sa.Column("content_markdown", sa.Text),
        sa.Column("source_content_hash", sa.String),
        sa.Column("llm_tier", sa.String),
        sa.Column("llm_model", sa.String),
        sa.Column("llm_cost_usd", sa.Float),
        sa.Column("processed_at", sa.String),
        sa.Column("teacher_edited_at", sa.String),
        sa.Column("failure_reason", sa.Text),
        sa.Column("retry_count", sa.Integer, nullable=False, server_default="0"),
        sa.UniqueConstraint("drive_file_id", "artifact_type", name="uq_artifact_file_type"),
        sa.CheckConstraint(
            "state IN ('pending', 'processing', 'processed', 'teacher_edited', "
            "'reprocess_pending', 'failed', 'unprocessable')",
            name="ck_artifact_state",
        ),
        sa.CheckConstraint(
            "artifact_type IN ('markdown_summary', 'transcript')",
            name="ck_artifact_type",
        ),
    )
    op.create_index("ix_artifact_drive_file_id", "processed_artifact", ["drive_file_id"])
    op.create_index("ix_artifact_state", "processed_artifact", ["state"])

    op.create_table(
        "pii_mapping",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "teacher_id",
            sa.String(36),
            sa.ForeignKey("teacher.id"),
            nullable=False,
        ),
        sa.Column("pii_type", sa.String, nullable=False),
        sa.Column("original_value_encrypted", sa.LargeBinary, nullable=False),
        sa.Column("pseudonym", sa.String, nullable=False),
        sa.Column("display_name", sa.String),
        sa.Column("scope", sa.String, nullable=False, server_default="global"),
        sa.Column("source", sa.String, nullable=False, server_default="auto"),
        sa.Column("created_at", sa.String, nullable=False),
        sa.UniqueConstraint("teacher_id", "pseudonym", name="uq_pii_pseudonym"),
        sa.UniqueConstraint(
            "teacher_id",
            "pii_type",
            "original_value_encrypted",
            name="uq_pii_value",
        ),
        sa.CheckConstraint(
            "pii_type IN ('student_name', 'student_id', 'parent_name', 'phone', "
            "'address', 'email', 'other_name', 'other')",
            name="ck_pii_type",
        ),
        sa.CheckConstraint("source IN ('auto', 'manual')", name="ck_pii_source"),
    )
    op.create_index("ix_pii_teacher_id", "pii_mapping", ["teacher_id"])
    op.create_index("ix_pii_pseudonym", "pii_mapping", ["pseudonym"])

    op.create_table(
        "semester_evaluation",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "teacher_id",
            sa.String(36),
            sa.ForeignKey("teacher.id"),
            nullable=False,
        ),
        sa.Column("semester_label", sa.String, nullable=False),
        sa.Column("student_pseudo_id", sa.String, nullable=False),
        sa.Column("seed_text", sa.Text, nullable=False),
        sa.Column("style", sa.String, nullable=False),
        sa.Column("generated_text", sa.Text, nullable=False),
        sa.Column("edited_text", sa.Text),
        sa.Column("llm_model", sa.String),
        sa.Column("llm_cost_usd", sa.Float),
        sa.Column("generated_at", sa.String, nullable=False),
        sa.Column("edited_at", sa.String),
        sa.UniqueConstraint(
            "teacher_id",
            "semester_label",
            "student_pseudo_id",
            name="uq_eval_teacher_semester_student",
        ),
        sa.CheckConstraint(
            "style IN ('formal', 'encouraging', 'objective')",
            name="ck_eval_style",
        ),
    )
    op.create_index("ix_eval_teacher_id", "semester_evaluation", ["teacher_id"])

    op.create_table(
        "batch_job",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "teacher_id",
            sa.String(36),
            sa.ForeignKey("teacher.id"),
            nullable=False,
        ),
        sa.Column("semester_label", sa.String, nullable=False),
        sa.Column("status", sa.String, nullable=False),
        sa.Column("total", sa.Integer, nullable=False, server_default="0"),
        sa.Column("completed", sa.Integer, nullable=False, server_default="0"),
        sa.Column("failed", sa.Integer, nullable=False, server_default="0"),
        sa.Column("total_cost_usd", sa.Float),
        sa.Column("decisions_json", sa.Text),
        sa.Column("error_summary", sa.Text),
        sa.Column("started_at", sa.String, nullable=False),
        sa.Column("finished_at", sa.String),
        sa.CheckConstraint(
            "status IN ('pending', 'running', 'completed', 'failed', 'cancelled')",
            name="ck_batch_status",
        ),
    )
    op.create_index("ix_batch_teacher_id", "batch_job", ["teacher_id"])

    op.create_table(
        "llm_call_audit",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "teacher_id",
            sa.String(36),
            sa.ForeignKey("teacher.id"),
            nullable=False,
        ),
        sa.Column("tier", sa.String, nullable=False),
        sa.Column("model_id", sa.String, nullable=False),
        sa.Column("purpose", sa.String, nullable=False),
        sa.Column("input_tokens", sa.Integer),
        sa.Column("output_tokens", sa.Integer),
        sa.Column("cost_usd", sa.Float),
        sa.Column("pii_replacement_count", sa.Integer, nullable=False, server_default="0"),
        sa.Column("duration_ms", sa.Integer),
        sa.Column("error_message", sa.Text),
        sa.Column("created_at", sa.String, nullable=False),
    )
    op.create_index("ix_llm_audit_teacher_created", "llm_call_audit", ["teacher_id", "created_at"])

    op.create_table(
        "system_event",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "teacher_id",
            sa.String(36),
            sa.ForeignKey("teacher.id"),
            nullable=True,
        ),
        sa.Column("event_type", sa.String, nullable=False),
        sa.Column("severity", sa.String, nullable=False, server_default="info"),
        sa.Column("payload_json", sa.Text),
        sa.Column("created_at", sa.String, nullable=False),
        sa.CheckConstraint(
            "event_type IN ('oauth_login', 'oauth_logout', 'oauth_revoked', "
            "'attestation_signed', 'attestation_invalidated', 'key_rotated', "
            "'schema_migrated', 'batch_started', 'batch_completed', 'batch_failed', "
            "'pii_leakage_detected')",
            name="ck_system_event_type",
        ),
    )
    op.create_index(
        "ix_system_event_teacher_created", "system_event", ["teacher_id", "created_at"]
    )
    op.create_index("ix_system_event_type", "system_event", ["event_type"])


def downgrade() -> None:
    # Drop in reverse FK order
    op.drop_table("system_event")
    op.drop_table("llm_call_audit")
    op.drop_table("batch_job")
    op.drop_table("semester_evaluation")
    op.drop_table("pii_mapping")
    op.drop_table("processed_artifact")
    op.drop_table("drive_file")
    op.drop_table("teacher")

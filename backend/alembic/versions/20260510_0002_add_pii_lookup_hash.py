"""add pii_mapping.lookup_hash for O(1) plaintext lookup under random-nonce AES-GCM

Revision ID: 20260510_0002
Revises: 20260510_0001
Create Date: 2026-05-10

Why this migration exists:
- Initial schema (D-2026-05-10-06) had `UNIQUE (teacher_id, pii_type, original_value_encrypted)`
- That constraint is dead: random-nonce AES-GCM produces a different ciphertext each
  time the same plaintext is encrypted, so the unique check never fires and we can't
  look up "have we seen this plaintext before?" by ciphertext comparison.
- Solution: add `lookup_hash` (HMAC-SHA-256 of plaintext, keyed with PII_ENCRYPTION_KEY).
  Hash is deterministic → enables O(1) lookup + correct uniqueness enforcement.
  Encryption stays random-nonce → at-rest pattern leakage risk unchanged from
  ARCH-001 §8.3 baseline.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "20260510_0002"
down_revision: str | None = "20260510_0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # SQLite needs batch mode for ALTER. Drop old constraint, add column, add new constraint.
    with op.batch_alter_table("pii_mapping", recreate="always") as batch:
        batch.add_column(
            sa.Column("lookup_hash", sa.String(64), nullable=False, server_default="")
        )
        batch.drop_constraint("uq_pii_value", type_="unique")
        batch.create_unique_constraint(
            "uq_pii_lookup", ["teacher_id", "pii_type", "lookup_hash"]
        )

    op.create_index("ix_pii_lookup_hash", "pii_mapping", ["teacher_id", "lookup_hash"])


def downgrade() -> None:
    op.drop_index("ix_pii_lookup_hash", table_name="pii_mapping")
    with op.batch_alter_table("pii_mapping", recreate="always") as batch:
        batch.drop_constraint("uq_pii_lookup", type_="unique")
        batch.create_unique_constraint(
            "uq_pii_value",
            ["teacher_id", "pii_type", "original_value_encrypted"],
        )
        batch.drop_column("lookup_hash")

"""drop UNIQUE (teacher_id, pseudonym) so manual aliases can share a pseudonym

Revision ID: 20260510_0003
Revises: 20260510_0002
Create Date: 2026-05-10

Why this migration exists:
- D13 PII Min UI allows teachers to add manual aliases — same person, multiple
  spellings — that all map to the same pseudonym (e.g., "王小明" → S001 and
  "阿明" → S001 as a manual alias).
- The original schema had `UNIQUE (teacher_id, pseudonym)` which forbids two
  rows sharing a pseudonym; that contradicts the alias requirement.
- The `(teacher_id, pii_type, lookup_hash)` UNIQUE (added in 0002) still
  prevents duplicate plaintexts → the alias path is safe without
  `uq_pii_pseudonym`.

Effect on `restore()`: any row with the pseudonym can supply display_name /
original_value — they all refer to the same canonical entity by definition.
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "20260510_0003"
down_revision: str | None = "20260510_0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("pii_mapping", recreate="always") as batch:
        batch.drop_constraint("uq_pii_pseudonym", type_="unique")


def downgrade() -> None:
    with op.batch_alter_table("pii_mapping", recreate="always") as batch:
        batch.create_unique_constraint(
            "uq_pii_pseudonym", ["teacher_id", "pseudonym"]
        )

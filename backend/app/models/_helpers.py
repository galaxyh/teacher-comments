"""Shared model helpers — UUID/timestamp defaults.

Per ARCH-001 §4.2 conventions: UUID stored as TEXT(36); timestamps as ISO8601 TEXT.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime


def gen_uuid() -> str:
    """UUID4 as 36-char hex with hyphens, used as PK default."""
    return str(uuid.uuid4())


def utcnow_iso() -> str:
    """Current UTC time as ISO8601 with explicit `Z` suffix.

    Matches PRD §4.2 schema convention; also avoids the `datetime.utcnow()`
    deprecation warning in 3.12.
    """
    return datetime.now(UTC).isoformat(timespec="seconds")

"""Auth-related DTOs."""

from __future__ import annotations

from pydantic import BaseModel


class MeResponse(BaseModel):
    """Returned by GET /me — what the frontend uses to render header / decide redirects."""

    teacher_id: str
    email: str
    has_drive_root: bool
    has_attested: bool

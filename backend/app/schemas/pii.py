"""PII Min UI DTOs (D13)."""

from __future__ import annotations

from pydantic import BaseModel, Field

from app.services.pii_anonymizer import PIIType


class PIIMappingRow(BaseModel):
    id: str
    pseudonym: str
    pii_type: str
    display_name: str | None
    original_value: str | None
    source: str
    created_at: str | None


class UpdateDisplayNameRequest(BaseModel):
    display_name: str | None = Field(default=None, max_length=200)
    """Empty string clears the override; treated as None."""


class AddManualMappingRequest(BaseModel):
    pseudonym: str = Field(..., min_length=1)
    """An existing pseudonym (e.g., S001) — alias is added under it."""

    original_value: str = Field(..., min_length=1, max_length=200)
    pii_type: PIIType

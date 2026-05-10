"""Settings DTOs."""

from __future__ import annotations

from pydantic import BaseModel, Field


class SettingsResponse(BaseModel):
    llm_tier_config: dict[str, str]
    monthly_cost_usd: float
    monthly_budget_usd: float


class UpdateTierConfigRequest(BaseModel):
    """Replace per-tier overrides. Empty string clears that tier's override."""

    overrides: dict[str, str] = Field(default_factory=dict)

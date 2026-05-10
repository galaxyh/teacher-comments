"""Settings service — per-teacher overrides for LLM tier model IDs (D8).

Per PRD §4.2 the `teacher.llm_tier_config` JSON column stores per-teacher
overrides: {tier_name: model_id}. When unset, the system falls back to
process-level Settings (D9 default = `google/gemini-2.5-flash-lite`).

Phase 12 walking-skeleton scope: read + replace the whole config blob. No
per-tier validation against an "allowed model" list — V2 may add a registry.

Budget cap (`teacher.budget_monthly_usd`?? deferred — for V1 the budget is
process-wide via Settings.budget_monthly_usd; per-teacher budget is V2 scope).
This service exposes a current-usage helper so the Settings UI can show
"this month: US$X.XX of US$5.00".
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import Settings
from app.db.session import get_sessionmaker
from app.db.write_queue import DBWriteQueue
from app.models import LLMCallAudit, Teacher

VALID_TIERS: frozenset[str] = frozenset({
    "summary_cheap", "vision_cheap", "audio_standard", "evaluation_quality"
})


@dataclass
class SettingsView:
    llm_tier_config: dict[str, str]
    """Effective tier→model map (teacher overrides ∪ process defaults)."""

    monthly_cost_usd: Decimal
    """Sum of llm_call_audit.cost_usd in the current calendar month."""

    monthly_budget_usd: Decimal
    """Process-wide cap from Settings.budget_monthly_usd."""


class SettingsService:
    def __init__(
        self,
        *,
        settings: Settings,
        db_write_queue: DBWriteQueue,
    ) -> None:
        self._settings = settings
        self._queue = db_write_queue

    async def get_view(self, *, teacher_id: str) -> SettingsView:
        async with get_sessionmaker()() as session:
            teacher = await session.get(Teacher, teacher_id)
            override: dict[str, str] = (
                json.loads(teacher.llm_tier_config) if teacher and teacher.llm_tier_config else {}
            )

            month_start = datetime.now(timezone.utc).replace(
                day=1, hour=0, minute=0, second=0, microsecond=0
            ).isoformat(timespec="seconds")
            cost_sum = (
                await session.execute(
                    select(func.coalesce(func.sum(LLMCallAudit.cost_usd), 0.0)).where(
                        LLMCallAudit.teacher_id == teacher_id,
                        LLMCallAudit.created_at >= month_start,
                    )
                )
            ).scalar_one()

        # Compose effective config — process default overlaid by teacher override
        effective = {
            "summary_cheap": override.get("summary_cheap", self._settings.llm_tier_summary_cheap),
            "vision_cheap": override.get("vision_cheap", self._settings.llm_tier_vision_cheap),
            "audio_standard": override.get("audio_standard", self._settings.llm_tier_audio_standard),
            "evaluation_quality": override.get(
                "evaluation_quality", self._settings.llm_tier_evaluation_quality
            ),
        }
        return SettingsView(
            llm_tier_config=effective,
            monthly_cost_usd=Decimal(str(cost_sum or 0)).quantize(Decimal("0.000001")),
            monthly_budget_usd=self._settings.budget_monthly_usd,
        )

    async def set_tier_overrides(
        self, *, teacher_id: str, overrides: dict[str, str]
    ) -> None:
        """Replace the teacher's LLM tier overrides with `overrides`.

        - Empty string for a tier means "remove override / use process default".
        - Unknown keys raise ValueError.
        """
        for k in overrides:
            if k not in VALID_TIERS:
                raise ValueError(f"Unknown tier {k!r}; valid: {sorted(VALID_TIERS)}")

        cleaned = {k: v for k, v in overrides.items() if v}

        async def update(session: AsyncSession) -> None:
            row = await session.get(Teacher, teacher_id)
            if row is None:
                raise ValueError(f"No teacher with id {teacher_id!r}")
            row.llm_tier_config = json.dumps(cleaned, ensure_ascii=False) if cleaned else None
        await self._queue.submit(update)

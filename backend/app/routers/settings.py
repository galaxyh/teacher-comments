"""Settings router (Phase 12) — view + update LLM tier overrides + budget gauge."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from app.config import Settings, get_settings
from app.db.write_queue import DBWriteQueue, get_write_queue
from app.models import Teacher
from app.routers.auth import get_current_teacher
from app.schemas.settings import SettingsResponse, UpdateTierConfigRequest
from app.services.settings_service import SettingsService

router = APIRouter(tags=["settings"])


def get_settings_service(
    settings: Settings = Depends(get_settings),
    queue: DBWriteQueue = Depends(get_write_queue),
) -> SettingsService:
    return SettingsService(settings=settings, db_write_queue=queue)


@router.get("/settings", response_model=SettingsResponse)
async def view(
    teacher: Teacher = Depends(get_current_teacher),
    svc: SettingsService = Depends(get_settings_service),
) -> SettingsResponse:
    v = await svc.get_view(teacher_id=teacher.id)
    return SettingsResponse(
        llm_tier_config=v.llm_tier_config,
        monthly_cost_usd=float(v.monthly_cost_usd),
        monthly_budget_usd=float(v.monthly_budget_usd),
    )


@router.put("/settings/llm-tier", status_code=200)
async def update_tier_config(
    body: UpdateTierConfigRequest,
    teacher: Teacher = Depends(get_current_teacher),
    svc: SettingsService = Depends(get_settings_service),
) -> dict[str, str]:
    try:
        await svc.set_tier_overrides(teacher_id=teacher.id, overrides=body.overrides)
    except ValueError as exc:
        raise HTTPException(
            status_code=400, detail={"reason": "invalid_tier", "message": str(exc)}
        ) from exc
    return {"status": "ok"}

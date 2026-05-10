"""PII Min UI router (D13) — list, rename display, add manual alias."""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException

from app.db.write_queue import DBWriteQueue, get_write_queue
from app.models import Teacher
from app.routers.auth import get_current_teacher
from app.schemas.pii import (
    AddManualMappingRequest,
    PIIMappingRow,
    UpdateDisplayNameRequest,
)
from app.services.pii_anonymizer import PIIAnonymizer

logger = logging.getLogger(__name__)
router = APIRouter(tags=["pii"])


def get_anonymizer(
    queue: DBWriteQueue = Depends(get_write_queue),
) -> PIIAnonymizer:
    return PIIAnonymizer(db_write_queue=queue)


@router.get("/pii/mappings", response_model=list[PIIMappingRow])
async def list_mappings(
    teacher: Teacher = Depends(get_current_teacher),
    anonymizer: PIIAnonymizer = Depends(get_anonymizer),
) -> list[PIIMappingRow]:
    rows = await anonymizer.list_mappings(teacher_id=teacher.id)
    return [PIIMappingRow(**r) for r in rows]


@router.put("/pii/mappings/{pseudonym}/display-name")
async def update_display_name(
    pseudonym: str,
    body: UpdateDisplayNameRequest,
    teacher: Teacher = Depends(get_current_teacher),
    anonymizer: PIIAnonymizer = Depends(get_anonymizer),
) -> dict[str, str]:
    name = body.display_name.strip() if body.display_name else None
    name = name or None  # treat empty string as clear
    try:
        await anonymizer.update_display_name(
            teacher_id=teacher.id, pseudonym=pseudonym, display_name=name
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=404, detail={"reason": "pseudonym_not_found", "message": str(exc)}
        ) from exc
    return {"status": "ok", "pseudonym": pseudonym}


@router.post("/pii/mappings", response_model=PIIMappingRow)
async def add_manual_mapping(
    body: AddManualMappingRequest,
    teacher: Teacher = Depends(get_current_teacher),
    anonymizer: PIIAnonymizer = Depends(get_anonymizer),
) -> PIIMappingRow:
    try:
        row = await anonymizer.add_manual_mapping(
            teacher_id=teacher.id,
            original_value=body.original_value,
            pseudonym=body.pseudonym,
            pii_type=body.pii_type,
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=400,
            detail={"reason": "invalid_pseudonym", "message": str(exc)},
        ) from exc
    return PIIMappingRow(**row)

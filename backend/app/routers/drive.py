"""Drive routes (Phase 4a) — list candidates, set root, scan, set folder mapping.

Per ARCH-001 §3.1 onboarding flow steps 17-32 / DESIGN-001 §4.4.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, status

from app.db.write_queue import DBWriteQueue, get_write_queue
from app.models import Teacher
from app.routers.auth import get_auth_service, get_current_teacher
from app.schemas.drive import (
    FolderMappingRequest,
    ScanResult,
    SetDriveRootRequest,
    TreeListResponse,
)
from app.services.auth_service import AuthService
from app.services.drive_sync_service import DriveSyncService

logger = logging.getLogger(__name__)
router = APIRouter(tags=["drive"])


def get_drive_sync_service(
    auth: AuthService = Depends(get_auth_service),
    queue: DBWriteQueue = Depends(get_write_queue),
) -> DriveSyncService:
    return DriveSyncService(auth=auth, db_write_queue=queue)


@router.get("/drive/list", response_model=TreeListResponse)
async def list_root_candidates(
    teacher: Teacher = Depends(get_current_teacher),
    sync: DriveSyncService = Depends(get_drive_sync_service),
) -> TreeListResponse:
    """Onboarding step: list folders at My Drive root for teacher to pick the teaching root."""
    items = await sync.list_root_candidates(teacher_id=teacher.id)
    return TreeListResponse(items=items)


@router.get("/drive/folder/{folder_id}/children", response_model=TreeListResponse)
async def list_children(
    folder_id: str,
    teacher: Teacher = Depends(get_current_teacher),
    sync: DriveSyncService = Depends(get_drive_sync_service),
) -> TreeListResponse:
    """Lazy load subfolders for the tree UI."""
    items = await sync.list_children(teacher_id=teacher.id, folder_id=folder_id)
    return TreeListResponse(items=items)


@router.post("/onboarding/drive-root", status_code=status.HTTP_200_OK)
async def set_drive_root(
    body: SetDriveRootRequest,
    teacher: Teacher = Depends(get_current_teacher),
    sync: DriveSyncService = Depends(get_drive_sync_service),
) -> dict[str, str]:
    await sync.set_drive_root(teacher_id=teacher.id, folder_id=body.folder_id)
    return {"status": "ok", "folder_id": body.folder_id}


@router.post("/drive/scan", response_model=ScanResult)
async def scan(
    teacher: Teacher = Depends(get_current_teacher),
    sync: DriveSyncService = Depends(get_drive_sync_service),
) -> ScanResult:
    """Walk 3-level Drive structure under teacher.drive_root_folder_id.

    Returns `needs_folder_mapping=True` with `unmapped_category_names` if a
    non-standard category folder name is encountered. Caller posts
    /onboarding/folder-mapping then calls this endpoint again.
    """
    return await sync.scan_root(teacher_id=teacher.id)


@router.post("/onboarding/folder-mapping", status_code=status.HTTP_200_OK)
async def set_folder_mapping(
    body: FolderMappingRequest,
    teacher: Teacher = Depends(get_current_teacher),
    sync: DriveSyncService = Depends(get_drive_sync_service),
) -> dict[str, str]:
    await sync.set_folder_mapping(teacher_id=teacher.id, mapping=body.mapping)
    return {"status": "ok", "mapping_count": str(len(body.mapping))}


# ── Attestation (D17) ──────────────────────────────────────────────


from pydantic import BaseModel, Field  # noqa: E402 — local class definition


class AttestRequest(BaseModel):
    version: str = Field(default="v1", min_length=1, max_length=8)
    """The attestation text version the teacher saw + agreed to."""


@router.post("/onboarding/attest", status_code=status.HTTP_200_OK)
async def attest(
    body: AttestRequest,
    teacher: Teacher = Depends(get_current_teacher),
    auth: AuthService = Depends(get_auth_service),
) -> dict[str, str]:
    """Record the teacher's parental-consent attestation (D17 / PRD §3.2 Flow A step 2).

    Idempotent — same teacher can sign multiple times (e.g., new version published).
    Each call records a fresh `attestation_signed` system_event for audit.
    """
    updated = await auth.attest(teacher_id=teacher.id, version=body.version)
    return {"status": "ok", "version": updated.consent_attestation_version or body.version}

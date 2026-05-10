"""Drive-related DTOs."""

from __future__ import annotations

from pydantic import BaseModel, Field

from app.services.drive_sync_service import DriveTreeNode, ScanResult


class TreeListResponse(BaseModel):
    items: list[DriveTreeNode]


class SetDriveRootRequest(BaseModel):
    folder_id: str = Field(..., min_length=1)


class FolderMappingRequest(BaseModel):
    """Mapping wizard payload (D14).

    Keys are actual folder names found in Drive (e.g., '課堂筆記').
    Values are canonical category enum values or '__skip__'.
    """

    mapping: dict[str, str] = Field(default_factory=dict)


__all__ = [
    "DriveTreeNode",
    "FolderMappingRequest",
    "ScanResult",
    "SetDriveRootRequest",
    "TreeListResponse",
]

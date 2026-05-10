"""DriveSyncService — Drive scan / index / mapping wizard logic.

Per DESIGN-001 §4.4 contract; Phase 4a scope:
- list_root_candidates — for onboarding pick-folder UI
- set_drive_root — persist teacher.drive_root_folder_id
- scan_root — walk 3 levels (semester / student / category) and INSERT/UPDATE drive_file rows
- set_folder_mapping — persist teacher.folder_mapping JSON

Phase 4b adds: download_file, content_hash, integration with ProcessingPipeline.

Walking-skeleton simplification: scan is single-shot rather than suspendable.
If a non-standard category folder is encountered AND no folder_mapping is set,
scan returns `needs_folder_mapping=True` with the candidate folder names —
caller posts mapping, then calls scan again. Two API round-trips total instead
of stateful suspend/resume; no observable UX difference for the teacher.

Standard category names (PRD §4.1):
    "學習紀錄" → "learning"
    "教師與學生互動紀錄" → "interaction"
    "作品成果" → "work"
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from typing import Final

from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.adapters.drive_client import DriveClient, DriveItem
from app.db.session import get_sessionmaker
from app.db.write_queue import DBWriteQueue
from app.models import DriveFile, Teacher
from app.models._helpers import gen_uuid, utcnow_iso
from app.services.auth_service import AuthService

logger = logging.getLogger(__name__)


STANDARD_CATEGORY_NAMES: Final[dict[str, str]] = {
    "學習紀錄": "learning",
    "教師與學生互動紀錄": "interaction",
    "作品成果": "work",
}
"""Maps Chinese folder name → schema enum value. Reverse lookup for mapping wizard."""

CATEGORY_ENUM_VALUES: Final[tuple[str, ...]] = ("learning", "interaction", "work")


# ── DTOs ──────────────────────────────────────────────────────────


class DriveTreeNode(BaseModel):
    drive_file_id: str
    name: str
    is_folder: bool


class ScanResult(BaseModel):
    semesters_found: int
    students_found: int
    files_indexed: int
    files_unchanged: int
    needs_folder_mapping: bool
    """If True, `unmapped_category_names` lists the non-standard names found."""

    unmapped_category_names: list[str] = []


# ── Service ────────────────────────────────────────────────────────


@dataclass
class _ScanState:
    """Mutable scan-time accumulator. Internal; never returned to callers."""

    semesters_found: int = 0
    students_found: int = 0
    files_indexed: int = 0
    files_unchanged: int = 0
    unmapped_names: set[str] = field(default_factory=set)


class DriveSyncService:
    def __init__(
        self,
        *,
        auth: AuthService,
        db_write_queue: DBWriteQueue,
        # `client_factory` allows tests to inject FakeDriveClient without going through
        # google.oauth2.credentials. Production code uses the default factory which
        # builds a real DriveClient from teacher credentials.
        client_factory: callable | None = None,  # type: ignore[valid-type]
    ) -> None:
        self._auth = auth
        self._queue = db_write_queue
        self._client_factory = client_factory or self._default_client_factory

    async def _default_client_factory(self, *, teacher_id: str) -> DriveClient:
        creds = await self._auth.get_credentials(teacher_id=teacher_id)
        return DriveClient(creds)

    # ── Onboarding helpers ───────────────────────────────────────

    async def list_root_candidates(self, *, teacher_id: str) -> list[DriveTreeNode]:
        """Folders at My Drive root — for the 'pick teaching root' UI."""
        client = await self._client_factory(teacher_id=teacher_id)
        items = await client.list_root_folders()
        return [_to_tree_node(i) for i in items]

    async def list_children(
        self, *, teacher_id: str, folder_id: str
    ) -> list[DriveTreeNode]:
        """Lazy-load subfolders for the tree UI."""
        client = await self._client_factory(teacher_id=teacher_id)
        items = await client.list_folders_in(folder_id)
        return [_to_tree_node(i) for i in items]

    async def set_drive_root(
        self, *, teacher_id: str, folder_id: str
    ) -> None:
        async def update(session: AsyncSession) -> None:
            row = await session.get(Teacher, teacher_id)
            if row is not None:
                row.drive_root_folder_id = folder_id
                row.last_active_at = utcnow_iso()

        await self._queue.submit(update)

    async def set_folder_mapping(
        self, *, teacher_id: str, mapping: dict[str, str]
    ) -> None:
        """Persist teacher.folder_mapping (D14).

        `mapping` keys are actual folder names found in Drive; values are the
        canonical category enum value ('learning' | 'interaction' | 'work' |
        '__skip__' to ignore).
        """
        for v in mapping.values():
            if v not in (*CATEGORY_ENUM_VALUES, "__skip__"):
                raise ValueError(
                    f"Invalid mapping target {v!r}; must be category enum or '__skip__'"
                )

        async def update(session: AsyncSession) -> None:
            row = await session.get(Teacher, teacher_id)
            if row is not None:
                row.folder_mapping = json.dumps(mapping, ensure_ascii=False)

        await self._queue.submit(update)

    # ── Scan ──────────────────────────────────────────────────────

    async def scan_root(self, *, teacher_id: str) -> ScanResult:
        """Walk 3 levels: semester → student → category → files.

        Pre-condition: teacher.drive_root_folder_id must be set. If folder_mapping
        is unset and non-standard category folders are found, returns immediately
        with `needs_folder_mapping=True`. Caller resolves mapping, then re-calls.
        """
        teacher = await self._auth.get_teacher(teacher_id=teacher_id)
        if teacher is None:
            raise ValueError(f"No teacher row for {teacher_id!r}")
        if not teacher.drive_root_folder_id:
            raise ValueError("Teacher.drive_root_folder_id not set; call set_drive_root first")

        mapping: dict[str, str] = (
            json.loads(teacher.folder_mapping) if teacher.folder_mapping else {}
        )
        client = await self._client_factory(teacher_id=teacher_id)

        # Level 1: semesters
        semesters = await client.list_folders_in(teacher.drive_root_folder_id)
        state = _ScanState(semesters_found=len(semesters))

        for semester in semesters:
            students = await client.list_folders_in(semester.drive_file_id)
            state.students_found += len(students)
            for student in students:
                # Level 3: category folders
                categories = await client.list_folders_in(student.drive_file_id)
                for cat_folder in categories:
                    category_value = self._resolve_category(
                        folder_name=cat_folder.name, mapping=mapping
                    )
                    if category_value is None:
                        state.unmapped_names.add(cat_folder.name)
                        continue  # don't recurse into unmapped folders
                    if category_value == "__skip__":
                        continue

                    # Level 4: files
                    files = await client.list_files_in(cat_folder.drive_file_id)
                    for f in files:
                        await self._upsert_drive_file(
                            teacher_id=teacher_id,
                            semester_label=semester.name,
                            student_pseudo_name=student.name,
                            category=category_value,
                            drive_path=(
                                f"{semester.name}/{student.name}/{cat_folder.name}/{f.name}"
                            ),
                            item=f,
                            state=state,
                        )

        if state.unmapped_names:
            return ScanResult(
                semesters_found=state.semesters_found,
                students_found=state.students_found,
                files_indexed=state.files_indexed,
                files_unchanged=state.files_unchanged,
                needs_folder_mapping=True,
                unmapped_category_names=sorted(state.unmapped_names),
            )

        return ScanResult(
            semesters_found=state.semesters_found,
            students_found=state.students_found,
            files_indexed=state.files_indexed,
            files_unchanged=state.files_unchanged,
            needs_folder_mapping=False,
        )

    # ── internals ─────────────────────────────────────────────────

    @staticmethod
    def _resolve_category(
        *, folder_name: str, mapping: dict[str, str]
    ) -> str | None:
        """Returns category enum value, '__skip__', or None (=needs mapping)."""
        if folder_name in STANDARD_CATEGORY_NAMES:
            return STANDARD_CATEGORY_NAMES[folder_name]
        if folder_name in mapping:
            return mapping[folder_name]
        return None

    async def _upsert_drive_file(
        self,
        *,
        teacher_id: str,
        semester_label: str,
        student_pseudo_name: str,
        category: str,
        drive_path: str,
        item: DriveItem,
        state: _ScanState,
    ) -> None:
        """Insert if new; update if drive_modified_at changed; else skip.

        Phase 4a: student_pseudo_id is the raw Drive folder name (e.g., '王小明').
        Phase 5 (PII anonymisation pass) replaces this with a deterministic
        pseudonym during pre-processing — at scan time we don't yet trust the
        pseudonym mapping is populated.
        """
        async with get_sessionmaker()() as session:
            existing = (
                await session.execute(
                    select(DriveFile).where(
                        DriveFile.teacher_id == teacher_id,
                        DriveFile.drive_file_id == item.drive_file_id,
                    )
                )
            ).scalar_one_or_none()

        if existing is not None:
            if existing.drive_modified_at == item.modified_time:
                state.files_unchanged += 1
                return

            async def update(session: AsyncSession) -> None:
                row = await session.get(DriveFile, existing.id)
                if row is not None:
                    row.drive_modified_at = item.modified_time
                    row.size_bytes = item.size_bytes
                    row.indexed_at = utcnow_iso()

            await self._queue.submit(update)
            state.files_indexed += 1
            return

        new_id = gen_uuid()
        new_row = DriveFile(
            id=new_id,
            teacher_id=teacher_id,
            drive_file_id=item.drive_file_id,
            semester_label=semester_label,
            student_pseudo_id=student_pseudo_name,
            category=category,
            drive_path=drive_path,
            filename=item.name,
            mime_type=item.mime_type,
            size_bytes=item.size_bytes,
            drive_modified_at=item.modified_time,
        )

        async def insert(session: AsyncSession) -> None:
            session.add(new_row)

        await self._queue.submit(insert)
        state.files_indexed += 1


def _to_tree_node(item: DriveItem) -> DriveTreeNode:
    return DriveTreeNode(
        drive_file_id=item.drive_file_id,
        name=item.name,
        is_folder=item.is_folder,
    )

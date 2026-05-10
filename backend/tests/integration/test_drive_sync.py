"""DriveSyncService integration tests with a FakeDriveClient.

The fake mirrors DriveClient's public surface — `list_root_folders`,
`list_folders_in`, `list_files_in` — and is constructed with a canned 3-level
folder tree. DriveSyncService doesn't care which client it gets.
"""

from __future__ import annotations

import subprocess
from dataclasses import dataclass, field

import pytest

from app.adapters.drive_client import DriveItem


@dataclass
class _FakeNode:
    """In-memory Drive folder/file tree for tests."""
    name: str
    is_folder: bool
    drive_file_id: str
    mime_type: str = "application/vnd.google-apps.folder"
    size_bytes: int | None = None
    modified_time: str = "2026-05-01T00:00:00Z"
    children: list[_FakeNode] = field(default_factory=list)


def _to_drive_item(node: _FakeNode) -> DriveItem:
    return DriveItem(
        drive_file_id=node.drive_file_id,
        name=node.name,
        mime_type=(
            "application/vnd.google-apps.folder" if node.is_folder else node.mime_type
        ),
        is_folder=node.is_folder,
        size_bytes=node.size_bytes,
        modified_time=node.modified_time,
    )


class FakeDriveClient:
    def __init__(
        self,
        root_children: list[_FakeNode],
        *,
        teaching_root_id: str = "ROOT",
    ) -> None:
        # Map drive_file_id → list of children
        self._index: dict[str, list[_FakeNode]] = {}
        self._root = root_children
        # The teaching-root folder (`drive_root_folder_id` on the teacher row) is
        # treated as containing the top-level entries — needed because scan_root
        # calls `list_folders_in(teacher.drive_root_folder_id)` first.
        self._index[teaching_root_id] = root_children
        self._build_index(root_children)

    def _build_index(self, nodes: list[_FakeNode]) -> None:
        for n in nodes:
            self._index[n.drive_file_id] = n.children
            if n.children:
                self._build_index(n.children)

    async def list_root_folders(self, *, page_size: int = 100) -> list[DriveItem]:
        return [_to_drive_item(n) for n in self._root if n.is_folder]

    async def list_folders_in(
        self, parent_id: str, *, page_size: int = 100
    ) -> list[DriveItem]:
        children = self._index.get(parent_id, [])
        return [_to_drive_item(n) for n in children if n.is_folder]

    async def list_files_in(
        self, parent_id: str, *, page_size: int = 200
    ) -> list[DriveItem]:
        children = self._index.get(parent_id, [])
        return [_to_drive_item(n) for n in children if not n.is_folder]


# ── Fixture ────────────────────────────────────────────────────────


@pytest.fixture
async def harness(isolated_env, write_queue):
    """Build a DriveSyncService backed by a real DB + a swappable FakeDriveClient."""
    subprocess.run(
        ["uv", "run", "alembic", "upgrade", "head"],
        check=True,
        cwd="/home/steven/projects/teacher-comments/backend",
        capture_output=True,
    )

    from app.config import get_settings
    from app.models import Teacher
    from app.services.audit_logger import AuditLogger
    from app.services.auth_service import AuthService
    from app.services.drive_sync_service import DriveSyncService

    # Seed teacher with drive_root_folder_id
    async def insert_teacher(session) -> str:
        t = Teacher(
            id="t1",
            google_sub="sub",
            email="t@e.com",
            drive_root_folder_id="ROOT",
        )
        session.add(t)
        return "t1"
    await write_queue.submit(insert_teacher)

    audit = AuditLogger(write_queue)
    auth = AuthService(
        settings=get_settings(),
        db_write_queue=write_queue,
        audit=audit,
    )

    # Holder so tests can reconfigure fake without re-fixturing
    fake_client_holder: dict[str, FakeDriveClient] = {}

    async def factory(*, teacher_id: str) -> FakeDriveClient:
        return fake_client_holder["client"]

    sync = DriveSyncService(
        auth=auth, db_write_queue=write_queue, client_factory=factory  # type: ignore[arg-type]
    )

    return sync, fake_client_holder


# Convenience builder for tree fixtures
def _file(name: str, fid: str, *, mime: str = "application/octet-stream") -> _FakeNode:
    return _FakeNode(name=name, is_folder=False, drive_file_id=fid, mime_type=mime)


def _folder(name: str, fid: str, children: list[_FakeNode] | None = None) -> _FakeNode:
    return _FakeNode(name=name, is_folder=True, drive_file_id=fid, children=children or [])


# ── Tests ──────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_scan_indexes_files_under_standard_categories(harness) -> None:
    sync, holder = harness
    holder["client"] = FakeDriveClient([
        _folder("113-1 上學期", "sem1", [
            _folder("王小明", "stu1", [
                _folder("學習紀錄", "cat1-learn", [
                    _file("週記1.docx", "f1"),
                    _file("週記2.docx", "f2"),
                ]),
                _folder("作品成果", "cat1-work", [
                    _file("作品.pdf", "f3"),
                ]),
            ]),
        ]),
    ])

    result = await sync.scan_root(teacher_id="t1")

    assert result.needs_folder_mapping is False
    assert result.semesters_found == 1
    assert result.students_found == 1
    assert result.files_indexed == 3

    # Verify rows landed in DB with correct category mapping
    from sqlalchemy import select

    from app.db.session import get_sessionmaker
    from app.models import DriveFile

    async with get_sessionmaker()() as session:
        rows = (await session.execute(select(DriveFile))).scalars().all()

    assert {r.filename for r in rows} == {"週記1.docx", "週記2.docx", "作品.pdf"}
    assert {r.category for r in rows} == {"learning", "work"}
    assert {r.semester_label for r in rows} == {"113-1 上學期"}
    assert {r.student_pseudo_id for r in rows} == {"王小明"}


@pytest.mark.asyncio
async def test_scan_returns_needs_mapping_for_nonstandard_folders(harness) -> None:
    sync, holder = harness
    holder["client"] = FakeDriveClient([
        _folder("113-1 上學期", "sem1", [
            _folder("王小明", "stu1", [
                _folder("課堂筆記", "cat1-notes", [_file("note.docx", "f1")]),  # nonstandard
                _folder("學習紀錄", "cat1-learn", [_file("std.docx", "f2")]),  # standard
            ]),
        ]),
    ])

    result = await sync.scan_root(teacher_id="t1")

    assert result.needs_folder_mapping is True
    assert "課堂筆記" in result.unmapped_category_names
    # The standard folder still indexed despite the unmapped one
    from sqlalchemy import select

    from app.db.session import get_sessionmaker
    from app.models import DriveFile

    async with get_sessionmaker()() as session:
        rows = (await session.execute(select(DriveFile))).scalars().all()
    assert {r.filename for r in rows} == {"std.docx"}


@pytest.mark.asyncio
async def test_scan_uses_persisted_folder_mapping(harness) -> None:
    """After set_folder_mapping persists, re-scan picks up mapped folders."""
    sync, holder = harness
    holder["client"] = FakeDriveClient([
        _folder("113-1", "sem1", [
            _folder("王小明", "stu1", [
                _folder("課堂筆記", "cat-notes", [_file("note.docx", "f1")]),
                _folder("晤談紀錄", "cat-talk", [_file("talk.docx", "f2")]),
                _folder("雜項", "cat-misc", [_file("misc.docx", "f3")]),
            ]),
        ]),
    ])

    # First scan → needs mapping
    r1 = await sync.scan_root(teacher_id="t1")
    assert r1.needs_folder_mapping is True
    assert set(r1.unmapped_category_names) == {"課堂筆記", "晤談紀錄", "雜項"}

    # Set mapping: notes → learning, talk → interaction, misc → skip
    await sync.set_folder_mapping(
        teacher_id="t1",
        mapping={
            "課堂筆記": "learning",
            "晤談紀錄": "interaction",
            "雜項": "__skip__",
        },
    )

    # Second scan picks up the mapping
    r2 = await sync.scan_root(teacher_id="t1")
    assert r2.needs_folder_mapping is False
    assert r2.files_indexed == 2  # note + talk; misc skipped

    from sqlalchemy import select

    from app.db.session import get_sessionmaker
    from app.models import DriveFile

    async with get_sessionmaker()() as session:
        rows = (await session.execute(select(DriveFile))).scalars().all()
    assert {r.category for r in rows} == {"learning", "interaction"}


@pytest.mark.asyncio
async def test_scan_idempotent_on_unchanged_files(harness) -> None:
    """Re-running scan on identical Drive state should not re-index unchanged files."""
    sync, holder = harness
    holder["client"] = FakeDriveClient([
        _folder("113-1", "sem1", [
            _folder("王小明", "stu1", [
                _folder("學習紀錄", "cat", [_file("a.docx", "f1")]),
            ]),
        ]),
    ])

    r1 = await sync.scan_root(teacher_id="t1")
    assert r1.files_indexed == 1
    assert r1.files_unchanged == 0

    r2 = await sync.scan_root(teacher_id="t1")
    assert r2.files_indexed == 0
    assert r2.files_unchanged == 1


@pytest.mark.asyncio
async def test_scan_updates_modified_file(harness) -> None:
    """If drive_modified_at changes, re-scan UPDATEs (counts as 'indexed')."""
    sync, holder = harness
    initial = FakeDriveClient([
        _folder("113-1", "sem1", [
            _folder("王小明", "stu1", [
                _folder("學習紀錄", "cat", [_file("a.docx", "f1")]),
            ]),
        ]),
    ])
    holder["client"] = initial

    await sync.scan_root(teacher_id="t1")

    # Change the modified_time on the file
    initial._index["cat"][0].modified_time = "2026-06-01T00:00:00Z"

    r2 = await sync.scan_root(teacher_id="t1")
    assert r2.files_indexed == 1   # updated
    assert r2.files_unchanged == 0


@pytest.mark.asyncio
async def test_set_folder_mapping_rejects_invalid_target(harness) -> None:
    sync, _ = harness
    with pytest.raises(ValueError, match="Invalid mapping target"):
        await sync.set_folder_mapping(
            teacher_id="t1", mapping={"foo": "bogus_category"}
        )


@pytest.mark.asyncio
async def test_list_root_candidates(harness) -> None:
    sync, holder = harness
    holder["client"] = FakeDriveClient([
        _folder("教學資料", "f1"),
        _folder("私人檔案", "f2"),
    ])

    items = await sync.list_root_candidates(teacher_id="t1")
    assert {(i.name, i.is_folder) for i in items} == {("教學資料", True), ("私人檔案", True)}

"""BatchWorker + SSE integration tests.

Verifies:
- start_job creates batch_job, marks artifacts processed/failed/unprocessable
  by exception class
- get_status snapshots counters
- recover_stale_jobs resets 'processing' → 'pending'
- SSE pub/sub broadcasts events to subscribers and includes terminal state
- /batch/* routes work via TestClient
"""

from __future__ import annotations

import asyncio
import json
import subprocess
from dataclasses import dataclass
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient

from app.core.exceptions import LLMRateLimitError, UnsupportedFormatError
from app.services.processing_pipeline import ProcessingResult


@dataclass
class _PipelineCall:
    teacher_id: str
    drive_file_id: str


class FakePipeline:
    """Stub returning canned ProcessingResult or raising configurable exceptions."""

    def __init__(self) -> None:
        self.calls: list[_PipelineCall] = []
        # drive_file_id → behavior: "ok" | "unsupported" | "rate_limit"
        self.behavior: dict[str, str] = {}

    async def process(self, *, teacher_id: str, drive_file) -> ProcessingResult:
        self.calls.append(_PipelineCall(teacher_id=teacher_id, drive_file_id=drive_file.id))
        beh = self.behavior.get(drive_file.id, "ok")
        if beh == "unsupported":
            raise UnsupportedFormatError("test: unsupported", context={})
        if beh == "rate_limit":
            raise LLMRateLimitError("test: 429", context={})
        from app.services.llm_service import TaskTier
        return ProcessingResult(
            artifact_type="markdown_summary",
            content_markdown=f"summary for {drive_file.filename}",
            raw_anonymized_markdown="raw",
            llm_tier=TaskTier.SUMMARY_CHEAP,
            llm_model="google/gemini-2.5-flash-lite",
            llm_cost_usd=Decimal("0.0001"),
            audit_id="audit-x",
            content_hash="a" * 64,
            warnings=[],
        )


@pytest.fixture
async def worker_harness(isolated_env, write_queue):
    """Real DB + fake pipeline + real SSE publisher."""
    subprocess.run(
        ["uv", "run", "alembic", "upgrade", "head"],
        check=True,
        cwd="/home/steven/projects/teacher-comments/backend",
        capture_output=True,
    )

    from app.config import get_settings
    from app.models import DriveFile, Teacher
    from app.services.audit_logger import AuditLogger
    from app.services.batch_worker import BatchWorker
    from app.services.sse_publisher import SSEPublisher

    # Seed teacher
    async def insert_teacher(s):
        s.add(Teacher(id="t1", google_sub="sub", email="t@e.com"))
    await write_queue.submit(insert_teacher)

    # Seed 3 drive_files in the same semester — second one will fail
    async def insert_files(s):
        s.add_all([
            DriveFile(
                id=f"df{i}", teacher_id="t1", drive_file_id=f"d{i}",
                semester_label="113-1", student_pseudo_id="王小明",
                category="learning", drive_path="...",
                filename=f"file{i}.docx",
                mime_type=(
                    "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
                ),
                drive_modified_at="2026-05-01T00:00:00Z",
            )
            for i in range(1, 4)
        ])
    await write_queue.submit(insert_files)

    fake_pipeline = FakePipeline()
    sse = SSEPublisher()
    audit = AuditLogger(write_queue)
    worker = BatchWorker(
        settings=get_settings(),
        pipeline=fake_pipeline,  # type: ignore[arg-type]
        db_write_queue=write_queue,
        sse=sse,
        audit=audit,
    )
    return worker, fake_pipeline, sse


@pytest.mark.asyncio
async def test_start_job_processes_all_files(worker_harness) -> None:
    worker, fake, _ = worker_harness

    batch_id = await worker.start_job(teacher_id="t1", semester_label="113-1")
    # Wait for background task to complete
    await asyncio.sleep(0)
    while True:
        snapshot = await worker.get_status(batch_job_id=batch_id)
        if snapshot.status in ("completed", "failed", "cancelled"):
            break
        await asyncio.sleep(0.05)

    assert snapshot.status == "completed"
    assert snapshot.total == 3
    assert snapshot.completed == 3
    assert snapshot.failed == 0
    assert len(fake.calls) == 3


@pytest.mark.asyncio
async def test_terminal_failure_marks_unprocessable(worker_harness) -> None:
    worker, fake, _ = worker_harness
    fake.behavior["df2"] = "unsupported"

    batch_id = await worker.start_job(teacher_id="t1", semester_label="113-1")
    while True:
        snapshot = await worker.get_status(batch_job_id=batch_id)
        if snapshot.status in ("completed", "failed", "cancelled"):
            break
        await asyncio.sleep(0.05)

    assert snapshot.completed == 2
    assert snapshot.failed == 1

    # Verify artifact state
    from app.db.session import get_sessionmaker
    from app.models import DriveFile, ProcessedArtifact
    from sqlalchemy import select

    async with get_sessionmaker()() as s:
        rows = (
            await s.execute(
                select(ProcessedArtifact, DriveFile)
                .join(DriveFile, DriveFile.id == ProcessedArtifact.drive_file_id)
            )
        ).all()
    states_by_file = {df.id: art.state for art, df in rows}
    assert states_by_file["df1"] == "processed"
    assert states_by_file["df2"] == "unprocessable"
    assert states_by_file["df3"] == "processed"


@pytest.mark.asyncio
async def test_rate_limit_marks_failed_not_unprocessable(worker_harness) -> None:
    worker, fake, _ = worker_harness
    fake.behavior["df1"] = "rate_limit"

    batch_id = await worker.start_job(teacher_id="t1", semester_label="113-1")
    while True:
        snapshot = await worker.get_status(batch_job_id=batch_id)
        if snapshot.status in ("completed", "failed", "cancelled"):
            break
        await asyncio.sleep(0.05)

    from app.db.session import get_sessionmaker
    from app.models import ProcessedArtifact
    from sqlalchemy import select
    async with get_sessionmaker()() as s:
        artifacts = (
            await s.execute(
                select(ProcessedArtifact).where(
                    ProcessedArtifact.drive_file_id == "df1"
                )
            )
        ).scalars().all()
    assert len(artifacts) == 1
    assert artifacts[0].state == "failed"
    assert artifacts[0].retry_count == 1


@pytest.mark.asyncio
async def test_recover_stale_jobs(worker_harness) -> None:
    worker, _, _ = worker_harness
    from app.models import ProcessedArtifact
    from app.models._helpers import gen_uuid

    # Seed an artifact stuck in 'processing'
    async def stuck(s):
        s.add(
            ProcessedArtifact(
                id=gen_uuid(),
                drive_file_id="df1",
                artifact_type="markdown_summary",
                state="processing",
            )
        )
    from app.db.write_queue import get_write_queue
    queue = get_write_queue()
    # Use the harness's queue (start was via fixture)
    # Reuse worker's queue by accessing private member is OK in tests
    await worker._queue.submit(stuck)

    recovered = await worker.recover_stale_jobs()
    assert recovered == 1


@pytest.mark.asyncio
async def test_sse_publisher_broadcasts_events(worker_harness) -> None:
    """Subscriber attached BEFORE publish receives the event."""
    _, _, sse = worker_harness

    received: list[dict] = []

    async def consumer():
        async for ev in sse.subscribe("test-topic"):
            received.append(ev)
            if ev.get("done"):
                break

    consumer_task = asyncio.create_task(consumer())
    # Yield to let subscribe() register
    await asyncio.sleep(0.01)
    await sse.publish("test-topic", {"step": 1})
    await sse.publish("test-topic", {"step": 2, "done": True})
    await asyncio.wait_for(consumer_task, timeout=2.0)

    assert received == [{"step": 1}, {"step": 2, "done": True}]


@pytest.mark.asyncio
async def test_get_status_returns_none_for_unknown(worker_harness) -> None:
    worker, _, _ = worker_harness
    snapshot = await worker.get_status(batch_job_id="nonexistent")
    assert snapshot is None


# ── Router-level via TestClient ────────────────────────────────


@pytest.fixture
def authed_client(isolated_env):
    """TestClient with a session cookie + BatchWorker override using FakePipeline."""
    subprocess.run(
        ["uv", "run", "alembic", "upgrade", "head"],
        check=True,
        cwd="/home/steven/projects/teacher-comments/backend",
        capture_output=True,
    )

    from app.config import get_settings
    from app.core.session import COOKIE_NAME, issue_session_cookie
    from app.db.write_queue import get_write_queue
    from app.main import create_app
    from app.models import DriveFile, Teacher
    from app.routers.batch import get_batch_worker
    from app.services.audit_logger import AuditLogger
    from app.services.batch_worker import BatchWorker
    from app.services.sse_publisher import get_sse_publisher

    fake_pipeline = FakePipeline()
    app = create_app()

    def _override_worker() -> BatchWorker:
        queue = get_write_queue()
        return BatchWorker(
            settings=get_settings(),
            pipeline=fake_pipeline,  # type: ignore[arg-type]
            db_write_queue=queue,
            sse=get_sse_publisher(),
            audit=AuditLogger(queue),
        )

    app.dependency_overrides[get_batch_worker] = _override_worker

    with TestClient(app) as client:
        queue = get_write_queue()

        async def seed_teacher(s):
            s.add(Teacher(id="t1", google_sub="sub", email="t@e.com"))
        client.portal.call(queue.submit, seed_teacher)

        async def seed_files(s):
            s.add_all([
                DriveFile(
                    id=f"df{i}", teacher_id="t1", drive_file_id=f"d{i}",
                    semester_label="113-1", student_pseudo_id="王小明",
                    category="learning", drive_path="...",
                    filename=f"f{i}.docx",
                    mime_type=(
                        "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
                    ),
                    drive_modified_at="2026-05-01T00:00:00Z",
                )
                for i in range(1, 3)
            ])
        client.portal.call(queue.submit, seed_files)

        client.cookies.set(COOKIE_NAME, issue_session_cookie("t1"))
        yield client


def test_start_batch_returns_202(authed_client: TestClient) -> None:
    r = authed_client.post("/batch/start", json={"semester_label": "113-1"})
    assert r.status_code == 202
    body = r.json()
    assert body["total"] == 2
    assert body["status"] == "running"


def test_status_after_start_returns_completed(authed_client: TestClient) -> None:
    s = authed_client.post("/batch/start", json={"semester_label": "113-1"})
    batch_id = s.json()["batch_job_id"]
    # Poll until completed
    import time
    for _ in range(50):
        r = authed_client.get(f"/batch/{batch_id}/status")
        if r.json()["status"] in ("completed", "failed", "cancelled"):
            break
        time.sleep(0.1)
    assert r.json()["status"] == "completed"
    assert r.json()["completed"] == 2


def test_anonymous_returns_401(authed_client: TestClient) -> None:
    authed_client.cookies.clear()
    r = authed_client.post("/batch/start", json={"semester_label": "113-1"})
    assert r.status_code == 401


def test_status_404_for_unknown_batch(authed_client: TestClient) -> None:
    r = authed_client.get("/batch/does-not-exist/status")
    assert r.status_code == 404

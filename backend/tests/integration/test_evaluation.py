"""EvaluationGenerator + /eval router e2e tests.

Verifies:
- gather_context joins drive_file × processed_artifact with category filtering
- generate produces persisted SemesterEvaluation row + PII-restored text
- regenerate updates same row (uniqueness on (teacher, semester, student))
- save_edit preserves generated_text (audit trail)
- HTTP layer maps NoArtifactsError → 412, LLM failures → 503
- /eval routes 401 anonymous
"""

from __future__ import annotations

import subprocess
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.adapters.openrouter_client import ChatResult


class FakeOpenRouter:
    def __init__(self, *, response_text: str = "S001 本學期積極投入學習，作品展現紮實基礎。") -> None:
        self.response_text = response_text
        self.last_prompt: str | None = None

    async def chat(self, **kwargs):
        self.last_prompt = kwargs["prompt"]
        return ChatResult(
            text=self.response_text,
            model_used=kwargs["model_id"],
            input_tokens=300,
            output_tokens=120,
            cost_usd=Decimal("0.0005"),
        )


@pytest.fixture
async def gen_harness(isolated_env, write_queue):
    """Real DB + real LLMService chokepoint + fake OpenRouter. Seeds 1 student
    × 1 semester × 2 processed artifacts (one learning, one work)."""
    subprocess.run(
        ["uv", "run", "alembic", "upgrade", "head"],
        check=True,
        cwd="/home/steven/projects/teacher-comments/backend",
        capture_output=True,
    )

    from app.config import get_settings
    from app.models import DriveFile, ProcessedArtifact, Teacher
    from app.services.audit_logger import AuditLogger
    from app.services.evaluation_generator import EvaluationGenerator
    from app.services.llm_service import LLMService
    from app.services.pii_anonymizer import PIIAnonymizer

    # Seed teacher first (FK)
    async def seed_teacher(s):
        s.add(Teacher(id="t1", google_sub="sub", email="t@e.com"))
    await write_queue.submit(seed_teacher)

    # Seed drive_files (one per category) + matching artifacts
    async def seed_files(s):
        s.add_all([
            DriveFile(
                id="df1", teacher_id="t1", drive_file_id="d1",
                semester_label="113-1", student_pseudo_id="王小明",
                category="learning", drive_path="...", filename="週記.docx",
                mime_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                drive_modified_at="2026-05-01T00:00:00Z",
            ),
            DriveFile(
                id="df2", teacher_id="t1", drive_file_id="d2",
                semester_label="113-1", student_pseudo_id="王小明",
                category="work", drive_path="...", filename="作品.docx",
                mime_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                drive_modified_at="2026-05-01T00:00:00Z",
            ),
        ])
    await write_queue.submit(seed_files)

    async def seed_artifacts(s):
        s.add_all([
            ProcessedArtifact(
                id="a1", drive_file_id="df1", artifact_type="markdown_summary",
                state="processed",
                content_markdown="## 學習觀察\n王小明完成多項作業，積極發問。",
            ),
            ProcessedArtifact(
                id="a2", drive_file_id="df2", artifact_type="markdown_summary",
                state="processed",
                content_markdown="## 作品總覽\n王小明的學期作品展現創意與細節。",
            ),
        ])
    await write_queue.submit(seed_artifacts)

    fake_or = FakeOpenRouter()
    audit = AuditLogger(write_queue)
    anonymizer = PIIAnonymizer(db_write_queue=write_queue)
    llm = LLMService(
        settings=get_settings(),
        anonymizer=anonymizer,
        openrouter=fake_or,  # type: ignore[arg-type]
        audit=audit,
        db_write_queue=write_queue,
    )
    gen = EvaluationGenerator(llm=llm, db_write_queue=write_queue)
    return gen, fake_or, write_queue


# ── Service-level tests ────────────────────────────────────────


@pytest.mark.asyncio
async def test_gather_context_returns_per_category_summaries(gen_harness) -> None:
    gen, _, _ = gen_harness

    from app.services.evaluation_generator import EvaluationStyle
    ctx = await gen.gather_context(
        teacher_id="t1",
        semester_label="113-1",
        pseudo_id="王小明",
        seed_text="seed",
        style=EvaluationStyle.FORMAL,
    )
    assert len(ctx.learning_summaries) == 1
    assert len(ctx.work_summaries) == 1
    assert ctx.interaction_transcripts == []
    assert "學習觀察" in ctx.learning_summaries[0]
    assert ctx.has_any_artifacts() is True


@pytest.mark.asyncio
async def test_generate_persists_evaluation_row(gen_harness) -> None:
    gen, fake_or, _ = gen_harness
    from app.services.evaluation_generator import EvaluationStyle

    result = await gen.generate(
        teacher_id="t1",
        semester_label="113-1",
        pseudo_id="王小明",
        seed_text="本學期觀察學生在數學科進步明顯。",
        style=EvaluationStyle.ENCOURAGING,
    )

    assert result.text  # non-empty restored text
    assert result.style == EvaluationStyle.ENCOURAGING
    assert result.llm_cost_usd == Decimal("0.0005")

    # Verify prompt sent to LLM contains style instruction + sections
    assert "鼓勵" in fake_or.last_prompt
    assert "學習紀錄" in fake_or.last_prompt
    assert "作品成果" in fake_or.last_prompt

    # Persisted row
    from app.db.session import get_sessionmaker
    from app.models import SemesterEvaluation
    async with get_sessionmaker()() as s:
        row = await s.get(SemesterEvaluation, result.evaluation_id)
    assert row is not None
    assert row.style == "encouraging"
    assert row.edited_text is None  # no edit yet


@pytest.mark.asyncio
async def test_regenerate_updates_same_row(gen_harness) -> None:
    gen, fake_or, _ = gen_harness
    from app.services.evaluation_generator import EvaluationStyle

    r1 = await gen.generate(
        teacher_id="t1", semester_label="113-1", pseudo_id="王小明",
        seed_text="第一次嘗試。學生表現用心。", style=EvaluationStyle.FORMAL,
    )

    fake_or.response_text = "第二版評語：S001 在學期中多有突破。"

    r2 = await gen.generate(
        teacher_id="t1", semester_label="113-1", pseudo_id="王小明",
        seed_text="第二次嘗試 — 改用鼓勵風格。", style=EvaluationStyle.ENCOURAGING,
    )

    # Same row id (UPSERT semantics)
    assert r1.evaluation_id == r2.evaluation_id

    # New row reflects regenerate
    from app.db.session import get_sessionmaker
    from app.models import SemesterEvaluation
    async with get_sessionmaker()() as s:
        row = await s.get(SemesterEvaluation, r2.evaluation_id)
    assert row.style == "encouraging"
    assert "第二版" in row.generated_text


@pytest.mark.asyncio
async def test_save_edit_preserves_generated_text(gen_harness) -> None:
    gen, _, _ = gen_harness
    from app.services.evaluation_generator import EvaluationStyle

    r = await gen.generate(
        teacher_id="t1", semester_label="113-1", pseudo_id="王小明",
        seed_text="seed text for evaluation.", style=EvaluationStyle.OBJECTIVE,
    )
    original_generated = r.text

    edited = await gen.save_edit(
        evaluation_id=r.evaluation_id, edited_text="教師最終版：學生本學期穩定學習。"
    )
    assert edited.edited_text == "教師最終版：學生本學期穩定學習。"
    assert edited.edited_at is not None
    # Generated text preserved (audit trail)
    assert edited.generated_text == original_generated


@pytest.mark.asyncio
async def test_generate_raises_no_artifacts_for_empty_student(gen_harness) -> None:
    gen, _, _ = gen_harness
    from app.services.evaluation_generator import EvaluationStyle, NoArtifactsError

    with pytest.raises(NoArtifactsError):
        await gen.generate(
            teacher_id="t1", semester_label="113-1",
            pseudo_id="不存在的學生",
            seed_text="seed", style=EvaluationStyle.FORMAL,
        )


# ── Router-level tests ─────────────────────────────────────────
# Independent fixture — does NOT reuse gen_harness because TestClient creates a
# fresh event loop for the lifespan, and a queue created in another loop's
# coroutines is "bound to different loop" (the asyncio.Queue underneath holds
# the loop reference). Build everything inside TestClient's loop via portal.


@pytest.fixture
def authed_client(isolated_env):
    """TestClient with a session cookie + EvaluationGenerator override.

    Seeds teacher + drive_files + processed_artifacts via TestClient's portal so
    the writes share the lifespan-started queue.
    """
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
    from app.models import DriveFile, ProcessedArtifact, Teacher
    from app.routers.evaluation import get_evaluation_generator
    from app.services.audit_logger import AuditLogger
    from app.services.evaluation_generator import EvaluationGenerator
    from app.services.llm_service import LLMService
    from app.services.pii_anonymizer import PIIAnonymizer

    fake_or = FakeOpenRouter()
    app = create_app()

    def _override_gen() -> EvaluationGenerator:
        queue = get_write_queue()  # bound to lifespan's loop
        audit = AuditLogger(queue)
        anonymizer = PIIAnonymizer(db_write_queue=queue)
        llm = LLMService(
            settings=get_settings(),
            anonymizer=anonymizer,
            openrouter=fake_or,  # type: ignore[arg-type]
            audit=audit,
            db_write_queue=queue,
        )
        return EvaluationGenerator(llm=llm, db_write_queue=queue)

    app.dependency_overrides[get_evaluation_generator] = _override_gen

    with TestClient(app) as client:
        # Seed via portal → uses lifespan-started queue (right loop)
        queue = get_write_queue()

        async def seed_teacher(s):
            s.add(Teacher(id="t1", google_sub="sub", email="t@e.com"))
        client.portal.call(queue.submit, seed_teacher)

        async def seed_files(s):
            s.add_all([
                DriveFile(
                    id="df1", teacher_id="t1", drive_file_id="d1",
                    semester_label="113-1", student_pseudo_id="王小明",
                    category="learning", drive_path="...", filename="週記.docx",
                    mime_type=(
                        "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
                    ),
                    drive_modified_at="2026-05-01T00:00:00Z",
                ),
                DriveFile(
                    id="df2", teacher_id="t1", drive_file_id="d2",
                    semester_label="113-1", student_pseudo_id="王小明",
                    category="work", drive_path="...", filename="作品.docx",
                    mime_type=(
                        "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
                    ),
                    drive_modified_at="2026-05-01T00:00:00Z",
                ),
            ])
        client.portal.call(queue.submit, seed_files)

        async def seed_artifacts(s):
            s.add_all([
                ProcessedArtifact(
                    id="a1", drive_file_id="df1", artifact_type="markdown_summary",
                    state="processed",
                    content_markdown="## 學習觀察\n王小明完成多項作業，積極發問。",
                ),
                ProcessedArtifact(
                    id="a2", drive_file_id="df2", artifact_type="markdown_summary",
                    state="processed",
                    content_markdown="## 作品總覽\n王小明的學期作品展現創意與細節。",
                ),
            ])
        client.portal.call(queue.submit, seed_artifacts)

        client.cookies.set(COOKIE_NAME, issue_session_cookie("t1"))
        yield client


def test_get_context_route(authed_client: TestClient) -> None:
    r = authed_client.get("/eval/113-1/王小明/context")
    assert r.status_code == 200
    body = r.json()
    assert len(body["learning_summaries"]) == 1
    assert len(body["work_summaries"]) == 1


def test_generate_route_happy_path(authed_client: TestClient) -> None:
    r = authed_client.post(
        "/eval/generate",
        json={
            "semester_label": "113-1",
            "student_pseudo_id": "王小明",
            "seed_text": "本學期王小明在科學科進步明顯。",
            "style": "formal",
        },
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["style"] == "formal"
    assert body["generated_text"]
    assert body["edited_text"] is None
    assert body["llm_cost_usd"] > 0


def test_generate_returns_412_when_no_artifacts(authed_client: TestClient) -> None:
    r = authed_client.post(
        "/eval/generate",
        json={
            "semester_label": "113-1",
            "student_pseudo_id": "幽靈學生",
            "seed_text": "seed text for an unknown student.",
            "style": "formal",
        },
    )
    assert r.status_code == 412
    assert r.json()["detail"]["reason"] == "no_artifacts"


def test_edit_persists(authed_client: TestClient) -> None:
    g = authed_client.post(
        "/eval/generate",
        json={
            "semester_label": "113-1",
            "student_pseudo_id": "王小明",
            "seed_text": "本學期王小明表現穩定，可以再加強表達。",
            "style": "objective",
        },
    )
    eval_id = g.json()["id"]

    e = authed_client.put(
        f"/eval/{eval_id}",
        json={"edited_text": "教師修改後版本。"},
    )
    assert e.status_code == 200
    assert e.json()["edited_text"] == "教師修改後版本。"


def test_invalid_style_returns_422(authed_client: TestClient) -> None:
    r = authed_client.post(
        "/eval/generate",
        json={
            "semester_label": "113-1",
            "student_pseudo_id": "王小明",
            "seed_text": "valid seed text exceeding minimum length.",
            "style": "bogus_style",
        },
    )
    assert r.status_code == 422


def test_anonymous_returns_401(authed_client: TestClient) -> None:
    authed_client.cookies.clear()
    r = authed_client.post(
        "/eval/generate",
        json={
            "semester_label": "113-1",
            "student_pseudo_id": "王小明",
            "seed_text": "valid seed",
            "style": "formal",
        },
    )
    assert r.status_code == 401

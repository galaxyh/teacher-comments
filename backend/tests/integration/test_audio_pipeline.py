"""Phase 10 audio pipeline tests — audio routes through AudioExtractor → audio_standard."""

from __future__ import annotations

import subprocess
from decimal import Decimal

import pytest

from app.adapters.openrouter_client import ChatResult


class FakeDriveClient:
    def __init__(self, *, file_bytes: bytes) -> None:
        self.file_bytes = file_bytes

    async def download_file(self, *, drive_file_id: str) -> bytes:
        return self.file_bytes


class FakeOpenRouter:
    def __init__(self) -> None:
        self.last_kwargs: dict | None = None

    async def chat(self, **kwargs):
        self.last_kwargs = kwargs
        return ChatResult(
            text="講者A：今天我們討論…\n講者B：是的…",
            model_used=kwargs["model_id"],
            input_tokens=5000,
            output_tokens=400,
            cost_usd=Decimal("0.005"),
        )


@pytest.fixture
async def audio_harness(isolated_env, write_queue):
    subprocess.run(
        ["uv", "run", "alembic", "upgrade", "head"],
        check=True,
        cwd="/home/steven/projects/teacher-comments/backend",
        capture_output=True,
    )

    from app.adapters.document_extractors import build_default_registry
    from app.config import get_settings
    from app.models import DriveFile, Teacher
    from app.services.audit_logger import AuditLogger
    from app.services.llm_service import LLMService
    from app.services.pii_anonymizer import PIIAnonymizer
    from app.services.processing_pipeline import ProcessingPipeline

    async def insert_teacher(s):
        s.add(Teacher(id="t1", google_sub="sub", email="t@e.com"))
    await write_queue.submit(insert_teacher)

    audio_bytes = b"\xff\xfb\x90\xc4" + b"\x00" * 1024  # mp3-ish header + body

    async def insert_file(s):
        s.add(
            DriveFile(
                id="dfaud",
                teacher_id="t1",
                drive_file_id="aud-id",
                semester_label="113-1",
                student_pseudo_id="王小明",
                category="interaction",
                drive_path="...",
                filename="晤談.mp3",
                mime_type="audio/mpeg",
                drive_modified_at="2026-05-01T00:00:00Z",
            )
        )
    await write_queue.submit(insert_file)

    fake_drive = FakeDriveClient(file_bytes=audio_bytes)
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

    async def factory(*, teacher_id: str):
        return fake_drive

    pipeline = ProcessingPipeline(
        drive_client_factory=factory,  # type: ignore[arg-type]
        extractors=build_default_registry(),
        llm=llm,
    )

    from app.db.session import get_sessionmaker
    async with get_sessionmaker()() as s:
        df = await s.get(DriveFile, "dfaud")
    return pipeline, df, fake_or, audio_bytes


@pytest.mark.asyncio
async def test_audio_routed_to_audio_tier(audio_harness) -> None:
    pipeline, drive_file, fake_or, audio_bytes = audio_harness

    result = await pipeline.process(teacher_id="t1", drive_file=drive_file)

    assert result.llm_tier.value == "audio_standard"
    assert result.artifact_type == "transcript"
    # OpenRouter received audio_bytes
    assert fake_or.last_kwargs["audio_bytes"] == audio_bytes
    assert fake_or.last_kwargs["audio_mime"] == "audio/mpeg"
    # Prompt includes PII placeholder rule
    assert "占位符" in fake_or.last_kwargs["prompt"]
    # Output is a transcript
    assert "講者A" in result.content_markdown


@pytest.mark.asyncio
async def test_openrouter_messages_with_audio() -> None:
    """_build_messages produces input_audio part with format derived from MIME."""
    from app.adapters.openrouter_client import OpenRouterClient

    msgs = OpenRouterClient._build_messages(
        prompt="transcribe", image_bytes=None, image_mime=None,
        audio_bytes=b"\xff\xfb\x00", audio_mime="audio/mpeg",
    )
    parts = msgs[0]["content"]
    assert parts[0] == {"type": "text", "text": "transcribe"}
    assert parts[1]["type"] == "input_audio"
    assert parts[1]["input_audio"]["format"] == "mp3"
    assert parts[1]["input_audio"]["data"]  # base64 string non-empty


def test_audio_extractor_warns_on_oversize(isolated_env) -> None:
    import asyncio

    from app.adapters.document_extractors.audio import MAX_AUDIO_BYTES, AudioExtractor

    ext = AudioExtractor()
    big = b"\x00" * (MAX_AUDIO_BYTES + 1024)
    result = asyncio.get_event_loop_policy().new_event_loop().run_until_complete(
        ext.extract(file_bytes=big, filename="big.mp3")
    )
    assert any("larger" in w for w in result.warnings)
    assert result.text == ""


def test_audio_extractor_supports_common_mimes() -> None:
    from app.adapters.document_extractors.audio import AudioExtractor

    ext = AudioExtractor()
    assert ext.supports(mime_type="audio/mpeg", filename="x")
    assert ext.supports(mime_type="audio/wav", filename="x")
    assert ext.supports(mime_type="application/octet-stream", filename="rec.mp3")
    assert ext.supports(mime_type="application/octet-stream", filename="rec.m4a")
    assert not ext.supports(mime_type="text/plain", filename="x.txt")


@pytest.mark.asyncio
async def test_pipeline_routes_audio_filename_with_octet_stream(audio_harness, write_queue) -> None:
    """If Drive returns generic application/octet-stream but filename is .mp3,
    routing still picks audio tier."""
    pipeline, _, fake_or, _ = audio_harness
    from app.models import DriveFile

    async def insert(s):
        s.add(
            DriveFile(
                id="dfaud2",
                teacher_id="t1",
                drive_file_id="aud-id-2",
                semester_label="113-1",
                student_pseudo_id="王小明",
                category="interaction",
                drive_path="...",
                filename="recording.m4a",
                mime_type="application/octet-stream",
                drive_modified_at="2026-05-01T00:00:00Z",
            )
        )
    await write_queue.submit(insert)

    from app.db.session import get_sessionmaker
    async with get_sessionmaker()() as s:
        df2 = await s.get(DriveFile, "dfaud2")

    result = await pipeline.process(teacher_id="t1", drive_file=df2)
    assert result.llm_tier.value == "audio_standard"

"""Phase 9 vision pipeline tests — image goes through ImageExtractor → vision_cheap."""

from __future__ import annotations

import io
import subprocess
from decimal import Decimal

import pytest
from PIL import Image

from app.adapters.openrouter_client import ChatResult


def _build_png() -> bytes:
    img = Image.new("RGB", (4, 4), color="red")
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


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
            text="## 摘要\n- 圖中為一張紅色作品",
            model_used=kwargs["model_id"],
            input_tokens=200,
            output_tokens=80,
            cost_usd=Decimal("0.0003"),
        )


@pytest.fixture
async def vision_harness(isolated_env, write_queue):
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

    png_bytes = _build_png()

    async def insert_file(s):
        s.add(
            DriveFile(
                id="dfimg",
                teacher_id="t1",
                drive_file_id="img-id",
                semester_label="113-1",
                student_pseudo_id="王小明",
                category="work",
                drive_path="...",
                filename="作品.png",
                mime_type="image/png",
                drive_modified_at="2026-05-01T00:00:00Z",
            )
        )
    await write_queue.submit(insert_file)

    fake_drive = FakeDriveClient(file_bytes=png_bytes)
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
        df = await s.get(DriveFile, "dfimg")
    return pipeline, df, fake_or, png_bytes


@pytest.mark.asyncio
async def test_image_routed_to_vision_tier(vision_harness) -> None:
    pipeline, drive_file, fake_or, png_bytes = vision_harness

    result = await pipeline.process(teacher_id="t1", drive_file=drive_file)

    assert result.llm_tier.value == "vision_cheap"
    # OpenRouter received image_bytes
    assert fake_or.last_kwargs["image_bytes"] == png_bytes
    assert fake_or.last_kwargs["image_mime"] == "image/png"
    # Prompt instructs the LLM not to transcribe PII
    assert "不要" in fake_or.last_kwargs["prompt"]


@pytest.mark.asyncio
async def test_openrouter_messages_with_image_are_multimodal() -> None:
    """Unit-level check on OpenRouterClient.chat message construction."""
    from app.adapters.openrouter_client import OpenRouterClient

    msgs = OpenRouterClient._build_messages(
        prompt="describe this", image_bytes=b"\x89PNG\r\n", image_mime="image/png"
    )
    assert msgs[0]["role"] == "user"
    parts = msgs[0]["content"]
    assert parts[0] == {"type": "text", "text": "describe this"}
    assert parts[1]["type"] == "image_url"
    assert parts[1]["image_url"]["url"].startswith("data:image/png;base64,")


def test_openrouter_messages_without_image_stay_simple() -> None:
    from app.adapters.openrouter_client import OpenRouterClient

    msgs = OpenRouterClient._build_messages(
        prompt="describe", image_bytes=None, image_mime=None
    )
    assert msgs == [{"role": "user", "content": "describe"}]


@pytest.mark.asyncio
async def test_image_extractor_warns_on_oversize(isolated_env) -> None:
    """ImageExtractor surfaces a warning if the image is bigger than MAX_IMAGE_BYTES."""
    from app.adapters.document_extractors.image import (
        MAX_IMAGE_BYTES,
        ImageExtractor,
    )

    ext = ImageExtractor()
    big = b"\x00" * (MAX_IMAGE_BYTES + 1024)
    result = await ext.extract(file_bytes=big, filename="big.jpg")
    assert any("larger" in w for w in result.warnings)
    assert result.has_images is True
    assert result.text == ""

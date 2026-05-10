"""LLMService integration tests with FakeOpenRouter.

Verifies the chokepoint:
- Anonymise → boundary check → OpenRouter → restore → audit
- PIILeakageError raised when boundary trips (model never called)
- Retry on rate limit / timeout
- llm_call_audit row written on success
- system_event 'pii_leakage_detected' written on Layer 2 trip
"""

from __future__ import annotations

import subprocess
from dataclasses import dataclass
from decimal import Decimal

import pytest
from sqlalchemy import select

from app.adapters.openrouter_client import ChatResult, OpenRouterClient
from app.core.exceptions import LLMRateLimitError, PIILeakageError
from app.services.llm_service import LLMService, TaskTier


@dataclass
class _Call:
    model_id: str
    prompt: str


class FakeOpenRouter:
    """Programmable stub. Records every chat call; returns canned responses or raises."""

    def __init__(
        self,
        *,
        response_text: str = "default-response",
        rate_limit_attempts: int = 0,
    ) -> None:
        self.response_text = response_text
        self._remaining_rate_limits = rate_limit_attempts
        self.calls: list[_Call] = []

    async def chat(
        self,
        *,
        model_id: str,
        prompt: str,
        max_output_tokens: int = 1024,
        temperature: float = 0.7,
        timeout: float = 60.0,
        image_bytes: bytes | None = None,
        image_mime: str | None = None,
        audio_bytes: bytes | None = None,
        audio_mime: str | None = None,
    ) -> ChatResult:
        self.calls.append(_Call(model_id=model_id, prompt=prompt))

        if self._remaining_rate_limits > 0:
            self._remaining_rate_limits -= 1
            raise LLMRateLimitError("simulated 429", context={"model": model_id})

        return ChatResult(
            text=self.response_text,
            model_used=model_id,
            input_tokens=100,
            output_tokens=50,
            cost_usd=Decimal("0.0001"),
        )


@pytest.fixture
async def llm_harness(isolated_env, write_queue):
    """LLMService wired with FakeOpenRouter + real PIIAnonymizer + DB."""
    subprocess.run(
        ["uv", "run", "alembic", "upgrade", "head"],
        check=True,
        cwd="/home/steven/projects/teacher-comments/backend",
        capture_output=True,
    )

    from app.config import get_settings
    from app.db.session import get_sessionmaker
    from app.models import Teacher
    from app.services.audit_logger import AuditLogger
    from app.services.pii_anonymizer import PIIAnonymizer

    # Seed teacher
    async def insert_teacher(session) -> str:
        t = Teacher(id="t1", google_sub="sub", email="t@e.com")
        session.add(t)
        return "t1"
    await write_queue.submit(insert_teacher)

    fake_or = FakeOpenRouter()
    audit = AuditLogger(write_queue)
    anonymizer = PIIAnonymizer(db_write_queue=write_queue)

    service = LLMService(
        settings=get_settings(),
        anonymizer=anonymizer,
        openrouter=fake_or,  # type: ignore[arg-type]
        audit=audit,
        db_write_queue=write_queue,
    )
    return service, fake_or, anonymizer


@pytest.mark.asyncio
async def test_happy_path(llm_harness) -> None:
    service, fake_or, _ = llm_harness
    fake_or.response_text = "S001 表現優異"

    result = await service.call(
        tier=TaskTier.SUMMARY_CHEAP,
        teacher_id="t1",
        prompt="0912345678 是學生家長電話",
        purpose="unit_test",
    )

    # The fake should have been called once with PII-anonymised prompt
    assert len(fake_or.calls) == 1
    assert "0912345678" not in fake_or.calls[0].prompt
    # Restored output
    assert result.output_text == "S001 表現優異"  # No restoration needed (no mapping for S001)
    assert result.input_tokens == 100
    assert result.cost_usd == Decimal("0.0001")


@pytest.mark.asyncio
async def test_audit_row_written(llm_harness) -> None:
    service, _, _ = llm_harness

    result = await service.call(
        tier=TaskTier.SUMMARY_CHEAP,
        teacher_id="t1",
        prompt="email me at a@b.com",
        purpose="audit_test",
    )

    from app.db.session import get_sessionmaker
    from app.models import LLMCallAudit

    async with get_sessionmaker()() as session:
        audit = await session.get(LLMCallAudit, result.audit_id)

    assert audit is not None
    assert audit.teacher_id == "t1"
    assert audit.tier == "summary_cheap"
    assert audit.purpose == "audit_test"
    assert audit.pii_replacement_count == 1
    assert audit.input_tokens == 100


@pytest.mark.asyncio
async def test_rate_limit_retry_then_success(llm_harness, monkeypatch) -> None:
    service, fake_or, _ = llm_harness
    fake_or._remaining_rate_limits = 2  # Two failures, then success

    # Skip the actual sleep to keep test fast — patch asyncio.sleep
    import asyncio as _asyncio

    async def no_sleep(_seconds: float) -> None:
        return None
    monkeypatch.setattr(_asyncio, "sleep", no_sleep)

    result = await service.call(
        tier=TaskTier.SUMMARY_CHEAP,
        teacher_id="t1",
        prompt="hello world",
        purpose="retry_test",
    )

    # Three calls total (2 failed + 1 success)
    assert len(fake_or.calls) == 3
    assert result.output_text == "default-response"


@pytest.mark.asyncio
async def test_rate_limit_exhaustion_propagates(llm_harness, monkeypatch) -> None:
    service, fake_or, _ = llm_harness
    fake_or._remaining_rate_limits = 100  # always rate-limited

    import asyncio as _asyncio
    async def no_sleep(_seconds: float) -> None:
        return None
    monkeypatch.setattr(_asyncio, "sleep", no_sleep)

    with pytest.raises(LLMRateLimitError):
        await service.call(
            tier=TaskTier.SUMMARY_CHEAP,
            teacher_id="t1",
            prompt="hello",
            purpose="retry_exhaustion",
            retry=3,
        )


@pytest.mark.asyncio
async def test_pii_leakage_aborts_call(llm_harness) -> None:
    """If anonymizer fails to substitute (simulated by patching), boundary trips."""
    service, fake_or, anonymizer = llm_harness

    # Patch anonymizer to return text with PII still in it (simulates a bug)
    from app.services.pii_anonymizer import AnonymizeResult

    async def buggy_anonymize(*, text: str, teacher_id: str) -> AnonymizeResult:
        # Pretend to anonymize but actually leave PII present
        return AnonymizeResult(
            anonymized_text="contact me at 0912345678",
            replacements=0,
            new_mappings_added=0,
        )

    anonymizer.anonymize = buggy_anonymize  # type: ignore[method-assign]

    with pytest.raises(PIILeakageError):
        await service.call(
            tier=TaskTier.SUMMARY_CHEAP,
            teacher_id="t1",
            prompt="contact me at 0912345678",
            purpose="leakage_test",
        )

    # OpenRouter MUST NOT have been called
    assert len(fake_or.calls) == 0

    # system_event row written
    from app.db.session import get_sessionmaker
    from app.models import SystemEvent

    async with get_sessionmaker()() as session:
        events = (
            await session.execute(
                select(SystemEvent).where(SystemEvent.event_type == "pii_leakage_detected")
            )
        ).scalars().all()
    assert len(events) == 1
    assert events[0].severity == "critical"
    assert events[0].teacher_id == "t1"

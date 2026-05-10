"""LLMService — chokepoint #2 (security.md, ARCH-001 §4.1).

The ONLY path to OpenRouterClient. Enforces:
1. PIIAnonymizer.anonymize() pre-call (Layer 1)
2. no_pii_in_anonymized() boundary check (Layer 2 tripwire)
3. OpenRouterClient.chat() — only when Layer 2 passes
4. PIIAnonymizer.restore() on response
5. AuditLogger writes llm_call_audit row + system_event on failures

This is Phase 3 scope. Vision and audio tiers (D8 vision_cheap / audio_standard)
extend `prompt: LLMInput` in Phase 5+ — for now LLMInput is text-only.

Retry strategy follows api-design.md "HTTP Retry Must Handle Both Transport and
Application Errors": exponential backoff on rate limit / timeout, propagate on
4xx-not-429, and a tripped boundary IS a critical incident — not retriable, not
suppressible.
"""

from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass
from decimal import Decimal
from enum import Enum

from sqlalchemy.ext.asyncio import AsyncSession

from app.adapters.openrouter_client import ChatResult, OpenRouterClient
from app.config import Settings
from app.core.exceptions import (
    LLMRateLimitError,
    LLMTimeoutError,
    PIILeakageError,
)
from app.db.write_queue import DBWriteQueue
from app.models import LLMCallAudit
from app.models._helpers import gen_uuid, utcnow_iso
from app.services.audit_logger import AuditLogger
from app.services.pii_anonymizer import PIIAnonymizer, no_pii_in_anonymized

logger = logging.getLogger(__name__)


class TaskTier(str, Enum):
    SUMMARY_CHEAP = "summary_cheap"
    VISION_CHEAP = "vision_cheap"
    AUDIO_STANDARD = "audio_standard"
    EVALUATION_QUALITY = "evaluation_quality"


@dataclass
class LLMCallResult:
    output_text: str            # PII-restored — safe to display to teacher
    raw_output_text: str        # PII-anonymized — what the model actually returned
    model_used: str
    input_tokens: int
    output_tokens: int
    cost_usd: Decimal
    audit_id: str               # llm_call_audit.id


class LLMService:
    def __init__(
        self,
        *,
        settings: Settings,
        anonymizer: PIIAnonymizer,
        openrouter: OpenRouterClient,
        audit: AuditLogger,
        db_write_queue: DBWriteQueue,
    ) -> None:
        self._settings = settings
        self._anonymizer = anonymizer
        self._openrouter = openrouter
        self._audit = audit
        self._queue = db_write_queue

    def _model_for_tier(self, tier: TaskTier) -> str:
        """Resolve tier → model via Settings (architecture.md "Declared Config Must Be Plumbed")."""
        return self._settings.llm_model_for_tier(tier.value)  # type: ignore[arg-type]

    async def call(
        self,
        *,
        tier: TaskTier,
        teacher_id: str,
        prompt: str,
        purpose: str,
        image_bytes: bytes | None = None,
        image_mime: str | None = None,
        audio_bytes: bytes | None = None,
        audio_mime: str | None = None,
        max_output_tokens: int = 1024,
        retry: int = 3,
    ) -> LLMCallResult:
        """Anonymise → boundary check → OpenRouter → restore → audit.

        `purpose` is a free-text label written to llm_call_audit.purpose (e.g.,
        'docx_summary', 'evaluation_draft'). It distinguishes call sites in audits.

        For vision tiers (`vision_cheap`), pass `image_bytes` + `image_mime`. The
        text prompt is still anonymised + boundary-checked; the image is forwarded
        as-is. PII visible in the image (handwriting, photos) is OUTSIDE this layer's
        protection — caller (ProcessingPipeline) MUST emit prompt instructions
        forbidding PII transcription, and the response is still PII-restored.
        """
        model_id = self._model_for_tier(tier)
        started_at = time.monotonic()

        # Step 1 — anonymise
        anon_result = await self._anonymizer.anonymize(text=prompt, teacher_id=teacher_id)

        # Step 2 — boundary tripwire
        if not no_pii_in_anonymized(anon_result.anonymized_text):
            # Critical: log to system_event, raise — DO NOT POST TO OPENROUTER
            await self._audit.log_event(
                "pii_leakage_detected",
                teacher_id=teacher_id,
                severity="critical",
                payload={
                    "tier": tier.value,
                    "purpose": purpose,
                    "model_id": model_id,
                    # Intentionally NOT logging the offending text — we don't want
                    # raw PII in audit logs either. The replacements count + tier
                    # is enough to triage.
                    "replacements_attempted": anon_result.replacements,
                },
            )
            raise PIILeakageError(
                "Boundary check tripped — anonymizer output still contains PII pattern",
                context={"tier": tier.value, "purpose": purpose},
            )

        # Step 3 — OpenRouter call with bounded retry
        chat_result = await self._call_with_retry(
            model_id=model_id,
            anonymized_prompt=anon_result.anonymized_text,
            image_bytes=image_bytes,
            image_mime=image_mime,
            audio_bytes=audio_bytes,
            audio_mime=audio_mime,
            max_output_tokens=max_output_tokens,
            retry=retry,
        )

        # Step 4 — restore PII in response
        restored = await self._anonymizer.restore(
            text=chat_result.text, teacher_id=teacher_id
        )

        # Step 5 — audit row
        duration_ms = int((time.monotonic() - started_at) * 1000)
        audit_id = await self._record_audit(
            teacher_id=teacher_id,
            tier=tier,
            chat_result=chat_result,
            purpose=purpose,
            replacement_count=anon_result.replacements,
            duration_ms=duration_ms,
        )

        return LLMCallResult(
            output_text=restored,
            raw_output_text=chat_result.text,
            model_used=chat_result.model_used,
            input_tokens=chat_result.input_tokens,
            output_tokens=chat_result.output_tokens,
            cost_usd=chat_result.cost_usd,
            audit_id=audit_id,
        )

    # ── internals ────────────────────────────────────────────────

    async def _call_with_retry(
        self,
        *,
        model_id: str,
        anonymized_prompt: str,
        max_output_tokens: int,
        retry: int,
        image_bytes: bytes | None = None,
        image_mime: str | None = None,
        audio_bytes: bytes | None = None,
        audio_mime: str | None = None,
    ) -> ChatResult:
        """Exponential backoff: 2s, 6s, 18s. Re-raises on retry exhaustion."""
        last_exc: Exception | None = None
        for attempt in range(retry):
            try:
                return await self._openrouter.chat(
                    model_id=model_id,
                    prompt=anonymized_prompt,
                    image_bytes=image_bytes,
                    image_mime=image_mime,
                    audio_bytes=audio_bytes,
                    audio_mime=audio_mime,
                    max_output_tokens=max_output_tokens,
                )
            except (LLMRateLimitError, LLMTimeoutError) as exc:
                last_exc = exc
                if attempt == retry - 1:
                    break
                wait = 2 * (3**attempt)
                logger.warning(
                    "LLM call retriable error attempt=%d wait=%.1fs error=%s",
                    attempt + 1, wait, exc,
                )
                await asyncio.sleep(wait)

        assert last_exc is not None
        raise last_exc

    async def _record_audit(
        self,
        *,
        teacher_id: str,
        tier: TaskTier,
        chat_result: ChatResult,
        purpose: str,
        replacement_count: int,
        duration_ms: int,
    ) -> str:
        audit_id = gen_uuid()

        async def insert(session: AsyncSession) -> str:
            row = LLMCallAudit(
                id=audit_id,
                teacher_id=teacher_id,
                tier=tier.value,
                model_id=chat_result.model_used,
                purpose=purpose,
                input_tokens=chat_result.input_tokens,
                output_tokens=chat_result.output_tokens,
                cost_usd=float(chat_result.cost_usd),
                pii_replacement_count=replacement_count,
                duration_ms=duration_ms,
                created_at=utcnow_iso(),
            )
            session.add(row)
            return audit_id

        return await self._queue.submit(insert)

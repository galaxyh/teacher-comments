"""OpenRouter chat completion adapter.

Per ARCH-001 §4.3 / D8 / D9 — OpenRouter is the LLM gateway and the openai
SDK pointed at the OpenRouter base URL is the chosen client.

Phase 3 walking-skeleton scope: text-only chat completions. Vision and audio
tiers extend this surface in later phases.

Lessons-learned applied:
- framework-gotcha.md "OpenRouter Model Names Don't Always Match Documentation":
  this adapter accepts a `model_id` parameter; never hard-codes a name.
- framework-gotcha.md "HTTP Client SDK Error Structure Varies": classification
  uses both typed exception attributes and message-string fallback.
- api-design.md "HTTP Retry Must Handle Both Transport and Application Errors":
  retry decisions live in LLMService, not here — this adapter raises typed
  exceptions and the service classifies them.
"""

from __future__ import annotations

import base64
import logging
import re
from dataclasses import dataclass
from decimal import Decimal

from openai import APIError, AsyncOpenAI, RateLimitError as OpenAIRateLimitError

from app.core.exceptions import (
    LLMRateLimitError,
    LLMTimeoutError,
)

logger = logging.getLogger(__name__)


@dataclass
class ChatResult:
    text: str
    model_used: str
    input_tokens: int
    output_tokens: int
    cost_usd: Decimal


class OpenRouterClient:
    def __init__(self, *, api_key: str, base_url: str = "https://openrouter.ai/api/v1") -> None:
        self._client = AsyncOpenAI(api_key=api_key, base_url=base_url)

    async def chat(
        self,
        *,
        model_id: str,
        prompt: str,
        image_bytes: bytes | None = None,
        image_mime: str | None = None,
        max_output_tokens: int = 1024,
        temperature: float = 0.7,
        timeout: float = 60.0,
    ) -> ChatResult:
        """Single-turn chat completion. Raises classified errors on failure.

        When `image_bytes` is provided, sends a multimodal message: text prompt +
        an inline-base64 `image_url` part. The model_id MUST be a vision-capable
        model (e.g. `google/gemini-2.5-flash-lite`).
        """
        if not model_id:
            # Per architecture.md "Declared Config Must Be Plumbed" — empty model_id
            # means tier→model resolution returned an empty default, which is a config
            # bug. Catch at the boundary so it's clear where to look.
            raise ValueError("model_id is empty — Settings.llm_tier_* misconfigured")

        messages = self._build_messages(prompt=prompt, image_bytes=image_bytes, image_mime=image_mime)

        try:
            resp = await self._client.chat.completions.create(
                model=model_id,
                messages=messages,
                max_tokens=max_output_tokens,
                temperature=temperature,
                timeout=timeout,
            )
        except OpenAIRateLimitError as exc:
            raise LLMRateLimitError(
                "OpenRouter rate limit",
                context={"model": model_id, "raw": str(exc)},
            ) from exc
        except APIError as exc:
            status = self._classify_status(exc)
            if status == 429:
                raise LLMRateLimitError(
                    "OpenRouter 429", context={"model": model_id, "raw": str(exc)}
                ) from exc
            if status in (504, 408):
                raise LLMTimeoutError(
                    "OpenRouter timeout", context={"model": model_id, "raw": str(exc)}
                ) from exc
            # Non-retriable: bubble up unwrapped — LLMService handles it
            raise

        choice = resp.choices[0]
        usage = resp.usage
        cost = _calculate_cost(
            model_id=model_id,
            input_tokens=usage.prompt_tokens if usage else 0,
            output_tokens=usage.completion_tokens if usage else 0,
        )
        return ChatResult(
            text=choice.message.content or "",
            model_used=resp.model or model_id,
            input_tokens=usage.prompt_tokens if usage else 0,
            output_tokens=usage.completion_tokens if usage else 0,
            cost_usd=cost,
        )

    @staticmethod
    def _build_messages(
        *, prompt: str, image_bytes: bytes | None, image_mime: str | None
    ) -> list[dict]:
        """Construct OpenAI/OpenRouter chat-completions message format.

        Plain text → simple `{role: user, content: "..."}`. With an image,
        `content` becomes a list of parts (text + image_url with data URL).
        """
        if image_bytes is None:
            return [{"role": "user", "content": prompt}]

        mime = image_mime or "image/jpeg"
        b64 = base64.b64encode(image_bytes).decode("ascii")
        data_url = f"data:{mime};base64,{b64}"
        return [
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": prompt},
                    {"type": "image_url", "image_url": {"url": data_url}},
                ],
            }
        ]

    @staticmethod
    def _classify_status(exc: Exception) -> int | None:
        """Two-level classifier per framework-gotcha.md: typed first, regex fallback."""
        for attr in ("status_code", "code", "http_status"):
            val = getattr(exc, attr, None)
            if isinstance(val, int):
                return val
        m = re.match(r"(\d{3})\b", str(exc))
        return int(m.group(1)) if m else None


# ─── Cost table ───────────────────────────────────────────────────
# Approximate prices for Flash Lite (D9 default). Other tiers will need entries
# when their settings.llm_tier_* changes from the default. Kept here (not in
# Settings) because it's pricing data — changes via PR + ADR, not env vars.
PRICING_USD_PER_1M_TOKENS: dict[str, tuple[Decimal, Decimal]] = {
    # model_id: (input_per_1M, output_per_1M)
    "google/gemini-2.5-flash-lite": (Decimal("0.10"), Decimal("0.40")),
}


def _calculate_cost(*, model_id: str, input_tokens: int, output_tokens: int) -> Decimal:
    pricing = PRICING_USD_PER_1M_TOKENS.get(model_id)
    if pricing is None:
        # Unknown model — record 0; teacher will see "$ ?" in UI. Better than
        # making up a price. Update PRICING_USD_PER_1M_TOKENS when adding models.
        return Decimal("0")
    p_in, p_out = pricing
    return (
        Decimal(input_tokens) * p_in / Decimal("1000000")
        + Decimal(output_tokens) * p_out / Decimal("1000000")
    ).quantize(Decimal("0.000001"))

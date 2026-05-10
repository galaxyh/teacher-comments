"""Pydantic Settings — single source of truth for runtime config.

Per ARCH-001 §6.2 and lessons-learned/architecture.md "Declared Config Must Be Plumbed":
every field declared here MUST be read by some consumer. CI grep test in DESIGN-001 §5.3
fails the build if any service hardcodes a model ID instead of reading `settings.llm_tier_*`.
"""

from __future__ import annotations

import base64
from decimal import Decimal
from functools import lru_cache
from typing import Literal

from pydantic import AnyHttpUrl, Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # ── DB (D16: SQLite + WAL + aiosqlite) ──────────────────────────
    database_url: str = "sqlite+aiosqlite:///./data/teacher.db"

    # ── OAuth (Google) ──────────────────────────────────────────────
    google_client_id: SecretStr
    google_client_secret: SecretStr
    public_base_url: AnyHttpUrl

    # ── LLM (D8/D9) ─────────────────────────────────────────────────
    openrouter_api_key: SecretStr
    openrouter_base_url: str = "https://openrouter.ai/api/v1"

    # Tier-based routing — caller passes tier name, settings resolve to model ID.
    # Per D9 default: Flash Lite for all tiers (~$1-2/semester).
    llm_tier_summary_cheap: str = "google/gemini-2.5-flash-lite"
    llm_tier_vision_cheap: str = "google/gemini-2.5-flash-lite"
    llm_tier_audio_standard: str = "google/gemini-2.5-flash-lite"
    llm_tier_evaluation_quality: str = "google/gemini-2.5-flash-lite"

    # ── Crypto (AES-256-GCM, per-record nonce) ──────────────────────
    pii_encryption_key: SecretStr
    oauth_token_encryption_key: SecretStr
    session_secret_key: SecretStr

    # ── Performance tuning ──────────────────────────────────────────
    batch_worker_concurrency: int = Field(default=4, ge=1, le=16)
    budget_monthly_usd: Decimal = Decimal("5.00")

    # ── Observability ───────────────────────────────────────────────
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR"] = "INFO"
    sentry_dsn: str | None = None

    # ── Validators (defence-in-depth, surface config errors at boot) ─
    @field_validator(
        "pii_encryption_key", "oauth_token_encryption_key", mode="after"
    )
    @classmethod
    def _validate_aes_key(cls, v: SecretStr) -> SecretStr:
        """Reject keys that are not exactly 32 bytes when base64-decoded.

        Surfaces misconfiguration at startup instead of at first encryption call.
        """
        raw = v.get_secret_value()
        try:
            decoded = base64.b64decode(raw, validate=True)
        except Exception as e:
            raise ValueError(
                "Encryption key must be valid base64. Generate with: "
                "python -c \"import os, base64; print(base64.b64encode(os.urandom(32)).decode())\""
            ) from e
        if len(decoded) != 32:
            raise ValueError(
                f"Encryption key must decode to 32 bytes (AES-256), got {len(decoded)}"
            )
        return v

    def llm_model_for_tier(
        self,
        tier: Literal[
            "summary_cheap", "vision_cheap", "audio_standard", "evaluation_quality"
        ],
    ) -> str:
        """Resolve tier name → concrete OpenRouter model ID.

        Single chokepoint; LLMService MUST call this and never read tier fields directly,
        so that future per-teacher overrides (PRD §4.2 teacher.llm_tier_config) can be
        injected here without touching call sites.
        """
        return getattr(self, f"llm_tier_{tier}")


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Cached accessor — Settings is parsed once per process.

    Use FastAPI dependency `Depends(get_settings)` in routers; pass directly into
    services at construction time elsewhere.
    """
    return Settings()  # type: ignore[call-arg]

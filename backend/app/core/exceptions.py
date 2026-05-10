"""Custom exception hierarchy per ARCH-001 §6.3.

Routers map these to HTTP responses via FastAPI exception handlers.
Worker catches at outer level → maps to state='failed' (retriable) or
state='unprocessable' (terminal) per D-2026-05-10-04 / lessons-learned
architecture.md "Distinguish Terminal Failures from Retriable Failures".

Conventions:
- terminal=True  → state='unprocessable', no auto-retry
- terminal=False → state='failed', auto-retry up to 3x with exponential backoff
- The classmethod helpers (`is_terminal()`) let callers branch without isinstance chains.
"""

from __future__ import annotations


class AppError(Exception):
    """Base for all application-defined errors."""

    terminal: bool = False  # subclass override; default to retriable

    def __init__(self, message: str, *, context: dict | None = None) -> None:
        super().__init__(message)
        self.context = context or {}

    def is_terminal(self) -> bool:
        return self.terminal


# ── Auth ────────────────────────────────────────────────────────────
class AuthError(AppError):
    terminal = True


class OAuthRevokedError(AuthError):
    """Refresh token rejected by Google (user revoked, password changed, etc.)."""


class AttestationRequiredError(AuthError):
    """Onboarding attestation (D17) not yet signed for current consent version."""


# ── Drive ───────────────────────────────────────────────────────────
class DriveError(AppError):
    pass


class DriveQuotaExceededError(DriveError):
    """Drive API 429. Retriable with Retry-After backoff."""


class DriveFileNotFoundError(DriveError):
    """Drive returned 404 — file removed or permission revoked."""

    terminal = True


# ── Processing ──────────────────────────────────────────────────────
class ProcessingError(AppError):
    pass


class UnsupportedFormatError(ProcessingError):
    """Format outside V1 support matrix (e.g., .pages, .key)."""

    terminal = True


class DocumentExtractionError(ProcessingError):
    """Underlying extractor raised — corrupt or password-protected file."""

    terminal = True


class LLMRateLimitError(ProcessingError):
    """OpenRouter 429 — retriable."""


class LLMTimeoutError(ProcessingError):
    """OpenRouter timeout — retriable."""


class LLMQuotaExhaustedError(ProcessingError):
    """Daily quota hit per lessons-learned/architecture.md.

    Not auto-retried within the day; pauses the batch worker. Operator clears.
    """

    terminal = True


# ── PII ─────────────────────────────────────────────────────────────
class PIIError(AppError):
    pass


class PIILeakageError(PIIError):
    """Boundary check (security.md Layer 2) caught known-PII pattern in anonymized text.

    HTTP POST to LLM provider does NOT proceed. Critical incident:
    log to system_event(pii_leakage_detected) and pause batch.
    """

    terminal = True


class PIIRestorationError(PIIError):
    """Pseudonym → display_name lookup failed.

    Caller should fall back to showing the literal pseudonym + a banner per
    security.md anti-pattern guidance ("don't silently fail restore").
    """


# ── Config ──────────────────────────────────────────────────────────
class ConfigError(AppError):
    """Misconfiguration surfaced at startup. Always fatal — process exits."""

    terminal = True

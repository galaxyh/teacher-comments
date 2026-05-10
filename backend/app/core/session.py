"""Stateless session cookie via itsdangerous (per OAQ-4 same-domain decision).

Why itsdangerous + not Redis: D1 single-user + D16 SQLite. Adding Redis violates
the "zero external runtime deps" principle baked into V1. The cookie carries the
signed teacher_id; Backend reads it on every request via FastAPI dependency.

Cookie contents intentionally minimal:
- `teacher_id` (UUID string) — 36 chars
- `iat` (issued-at unix ts) — 10 chars

Total signed payload < 100 bytes. Cookie size budget is fine.

Security:
- HttpOnly + Secure + SameSite=Lax (per ARCH-001 §8.1)
- 30-day TTL with explicit `iat`-based expiry check (defence in depth — even if the
  signer's `max_age` is bypassed, our check still rejects stale cookies)
- Signed with `SESSION_SECRET_KEY` — separate from data-at-rest encryption keys
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Final

from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer
from itsdangerous.exc import BadData

from app.config import get_settings

COOKIE_NAME: Final[str] = "tc_session"
SESSION_TTL_SECONDS: Final[int] = 60 * 60 * 24 * 30   # 30 days
OAUTH_STATE_COOKIE: Final[str] = "tc_oauth_state"
OAUTH_STATE_TTL: Final[int] = 60 * 10                  # 10 min — OAuth code exchange is fast


@dataclass(frozen=True)
class SessionPayload:
    teacher_id: str
    iat: int

    def is_expired(self, *, ttl_seconds: int = SESSION_TTL_SECONDS) -> bool:
        return (time.time() - self.iat) > ttl_seconds


def _serializer(salt: str) -> URLSafeTimedSerializer:
    """Create a serializer scoped by purpose-string salt.

    Using distinct salts for distinct purposes (`session` vs `oauth-state`) means
    a session cookie can never be replayed as a state token and vice versa, even
    if the secret is the same. This is the standard pattern in itsdangerous docs.
    """
    secret = get_settings().session_secret_key.get_secret_value()
    return URLSafeTimedSerializer(secret, salt=salt)


def issue_session_cookie(teacher_id: str) -> str:
    """Sign and serialise a session for the given teacher."""
    payload = {"teacher_id": teacher_id, "iat": int(time.time())}
    return _serializer("session").dumps(payload)


def parse_session_cookie(raw: str) -> SessionPayload | None:
    """Verify signature + TTL. Returns None on any failure (caller treats as anonymous)."""
    try:
        data = _serializer("session").loads(raw, max_age=SESSION_TTL_SECONDS)
    except (BadSignature, SignatureExpired, BadData):
        return None

    if not isinstance(data, dict) or "teacher_id" not in data or "iat" not in data:
        return None

    return SessionPayload(teacher_id=str(data["teacher_id"]), iat=int(data["iat"]))


def issue_oauth_state(return_to: str = "/") -> str:
    """OAuth `state` token — random + signed.

    `return_to` lets the callback redirect to a stored URL (e.g., the page the user
    tried to access pre-login). itsdangerous's signed payload doubles as both the
    CSRF state and the return-target store.
    """
    payload = {"return_to": return_to, "iat": int(time.time())}
    return _serializer("oauth-state").dumps(payload)


def parse_oauth_state(raw: str) -> dict | None:
    try:
        data = _serializer("oauth-state").loads(raw, max_age=OAUTH_STATE_TTL)
    except (BadSignature, SignatureExpired, BadData):
        return None
    return data if isinstance(data, dict) else None

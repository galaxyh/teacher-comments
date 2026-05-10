"""AuthService — OAuth orchestration + teacher persistence.

Per DESIGN-001 §4.3 contract; V1 single-user enforcement (D1 / A6) lives here.

Single-user enforcement strategy:
- The teacher table can have **at most one row** in V1 (CHECK enforced at app layer
  rather than DB to keep schema V2-compatible)
- `complete_oauth` checks: if a row exists with a different `google_sub` → reject

This is intentionally over-strict for V1: the operator is the only user. If they
log in with a different Google account, that's almost certainly a misconfiguration
(wrong account selected), not a feature request.
"""

from __future__ import annotations

import logging

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from google.oauth2.credentials import Credentials

from app.adapters.google_oauth import (
    GOOGLE_TOKEN_URL,
    SCOPES,
    GoogleOAuthAdapter,
    TokenBundle,
)
from app.config import Settings
from app.core.exceptions import AuthError
from app.db.session import get_sessionmaker
from app.db.write_queue import DBWriteQueue
from app.models import Teacher
from app.models._helpers import gen_uuid, utcnow_iso
from app.services.audit_logger import AuditLogger
from app.services.encryption import get_oauth_cipher

logger = logging.getLogger(__name__)


class SingleUserViolationError(AuthError):
    """A teacher row with a different google_sub already exists.

    UI surfaces this as "this instance is already bound to <other_email>".
    """


class AuthService:
    def __init__(
        self,
        settings: Settings,
        db_write_queue: DBWriteQueue,
        audit: AuditLogger,
        oauth_adapter: GoogleOAuthAdapter | None = None,
    ) -> None:
        self._settings = settings
        self._queue = db_write_queue
        self._audit = audit
        self._oauth = oauth_adapter or GoogleOAuthAdapter(
            client_id=settings.google_client_id.get_secret_value(),
            client_secret=settings.google_client_secret.get_secret_value(),
        )

    @property
    def callback_uri(self) -> str:
        return f"{str(self._settings.public_base_url).rstrip('/')}/auth/callback"

    def begin_oauth(self, *, state: str) -> str:
        """Build the Google authorize URL. Caller persists `state` in cookie."""
        return self._oauth.build_authorize_url(
            redirect_uri=self.callback_uri,
            state=state,
        )

    async def complete_oauth(self, *, code: str) -> Teacher:
        """Exchange code, upsert teacher, log oauth_login. Returns Teacher row."""
        try:
            bundle = await self._oauth.exchange_code(
                code=code, redirect_uri=self.callback_uri
            )
        except Exception as exc:  # transport / 4xx from Google
            logger.exception("OAuth code exchange failed")
            raise AuthError(
                "Google OAuth code exchange failed",
                context={"reason": str(exc)},
            ) from exc

        if not bundle.refresh_token:
            # First-time consent always returns refresh_token. If it's missing,
            # the adapter's `prompt=consent` invariant was violated (e.g., user
            # somehow re-authorised without prompt) — we cannot proceed without it.
            raise AuthError(
                "Google did not return a refresh_token. "
                "Try revoking access at https://myaccount.google.com/permissions and re-login."
            )

        userinfo = await self._oauth.fetch_userinfo(access_token=bundle.access_token)

        teacher = await self._upsert_teacher(bundle=bundle, sub=userinfo.sub, email=userinfo.email)

        await self._audit.log_event(
            "oauth_login",
            teacher_id=teacher.id,
            payload={"email": userinfo.email, "email_verified": userinfo.email_verified},
        )
        return teacher

    async def logout(self, *, teacher_id: str) -> None:
        """Local logout — clear refresh_token from DB. Best-effort revoke on Google."""
        async with get_sessionmaker()() as session:
            row = await session.get(Teacher, teacher_id)
            if row is None:
                return
            encrypted_token = row.oauth_refresh_token_encrypted

        # Best-effort revoke. Failure is non-fatal — local clear already happened in DB write.
        if encrypted_token:
            try:
                refresh_token = get_oauth_cipher().decrypt_str(encrypted_token)
                await self._oauth.revoke_token(refresh_token=refresh_token)
            except Exception:  # noqa: BLE001 — revocation is fire-and-forget
                logger.warning("Google revoke failed; local logout still proceeds")

        async def clear_token(session: AsyncSession) -> None:
            row = await session.get(Teacher, teacher_id)
            if row is not None:
                row.oauth_refresh_token_encrypted = None
        await self._queue.submit(clear_token)

        await self._audit.log_event("oauth_logout", teacher_id=teacher_id)

    async def attest(self, *, teacher_id: str, version: str = "v1") -> Teacher:
        """Record onboarding consent attestation (D17 / PRD §3.2 Flow A step 2).

        UPDATE teacher.consent_attestation_at + version. Logs `attestation_signed`
        for audit (legal-grade trail).
        """
        async def update(session: AsyncSession) -> Teacher:
            row = await session.get(Teacher, teacher_id)
            if row is None:
                raise ValueError(f"No teacher with id={teacher_id!r}")
            row.consent_attestation_at = utcnow_iso()
            row.consent_attestation_version = version
            return row

        teacher = await self._queue.submit(update)
        await self._audit.log_event(
            "attestation_signed",
            teacher_id=teacher_id,
            payload={"version": version},
        )
        return teacher

    async def get_teacher(self, *, teacher_id: str) -> Teacher | None:
        async with get_sessionmaker()() as session:
            return await session.get(Teacher, teacher_id)

    async def get_credentials(self, *, teacher_id: str) -> Credentials:
        """Return google.oauth2.credentials.Credentials for Drive calls.

        The Credentials object handles lazy refresh internally — when the access
        token expires, the next API call's underlying httplib2 transport refreshes
        it via the refresh_token + token_url. We don't need to call .refresh()
        manually unless we want a fresh token preemptively.

        Raises:
            OAuthRevokedError: teacher row has no refresh_token (logged out or
              never logged in). UI must redirect to /auth/login.
        """
        teacher = await self.get_teacher(teacher_id=teacher_id)
        if teacher is None or not teacher.oauth_refresh_token_encrypted:
            from app.core.exceptions import OAuthRevokedError

            raise OAuthRevokedError(
                "No refresh token on file — re-authentication required",
                context={"teacher_id": teacher_id},
            )

        refresh_token = get_oauth_cipher().decrypt_str(
            teacher.oauth_refresh_token_encrypted
        )
        return Credentials(
            token=None,  # forces refresh on first use
            refresh_token=refresh_token,
            token_uri=GOOGLE_TOKEN_URL,
            client_id=self._settings.google_client_id.get_secret_value(),
            client_secret=self._settings.google_client_secret.get_secret_value(),
            scopes=list(SCOPES),
        )

    # ── internals ──────────────────────────────────────────────────

    async def _upsert_teacher(
        self, *, bundle: TokenBundle, sub: str, email: str
    ) -> Teacher:
        """V1 single-user enforcement + UPSERT.

        Two cases:
        - No teacher row → INSERT
        - Teacher row exists with same `google_sub` → UPDATE (refresh refresh_token)
        - Teacher row exists with different `google_sub` → reject
        """
        encrypted = get_oauth_cipher().encrypt_str(bundle.refresh_token)

        async with get_sessionmaker()() as session:
            existing = (await session.execute(select(Teacher))).scalars().all()

        if len(existing) > 1:
            # Should be impossible per V1 invariant, but guard against schema drift.
            raise SingleUserViolationError(
                "Multiple teacher rows present — this DB is corrupt for V1 single-user mode",
                context={"row_count": len(existing)},
            )

        if existing and existing[0].google_sub != sub:
            raise SingleUserViolationError(
                "This instance is already bound to a different Google account",
                context={"existing_email": existing[0].email, "attempted_email": email},
            )

        if existing:
            teacher_id = existing[0].id

            async def update(session: AsyncSession) -> Teacher:
                row = await session.get(Teacher, teacher_id)
                assert row is not None
                row.oauth_refresh_token_encrypted = encrypted
                row.email = email
                row.last_active_at = utcnow_iso()
                return row

            return await self._queue.submit(update)

        # New teacher — INSERT
        new_id = gen_uuid()
        new_email = email
        new_sub = sub

        async def insert(session: AsyncSession) -> Teacher:
            row = Teacher(
                id=new_id,
                google_sub=new_sub,
                email=new_email,
                oauth_refresh_token_encrypted=encrypted,
                last_active_at=utcnow_iso(),
            )
            session.add(row)
            await session.flush()
            return row

        return await self._queue.submit(insert)



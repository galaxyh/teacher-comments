"""Google OAuth 2.0 adapter — wraps authlib's AsyncOAuth2Client.

Per ARCH-001 §2.1 and lessons-learned/framework-gotcha.md "Lazy Imports Hide
Missing Dependencies": authlib + httpx are eagerly imported here so a missing
dep surfaces at app boot, not at first /auth/login call.

Endpoints are constants by default but overridable via env (used in tests to
point at a stub server instead of real Google).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Final

import httpx
from authlib.integrations.httpx_client import AsyncOAuth2Client

# OIDC discovery endpoints (rarely change, but allow override for tests)
GOOGLE_AUTHORIZE_URL: Final[str] = "https://accounts.google.com/o/oauth2/v2/auth"
GOOGLE_TOKEN_URL: Final[str] = "https://oauth2.googleapis.com/token"
GOOGLE_REVOKE_URL: Final[str] = "https://oauth2.googleapis.com/revoke"
GOOGLE_USERINFO_URL: Final[str] = "https://openidconnect.googleapis.com/v1/userinfo"

# Scopes per D5 (Drive read-only) + OIDC standard for identity
SCOPES: Final[tuple[str, ...]] = (
    "openid",
    "email",
    "profile",
    "https://www.googleapis.com/auth/drive.readonly",
)


@dataclass
class TokenBundle:
    """Result of code exchange — what we persist + use immediately."""

    access_token: str
    refresh_token: str
    expires_in: int
    id_token: str | None  # OIDC id_token; we use it to extract `sub` + `email`


@dataclass
class GoogleUserInfo:
    sub: str         # Stable Google account identifier — primary key for teacher.google_sub
    email: str
    email_verified: bool


class GoogleOAuthAdapter:
    """Thin wrapper over authlib + httpx.

    Configurable URLs allow:
    - Real Google in prod
    - Stub server (run by pytest) for integration tests
    """

    def __init__(
        self,
        client_id: str,
        client_secret: str,
        *,
        authorize_url: str = GOOGLE_AUTHORIZE_URL,
        token_url: str = GOOGLE_TOKEN_URL,
        revoke_url: str = GOOGLE_REVOKE_URL,
        userinfo_url: str = GOOGLE_USERINFO_URL,
    ) -> None:
        self._client_id = client_id
        self._client_secret = client_secret
        self._authorize_url = authorize_url
        self._token_url = token_url
        self._revoke_url = revoke_url
        self._userinfo_url = userinfo_url

    def build_authorize_url(self, *, redirect_uri: str, state: str) -> str:
        """Construct the Google authorize URL with state + offline access.

        `access_type=offline` + `prompt=consent` together guarantee a refresh_token
        is issued (Google only issues one on the first consent or when forced).
        Without this, V1 cannot refresh access tokens unattended — a ten-second
        misconfiguration that costs days of debugging if missed.
        """
        client = AsyncOAuth2Client(
            self._client_id,
            self._client_secret,
            scope=" ".join(SCOPES),
            redirect_uri=redirect_uri,
        )
        url, _state = client.create_authorization_url(
            self._authorize_url,
            state=state,
            access_type="offline",
            prompt="consent",
        )
        return url

    async def exchange_code(
        self, *, code: str, redirect_uri: str
    ) -> TokenBundle:
        """Exchange authorization code for tokens.

        Raises httpx errors on transport failure; authlib raises on token-endpoint
        4xx/5xx. Caller (AuthService) maps these to AuthError.
        """
        async with AsyncOAuth2Client(
            self._client_id,
            self._client_secret,
            redirect_uri=redirect_uri,
        ) as client:
            token = await client.fetch_token(
                self._token_url,
                code=code,
                grant_type="authorization_code",
            )

        return TokenBundle(
            access_token=str(token["access_token"]),
            refresh_token=str(token.get("refresh_token", "")),
            expires_in=int(token.get("expires_in", 3600)),
            id_token=token.get("id_token"),
        )

    async def fetch_userinfo(self, *, access_token: str) -> GoogleUserInfo:
        """OIDC userinfo. Returns sub + email even when id_token verification is skipped."""
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(
                self._userinfo_url,
                headers={"Authorization": f"Bearer {access_token}"},
            )
            resp.raise_for_status()
            data = resp.json()

        return GoogleUserInfo(
            sub=str(data["sub"]),
            email=str(data["email"]),
            email_verified=bool(data.get("email_verified", False)),
        )

    async def revoke_token(self, *, refresh_token: str) -> None:
        """Best-effort revocation. 200 = revoked; 400 often means already revoked.

        We swallow non-200 because the local logout (clearing teacher row) is
        what actually matters; revoking on Google is courtesy.
        """
        async with httpx.AsyncClient(timeout=10.0) as client:
            await client.post(self._revoke_url, data={"token": refresh_token})

"""Integration test — OAuth flow with a fake GoogleOAuthAdapter.

The real adapter calls accounts.google.com; tests substitute a fake that returns
canned tokens + userinfo. Everything else (session cookies, single-user check,
DB writes via the queue) runs as in production.
"""

from __future__ import annotations

import subprocess
from dataclasses import dataclass
from typing import Any

import pytest
from fastapi.testclient import TestClient

from app.adapters.google_oauth import GoogleUserInfo, TokenBundle


class FakeGoogleAdapter:
    """Stub that records calls and returns canned data.

    Mirrors GoogleOAuthAdapter's public surface; AuthService doesn't care which it gets.
    """

    def __init__(
        self,
        *,
        sub: str = "google-sub-12345",
        email: str = "teacher@example.com",
        refresh_token: str = "fake-refresh-token",
    ) -> None:
        self.sub = sub
        self.email = email
        self.refresh_token = refresh_token
        self.exchange_calls: list[dict[str, Any]] = []
        self.revoke_calls: list[dict[str, Any]] = []

    def build_authorize_url(self, *, redirect_uri: str, state: str) -> str:
        return f"https://fake-google.test/authorize?redirect_uri={redirect_uri}&state={state}"

    async def exchange_code(self, *, code: str, redirect_uri: str) -> TokenBundle:
        self.exchange_calls.append({"code": code, "redirect_uri": redirect_uri})
        return TokenBundle(
            access_token="fake-access",
            refresh_token=self.refresh_token,
            expires_in=3600,
            id_token=None,
        )

    async def fetch_userinfo(self, *, access_token: str) -> GoogleUserInfo:
        return GoogleUserInfo(sub=self.sub, email=self.email, email_verified=True)

    async def revoke_token(self, *, refresh_token: str) -> None:
        self.revoke_calls.append({"refresh_token": refresh_token})


@dataclass
class AuthHarness:
    client: TestClient
    fake: FakeGoogleAdapter


@pytest.fixture
def harness(isolated_env) -> AuthHarness:
    """Build an app with the fake adapter wired in via dependency override."""
    subprocess.run(
        ["uv", "run", "alembic", "upgrade", "head"],
        check=True,
        cwd="/home/steven/projects/teacher-comments/backend",
        capture_output=True,
    )

    from app.config import get_settings
    from app.db.write_queue import get_write_queue
    from app.main import create_app
    from app.routers.auth import get_auth_service
    from app.services.audit_logger import AuditLogger
    from app.services.auth_service import AuthService

    fake = FakeGoogleAdapter()

    def _override() -> AuthService:
        settings = get_settings()
        queue = get_write_queue()
        return AuthService(
            settings=settings,
            db_write_queue=queue,
            audit=AuditLogger(queue),
            oauth_adapter=fake,  # type: ignore[arg-type]
        )

    app = create_app()
    app.dependency_overrides[get_auth_service] = _override

    with TestClient(app) as client:
        yield AuthHarness(client=client, fake=fake)


# ── Tests ──────────────────────────────────────────────────────────


def test_login_redirects_to_authorize_url(harness: AuthHarness) -> None:
    r = harness.client.get("/auth/login", follow_redirects=False)
    assert r.status_code == 302
    assert r.headers["location"].startswith("https://fake-google.test/authorize")
    # State cookie set with proper attributes
    cookie = r.cookies.get("tc_oauth_state")
    assert cookie is not None


def test_callback_happy_path(harness: AuthHarness) -> None:
    # Step 1: login → state cookie issued
    login_r = harness.client.get("/auth/login", follow_redirects=False)
    state = login_r.cookies["tc_oauth_state"]

    # Step 2: callback with the same state → session set, redirect to /
    cb_r = harness.client.get(
        "/auth/callback",
        params={"code": "fake-code", "state": state},
        cookies={"tc_oauth_state": state},
        follow_redirects=False,
    )
    assert cb_r.status_code == 302
    assert cb_r.headers["location"] == "/"
    assert cb_r.cookies.get("tc_session") is not None

    # Step 3: /me works with the session cookie
    me_r = harness.client.get("/me", cookies={"tc_session": cb_r.cookies["tc_session"]})
    assert me_r.status_code == 200
    body = me_r.json()
    assert body["email"] == "teacher@example.com"
    assert body["has_drive_root"] is False
    assert body["has_attested"] is False


def test_callback_csrf_mismatch_rejected(harness: AuthHarness) -> None:
    """If the state cookie doesn't match the URL's `state` param → 400."""
    login_r = harness.client.get("/auth/login", follow_redirects=False)
    real_state = login_r.cookies["tc_oauth_state"]

    cb_r = harness.client.get(
        "/auth/callback",
        params={"code": "fake-code", "state": "tampered-state"},
        cookies={"tc_oauth_state": real_state},
        follow_redirects=False,
    )
    assert cb_r.status_code == 400
    assert cb_r.json()["detail"]["reason"] == "state_mismatch"


def test_single_user_violation_blocks_second_account(harness: AuthHarness) -> None:
    """V1 single-user enforcement: second login with different google_sub → 409."""
    # First login
    login_r = harness.client.get("/auth/login", follow_redirects=False)
    state = login_r.cookies["tc_oauth_state"]
    cb_r = harness.client.get(
        "/auth/callback",
        params={"code": "fake-code", "state": state},
        cookies={"tc_oauth_state": state},
        follow_redirects=False,
    )
    assert cb_r.status_code == 302  # success

    # Second login from a different account — change the fake adapter's sub
    harness.fake.sub = "different-google-sub"
    harness.fake.email = "intruder@example.com"

    login2 = harness.client.get("/auth/login", follow_redirects=False)
    state2 = login2.cookies["tc_oauth_state"]
    cb2 = harness.client.get(
        "/auth/callback",
        params={"code": "fake-code", "state": state2},
        cookies={"tc_oauth_state": state2},
        follow_redirects=False,
    )
    assert cb2.status_code == 409
    assert cb2.json()["detail"]["reason"] == "single_user_violation"


def test_me_anonymous_returns_401(harness: AuthHarness) -> None:
    r = harness.client.get("/me")
    assert r.status_code == 401
    assert r.json()["detail"]["reason"] == "no_session"

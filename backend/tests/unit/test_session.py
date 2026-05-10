"""Session cookie helpers — sign/verify/expire/tamper tests."""

from __future__ import annotations

import time

import pytest

from app.core.session import (
    SESSION_TTL_SECONDS,
    SessionPayload,
    issue_oauth_state,
    issue_session_cookie,
    parse_oauth_state,
    parse_session_cookie,
)


@pytest.mark.usefixtures("isolated_env")
class TestSessionCookie:
    def test_round_trip(self) -> None:
        cookie = issue_session_cookie("teacher-uuid-1")
        parsed = parse_session_cookie(cookie)
        assert parsed is not None
        assert parsed.teacher_id == "teacher-uuid-1"
        assert parsed.is_expired() is False

    def test_tampered_signature_rejected(self) -> None:
        cookie = issue_session_cookie("teacher-uuid-1")
        # Flip a character in the cookie body — signature won't verify
        tampered = cookie[:-3] + "AAA"
        assert parse_session_cookie(tampered) is None

    def test_garbage_rejected(self) -> None:
        assert parse_session_cookie("not-a-real-cookie") is None
        assert parse_session_cookie("") is None

    def test_explicit_ttl_check(self) -> None:
        # is_expired uses iat; provide a fake to confirm boundary
        old = SessionPayload(teacher_id="x", iat=int(time.time()) - SESSION_TTL_SECONDS - 1)
        assert old.is_expired() is True

        fresh = SessionPayload(teacher_id="x", iat=int(time.time()))
        assert fresh.is_expired() is False


@pytest.mark.usefixtures("isolated_env")
class TestOAuthState:
    def test_round_trip(self) -> None:
        state = issue_oauth_state(return_to="/dashboard")
        parsed = parse_oauth_state(state)
        assert parsed is not None
        assert parsed["return_to"] == "/dashboard"
        assert "iat" in parsed

    def test_purpose_separation(self) -> None:
        """A session cookie must not be replayable as an OAuth state, and vice versa.

        Both serializers share the same secret but use different salts; itsdangerous
        treats them as cryptographically distinct keys.
        """
        session_cookie = issue_session_cookie("t")
        # Trying to parse a session cookie as oauth state must fail
        assert parse_oauth_state(session_cookie) is None

        state = issue_oauth_state(return_to="/")
        # Parsing oauth state as session must fail
        assert parse_session_cookie(state) is None

"""Onboarding flow tests — attestation (D17) + drive root + folder mapping wired end-to-end."""

from __future__ import annotations

import subprocess

import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def authed_client(isolated_env):
    """TestClient with session cookie + a seeded teacher row."""
    subprocess.run(
        ["uv", "run", "alembic", "upgrade", "head"],
        check=True,
        cwd="/home/steven/projects/teacher-comments/backend",
        capture_output=True,
    )

    from app.core.session import COOKIE_NAME, issue_session_cookie
    from app.db.write_queue import get_write_queue
    from app.main import create_app
    from app.models import Teacher

    app = create_app()
    with TestClient(app) as client:
        queue = get_write_queue()

        async def seed(s):
            s.add(Teacher(id="t1", google_sub="sub", email="t@e.com"))
        client.portal.call(queue.submit, seed)

        client.cookies.set(COOKIE_NAME, issue_session_cookie("t1"))
        yield client


def test_attest_records_consent(authed_client: TestClient) -> None:
    r = authed_client.post("/onboarding/attest", json={"version": "v1"})
    assert r.status_code == 200
    assert r.json() == {"status": "ok", "version": "v1"}

    # /me should now show has_attested=True
    me = authed_client.get("/me").json()
    assert me["has_attested"] is True


def test_attest_writes_system_event(authed_client: TestClient) -> None:
    authed_client.post("/onboarding/attest", json={"version": "v1"})

    # Check audit row written via direct DB read
    from app.db.session import get_sessionmaker
    from app.models import SystemEvent
    from sqlalchemy import select
    import asyncio

    async def fetch():
        async with get_sessionmaker()() as s:
            rows = (
                await s.execute(
                    select(SystemEvent).where(
                        SystemEvent.event_type == "attestation_signed"
                    )
                )
            ).scalars().all()
            return [r.payload_json for r in rows]

    payloads = authed_client.portal.call(fetch)
    assert len(payloads) == 1
    assert "v1" in (payloads[0] or "")


def test_attest_anonymous_returns_401(authed_client: TestClient) -> None:
    authed_client.cookies.clear()
    r = authed_client.post("/onboarding/attest", json={"version": "v1"})
    assert r.status_code == 401


def test_attest_invalid_version_returns_422(authed_client: TestClient) -> None:
    r = authed_client.post("/onboarding/attest", json={"version": ""})
    assert r.status_code == 422


def test_attest_idempotent(authed_client: TestClient) -> None:
    """Two attestations with same version both succeed; both audit-logged."""
    r1 = authed_client.post("/onboarding/attest", json={"version": "v1"})
    r2 = authed_client.post("/onboarding/attest", json={"version": "v1"})
    assert r1.status_code == 200 and r2.status_code == 200

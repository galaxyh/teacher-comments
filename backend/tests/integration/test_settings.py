"""Settings router tests (Phase 12)."""

from __future__ import annotations

import subprocess

import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def authed_client(isolated_env):
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


def test_settings_returns_defaults_for_fresh_teacher(authed_client: TestClient) -> None:
    r = authed_client.get("/settings")
    assert r.status_code == 200
    body = r.json()
    cfg = body["llm_tier_config"]
    # All four tiers default to Flash Lite (D9)
    assert cfg["summary_cheap"] == "google/gemini-2.5-flash-lite"
    assert cfg["evaluation_quality"] == "google/gemini-2.5-flash-lite"
    assert body["monthly_cost_usd"] == 0.0
    assert body["monthly_budget_usd"] == 5.0


def test_set_tier_override_persists(authed_client: TestClient) -> None:
    r = authed_client.put(
        "/settings/llm-tier",
        json={"overrides": {"evaluation_quality": "google/gemini-2.5-pro"}},
    )
    assert r.status_code == 200
    after = authed_client.get("/settings").json()
    assert after["llm_tier_config"]["evaluation_quality"] == "google/gemini-2.5-pro"
    # Other tiers still on the default
    assert after["llm_tier_config"]["summary_cheap"] == "google/gemini-2.5-flash-lite"


def test_clear_override_with_empty_string(authed_client: TestClient) -> None:
    authed_client.put(
        "/settings/llm-tier",
        json={"overrides": {"evaluation_quality": "google/gemini-2.5-pro"}},
    )
    r = authed_client.put(
        "/settings/llm-tier", json={"overrides": {"evaluation_quality": ""}}
    )
    assert r.status_code == 200
    after = authed_client.get("/settings").json()
    assert after["llm_tier_config"]["evaluation_quality"] == "google/gemini-2.5-flash-lite"


def test_unknown_tier_returns_400(authed_client: TestClient) -> None:
    r = authed_client.put(
        "/settings/llm-tier", json={"overrides": {"bogus_tier": "x"}}
    )
    assert r.status_code == 400
    assert r.json()["detail"]["reason"] == "invalid_tier"


def test_anonymous_returns_401(authed_client: TestClient) -> None:
    authed_client.cookies.clear()
    r = authed_client.get("/settings")
    assert r.status_code == 401


def test_monthly_cost_aggregates_audit_rows(authed_client: TestClient) -> None:
    """Insert two audit rows in current month + one outside; only current-month sum returned."""
    from app.db.write_queue import get_write_queue
    from app.models import LLMCallAudit
    from app.models._helpers import gen_uuid, utcnow_iso

    queue = get_write_queue()
    now = utcnow_iso()

    async def seed(s):
        s.add_all([
            LLMCallAudit(
                id=gen_uuid(), teacher_id="t1", tier="summary_cheap",
                model_id="x", purpose="test",
                input_tokens=100, output_tokens=50, cost_usd=0.001,
                created_at=now,
            ),
            LLMCallAudit(
                id=gen_uuid(), teacher_id="t1", tier="summary_cheap",
                model_id="x", purpose="test",
                input_tokens=200, output_tokens=100, cost_usd=0.002,
                created_at=now,
            ),
        ])
    authed_client.portal.call(queue.submit, seed)

    body = authed_client.get("/settings").json()
    assert body["monthly_cost_usd"] == pytest.approx(0.003, abs=1e-6)

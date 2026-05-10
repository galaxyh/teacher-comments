"""PII Min UI tests (D13)."""

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
    from app.services.pii_anonymizer import PIIAnonymizer

    app = create_app()
    with TestClient(app) as client:
        queue = get_write_queue()

        async def seed(s):
            s.add(Teacher(id="t1", google_sub="sub", email="t@e.com"))
        client.portal.call(queue.submit, seed)

        # Seed two real mappings via anonymize() so the lookup_hash flow is exercised
        async def seed_mappings():
            anonymizer = PIIAnonymizer(db_write_queue=queue)
            await anonymizer.anonymize(
                text="Phone 0912345678 email t@x.com", teacher_id="t1"
            )
        client.portal.call(seed_mappings)

        client.cookies.set(COOKIE_NAME, issue_session_cookie("t1"))
        yield client


def test_list_mappings_returns_seeded_rows(authed_client: TestClient) -> None:
    r = authed_client.get("/pii/mappings")
    assert r.status_code == 200
    rows = r.json()
    assert len(rows) == 2
    pseudonyms = {row["pseudonym"] for row in rows}
    assert "PH001" in pseudonyms
    assert "EM001" in pseudonyms
    # Original values are returned for display (decrypted)
    originals = {row["original_value"] for row in rows}
    assert "0912345678" in originals
    assert "t@x.com" in originals


def test_update_display_name(authed_client: TestClient) -> None:
    r = authed_client.put(
        "/pii/mappings/PH001/display-name",
        json={"display_name": "家長電話"},
    )
    assert r.status_code == 200

    rows = authed_client.get("/pii/mappings").json()
    ph = next(r for r in rows if r["pseudonym"] == "PH001")
    assert ph["display_name"] == "家長電話"


def test_clear_display_name(authed_client: TestClient) -> None:
    authed_client.put("/pii/mappings/PH001/display-name", json={"display_name": "X"})
    r = authed_client.put("/pii/mappings/PH001/display-name", json={"display_name": ""})
    assert r.status_code == 200
    rows = authed_client.get("/pii/mappings").json()
    ph = next(r for r in rows if r["pseudonym"] == "PH001")
    assert ph["display_name"] is None


def test_unknown_pseudonym_returns_404(authed_client: TestClient) -> None:
    r = authed_client.put(
        "/pii/mappings/PH999/display-name", json={"display_name": "X"}
    )
    assert r.status_code == 404
    assert r.json()["detail"]["reason"] == "pseudonym_not_found"


def test_add_manual_mapping(authed_client: TestClient) -> None:
    r = authed_client.post(
        "/pii/mappings",
        json={
            "pseudonym": "PH001",
            "original_value": "+886912345678",
            "pii_type": "phone",
        },
    )
    assert r.status_code == 200
    body = r.json()
    assert body["source"] == "manual"
    assert body["pseudonym"] == "PH001"


def test_add_manual_mapping_for_unknown_pseudonym_returns_400(
    authed_client: TestClient,
) -> None:
    r = authed_client.post(
        "/pii/mappings",
        json={"pseudonym": "PH999", "original_value": "x", "pii_type": "phone"},
    )
    assert r.status_code == 400
    assert r.json()["detail"]["reason"] == "invalid_pseudonym"


def test_anonymous_returns_401(authed_client: TestClient) -> None:
    authed_client.cookies.clear()
    r = authed_client.get("/pii/mappings")
    assert r.status_code == 401

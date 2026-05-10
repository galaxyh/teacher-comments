"""Integration test — boot the full app via TestClient and hit health endpoints."""

from __future__ import annotations

import subprocess

import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def client(isolated_env):
    # Migrate test DB before app boot
    subprocess.run(
        ["uv", "run", "alembic", "upgrade", "head"],
        check=True,
        cwd="/home/steven/projects/teacher-comments/backend",
        capture_output=True,
    )
    # Importing here so settings cache is fresh per `isolated_env`
    from app.main import create_app

    app = create_app()
    with TestClient(app) as c:
        yield c


def test_healthz(client: TestClient) -> None:
    r = client.get("/healthz")
    assert r.status_code == 200
    assert r.json() == {"status": "ok"}


def test_readyz(client: TestClient) -> None:
    r = client.get("/readyz")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "ok"
    assert body["checks"]["db"] is True
    assert body["checks"]["write_queue_depth"] == 0

"""Tests for the FastAPI HTTP layer."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from jobpilot.api.app import create_app


@pytest.fixture
def client(settings):
    app = create_app(settings=settings)
    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture
def payload(candidate):
    return {
        "candidate": candidate.model_dump(mode="json"),
        "goal": "Senior Python engineer, remote",
    }


def test_health(client):
    resp = client.get("/health")
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "ok"
    assert body["llm_provider"] == "anthropic"
    assert body["llm_enabled"] is False  # no key in test settings
    assert body["browser_mode"] == "simulated"


def test_root(client):
    assert client.get("/").json()["name"] == "JobPilot"


def test_start_get_and_approve_flow(client, payload):
    # Start
    resp = client.post("/applications", json=payload)
    assert resp.status_code == 201
    run = resp.json()
    assert run["awaiting_approval"] is True
    assert run["status"] == "awaiting_approval"
    assert run["job"]["title"]
    assert run["resume"]["markdown"]
    assert run["cover_letter_text"]
    thread_id = run["thread_id"]

    # Get
    got = client.get(f"/applications/{thread_id}")
    assert got.status_code == 200
    assert got.json()["thread_id"] == thread_id

    # Approve
    approved = client.post(f"/applications/{thread_id}/approve", json={"approved": True})
    assert approved.status_code == 200
    body = approved.json()
    assert body["status"] == "completed"
    assert body["application"]["submitted"] is True

    # Approving again conflicts.
    again = client.post(f"/applications/{thread_id}/approve", json={"approved": True})
    assert again.status_code == 409


def test_reject_flow(client, payload):
    thread_id = client.post("/applications", json=payload).json()["thread_id"]
    resp = client.post(
        f"/applications/{thread_id}/approve", json={"approved": False, "notes": "later"}
    )
    assert resp.status_code == 200
    assert resp.json()["status"] == "rejected"


def test_get_unknown_returns_404(client):
    assert client.get("/applications/ghost").status_code == 404


def test_approve_unknown_returns_404(client):
    resp = client.post("/applications/ghost/approve", json={"approved": True})
    assert resp.status_code == 404

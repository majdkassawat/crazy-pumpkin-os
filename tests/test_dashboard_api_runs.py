"""Tests for the /api/runs dashboard endpoint."""

from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone

import pytest
from fastapi import FastAPI
from starlette.testclient import TestClient

from crazypumpkin.dashboard import api as dashboard_api
from crazypumpkin.framework.models import RunRecord
from crazypumpkin.framework.store import Store


# ── Helpers ──


def _make_record(
    run_id: str,
    agent_name: str = "agent",
    status: str = "success",
    minutes_ago: int = 0,
) -> RunRecord:
    started = datetime.now(timezone.utc) - timedelta(minutes=minutes_ago)
    return RunRecord(
        run_id=run_id,
        agent_name=agent_name,
        started_at=started,
        status=status,
    )


def _run(coro):
    return asyncio.get_event_loop().run_until_complete(coro)


@pytest.fixture()
def store():
    return Store()


@pytest.fixture()
def client(store):
    """Create a TestClient wired to the dashboard router with *store*."""
    app = FastAPI()
    app.include_router(dashboard_api.router)
    dashboard_api.configure(store)
    yield TestClient(app)
    # Reset module-level store after test
    dashboard_api.configure(None)


# ── Basic response ──


def test_get_runs_returns_200_with_runs_array(client):
    resp = client.get("/api/runs")
    assert resp.status_code == 200
    body = resp.json()
    assert "runs" in body
    assert isinstance(body["runs"], list)


def test_empty_store_returns_empty_runs(client):
    body = client.get("/api/runs").json()
    assert body["runs"] == []
    assert body["total"] == 0


def test_response_includes_pagination_fields(client):
    body = client.get("/api/runs").json()
    assert "total" in body
    assert "limit" in body
    assert "offset" in body
    assert isinstance(body["total"], int)
    assert isinstance(body["limit"], int)
    assert isinstance(body["offset"], int)


# ── With data ──


def test_returns_stored_runs(client, store):
    _run(store.save_run_record(_make_record("r1", agent_name="Alpha")))
    _run(store.save_run_record(_make_record("r2", agent_name="Beta")))
    body = client.get("/api/runs").json()
    assert body["total"] == 2
    assert len(body["runs"]) == 2


def test_run_dict_has_expected_keys(client, store):
    _run(store.save_run_record(_make_record("r1")))
    run = client.get("/api/runs").json()["runs"][0]
    for key in ("run_id", "agent_name", "started_at", "status"):
        assert key in run


# ── Filtering by agent_name ──


def test_filter_by_agent_name(client, store):
    _run(store.save_run_record(_make_record("r1", agent_name="Alpha")))
    _run(store.save_run_record(_make_record("r2", agent_name="Beta")))
    _run(store.save_run_record(_make_record("r3", agent_name="Alpha")))

    body = client.get("/api/runs", params={"agent_name": "Alpha"}).json()
    assert body["total"] == 2
    assert len(body["runs"]) == 2
    assert all(r["agent_name"] == "Alpha" for r in body["runs"])


def test_filter_by_agent_name_no_match(client, store):
    _run(store.save_run_record(_make_record("r1", agent_name="Alpha")))
    body = client.get("/api/runs", params={"agent_name": "Nonexistent"}).json()
    assert body["total"] == 0
    assert body["runs"] == []


# ── Filtering by status ──


def test_filter_by_status(client, store):
    _run(store.save_run_record(_make_record("r1", status="success")))
    _run(store.save_run_record(_make_record("r2", status="failure")))
    _run(store.save_run_record(_make_record("r3", status="success")))

    body = client.get("/api/runs", params={"status": "failure"}).json()
    assert body["total"] == 1
    assert len(body["runs"]) == 1
    assert body["runs"][0]["status"] == "failure"


def test_filter_by_status_no_match(client, store):
    _run(store.save_run_record(_make_record("r1", status="success")))
    body = client.get("/api/runs", params={"status": "failure"}).json()
    assert body["total"] == 0
    assert body["runs"] == []


# ── Combined filters ──


def test_filter_by_agent_name_and_status(client, store):
    _run(store.save_run_record(_make_record("r1", agent_name="A", status="success")))
    _run(store.save_run_record(_make_record("r2", agent_name="A", status="failure")))
    _run(store.save_run_record(_make_record("r3", agent_name="B", status="success")))

    body = client.get("/api/runs", params={"agent_name": "A", "status": "success"}).json()
    assert body["total"] == 1
    assert body["runs"][0]["run_id"] == "r1"


# ── Pagination ──


def test_pagination_limit_and_offset(client, store):
    for i in range(10):
        _run(store.save_run_record(_make_record(f"r{i}", minutes_ago=9 - i)))

    body = client.get("/api/runs", params={"limit": 3, "offset": 0}).json()
    assert len(body["runs"]) == 3
    assert body["total"] == 10
    assert body["limit"] == 3
    assert body["offset"] == 0


def test_pagination_offset(client, store):
    for i in range(5):
        _run(store.save_run_record(_make_record(f"r{i}", minutes_ago=4 - i)))
    # Newest first: r4, r3, r2, r1, r0
    body = client.get("/api/runs", params={"limit": 2, "offset": 2}).json()
    assert len(body["runs"]) == 2
    assert body["total"] == 5


def test_pagination_offset_beyond_total(client, store):
    _run(store.save_run_record(_make_record("r1")))
    body = client.get("/api/runs", params={"offset": 100}).json()
    assert body["runs"] == []
    assert body["total"] == 1


def test_default_limit_is_50(client, store):
    for i in range(60):
        _run(store.save_run_record(_make_record(f"r{i}", minutes_ago=i)))
    body = client.get("/api/runs").json()
    assert len(body["runs"]) == 50
    assert body["total"] == 60
    assert body["limit"] == 50
    assert body["offset"] == 0

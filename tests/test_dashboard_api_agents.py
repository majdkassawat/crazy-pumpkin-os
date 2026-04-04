"""Tests for dashboard API endpoints: GET /api/agents/status and GET /api/cost/summary."""

from __future__ import annotations

import pytest
from aiohttp import web
from aiohttp.test_utils import TestClient, TestServer

from crazypumpkin.dashboard.api import setup_routes, get_agents_status, get_cost_summary
from crazypumpkin.framework.agent import BaseAgent
from crazypumpkin.framework.models import (
    Agent,
    AgentRole,
    AgentStatus,
    Task,
    TaskStatus,
)
from crazypumpkin.framework.registry import AgentRegistry
from crazypumpkin.framework.store import Store
from crazypumpkin.llm.base import CallCost, CostTracker, get_default_tracker


# ── Helpers ──

_TEST_TOKEN = "test-dashboard-token"


class _StubAgent(BaseAgent):
    def execute(self, task, context):
        raise NotImplementedError


def _agent(name: str, role: AgentRole = AgentRole.EXECUTION, status: AgentStatus = AgentStatus.ACTIVE) -> _StubAgent:
    return _StubAgent(agent=Agent(name=name, role=role, status=status))


def _task(tid: str, title: str, status: TaskStatus, assigned_to: str = "") -> Task:
    return Task(id=tid, title=title, status=status, assigned_to=assigned_to)


def _make_app(registry: AgentRegistry | None = None, store: Store | None = None) -> web.Application:
    app = web.Application()
    app["registry"] = registry or AgentRegistry()
    app["store"] = store or Store()
    app["dashboard_api_token"] = _TEST_TOKEN
    setup_routes(app)
    return app


def _auth_headers() -> dict[str, str]:
    return {"Authorization": f"Bearer {_TEST_TOKEN}"}


# ── Authentication ──


@pytest.mark.asyncio
async def test_agents_status_returns_401_without_token():
    app = _make_app()
    async with TestClient(TestServer(app)) as client:
        resp = await client.get("/api/agents/status")
        assert resp.status == 401


@pytest.mark.asyncio
async def test_cost_summary_returns_401_without_token():
    app = _make_app()
    async with TestClient(TestServer(app)) as client:
        resp = await client.get("/api/cost/summary")
        assert resp.status == 401


@pytest.mark.asyncio
async def test_agents_status_returns_401_with_bad_token():
    app = _make_app()
    async with TestClient(TestServer(app)) as client:
        resp = await client.get("/api/agents/status", headers={"Authorization": "Bearer wrong"})
        assert resp.status == 401


# ── GET /api/agents/status ──


@pytest.mark.asyncio
async def test_agents_status_returns_200():
    app = _make_app()
    async with TestClient(TestServer(app)) as client:
        resp = await client.get("/api/agents/status", headers=_auth_headers())
        assert resp.status == 200


@pytest.mark.asyncio
async def test_agents_status_returns_json_array():
    app = _make_app()
    async with TestClient(TestServer(app)) as client:
        resp = await client.get("/api/agents/status", headers=_auth_headers())
        data = await resp.json()
        assert isinstance(data, list)


@pytest.mark.asyncio
async def test_agents_status_empty_registry():
    app = _make_app()
    async with TestClient(TestServer(app)) as client:
        resp = await client.get("/api/agents/status", headers=_auth_headers())
        assert resp.status == 200
        data = await resp.json()
        assert data == []


@pytest.mark.asyncio
async def test_agents_status_contains_required_fields():
    registry = AgentRegistry()
    registry.register(_agent("alice"))
    app = _make_app(registry=registry)
    async with TestClient(TestServer(app)) as client:
        resp = await client.get("/api/agents/status", headers=_auth_headers())
        assert resp.status == 200
        data = await resp.json()
        assert len(data) == 1
        entry = data[0]
        for key in ("id", "name", "role", "status"):
            assert key in entry, f"Missing key: {key}"
            assert isinstance(entry[key], str)


@pytest.mark.asyncio
async def test_agents_status_includes_all_agents():
    registry = AgentRegistry()
    registry.register(_agent("alice"))
    registry.register(_agent("bob", role=AgentRole.STRATEGY))
    registry.register(_agent("charlie", status=AgentStatus.DISABLED))
    app = _make_app(registry=registry)
    async with TestClient(TestServer(app)) as client:
        resp = await client.get("/api/agents/status", headers=_auth_headers())
        data = await resp.json()
        names = {a["name"] for a in data}
        assert names == {"alice", "bob", "charlie"}


@pytest.mark.asyncio
async def test_agents_status_reflects_role_and_status():
    registry = AgentRegistry()
    registry.register(_agent("strategist", role=AgentRole.STRATEGY, status=AgentStatus.IDLE))
    app = _make_app(registry=registry)
    async with TestClient(TestServer(app)) as client:
        resp = await client.get("/api/agents/status", headers=_auth_headers())
        data = await resp.json()
        entry = data[0]
        assert entry["role"] == "strategy"
        assert entry["status"] == "idle"


@pytest.mark.asyncio
async def test_agents_status_has_last_active_and_current_task():
    registry = AgentRegistry()
    registry.register(_agent("alice"))
    app = _make_app(registry=registry)
    async with TestClient(TestServer(app)) as client:
        resp = await client.get("/api/agents/status", headers=_auth_headers())
        data = await resp.json()
        entry = data[0]
        assert "last_active" in entry
        assert "current_task" in entry


@pytest.mark.asyncio
async def test_agents_status_shows_current_task():
    registry = AgentRegistry()
    a = _agent("alice")
    registry.register(a)
    store = Store()
    store.add_task(_task("t1", "Build feature", TaskStatus.IN_PROGRESS, assigned_to=a.id))
    app = _make_app(registry=registry, store=store)
    async with TestClient(TestServer(app)) as client:
        resp = await client.get("/api/agents/status", headers=_auth_headers())
        data = await resp.json()
        entry = data[0]
        assert entry["current_task"] == "Build feature"


# ── GET /api/cost/summary ──


@pytest.mark.asyncio
async def test_cost_summary_returns_200():
    app = _make_app()
    async with TestClient(TestServer(app)) as client:
        resp = await client.get("/api/cost/summary", headers=_auth_headers())
        assert resp.status == 200


@pytest.mark.asyncio
async def test_cost_summary_contains_required_fields():
    app = _make_app()
    async with TestClient(TestServer(app)) as client:
        resp = await client.get("/api/cost/summary", headers=_auth_headers())
        data = await resp.json()
        assert "total_cost_usd" in data
        assert "by_model" in data
        assert "by_agent" in data
        assert isinstance(data["by_model"], dict)
        assert isinstance(data["by_agent"], dict)


@pytest.mark.asyncio
async def test_cost_summary_empty_state():
    # Reset the global tracker to ensure clean state
    tracker = get_default_tracker()
    tracker.reset()
    app = _make_app()
    async with TestClient(TestServer(app)) as client:
        resp = await client.get("/api/cost/summary", headers=_auth_headers())
        assert resp.status == 200
        data = await resp.json()
        assert data["total_cost_usd"] == 0.0
        assert data["by_model"] == {}
        assert data["by_agent"] == {}


@pytest.mark.asyncio
async def test_cost_summary_with_model_costs():
    tracker = get_default_tracker()
    tracker.reset()
    tracker.record("gpt-4", CallCost(prompt_tokens=100, completion_tokens=50, cost_usd=0.05))
    tracker.record("gpt-4", CallCost(prompt_tokens=200, completion_tokens=100, cost_usd=0.10))
    tracker.record("claude-3", CallCost(prompt_tokens=50, completion_tokens=25, cost_usd=0.02))
    app = _make_app()
    async with TestClient(TestServer(app)) as client:
        resp = await client.get("/api/cost/summary", headers=_auth_headers())
        data = await resp.json()
        assert data["total_cost_usd"] == pytest.approx(0.17, abs=0.001)
        assert "gpt-4" in data["by_model"]
        assert "claude-3" in data["by_model"]


@pytest.mark.asyncio
async def test_cost_summary_with_agent_costs():
    tracker = get_default_tracker()
    tracker.reset()
    store = Store()
    store.record_llm_spend("agent-1", 0.50)
    store._agent_metrics["agent-1"].agent_name = "Alice"
    store.record_llm_spend("agent-2", 0.25)
    store._agent_metrics["agent-2"].agent_name = "Bob"
    app = _make_app(store=store)
    async with TestClient(TestServer(app)) as client:
        resp = await client.get("/api/cost/summary", headers=_auth_headers())
        data = await resp.json()
        assert "Alice" in data["by_agent"]
        assert "Bob" in data["by_agent"]
        assert data["by_agent"]["Alice"] == pytest.approx(0.50)
        assert data["by_agent"]["Bob"] == pytest.approx(0.25)


@pytest.mark.asyncio
async def test_cost_summary_total_from_tracker():
    tracker = get_default_tracker()
    tracker.reset()
    tracker.record("model-x", CallCost(cost_usd=1.23))
    app = _make_app()
    async with TestClient(TestServer(app)) as client:
        resp = await client.get("/api/cost/summary", headers=_auth_headers())
        data = await resp.json()
        assert data["total_cost_usd"] == pytest.approx(1.23)

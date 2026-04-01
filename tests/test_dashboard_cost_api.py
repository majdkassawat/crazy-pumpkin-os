"""Tests for the GET /api/cost dashboard endpoint."""

from __future__ import annotations

import pytest
from aiohttp import web
from aiohttp.test_utils import AioHTTPTestCase, TestClient, TestServer

from crazypumpkin.dashboard.api import handle_cost_summary, setup_routes
from crazypumpkin.observability.cost import CostTracker, LLMUsageRecord


def _make_app(cost_tracker: CostTracker) -> web.Application:
    app = web.Application()
    app["cost_tracker"] = cost_tracker
    setup_routes(app)
    return app


@pytest.fixture
def cost_tracker() -> CostTracker:
    return CostTracker()


@pytest.fixture
def populated_tracker() -> CostTracker:
    tracker = CostTracker()
    tracker.record(LLMUsageRecord(
        agent_name="planner",
        provider="openai",
        model="gpt-4o",
        input_tokens=1000,
        output_tokens=500,
        cached_tokens=0,
        cost_usd=0.05,
    ))
    tracker.record(LLMUsageRecord(
        agent_name="coder",
        provider="openai",
        model="gpt-4o",
        input_tokens=2000,
        output_tokens=1000,
        cached_tokens=0,
        cost_usd=0.10,
    ))
    tracker.record(LLMUsageRecord(
        agent_name="planner",
        provider="anthropic",
        model="claude-sonnet-4-20250514",
        input_tokens=800,
        output_tokens=400,
        cached_tokens=0,
        cost_usd=0.03,
    ))
    return tracker


# ── GET /api/cost returns 200 with correct JSON keys ──


@pytest.mark.asyncio
async def test_cost_endpoint_returns_200(cost_tracker: CostTracker) -> None:
    app = _make_app(cost_tracker)
    async with TestClient(TestServer(app)) as client:
        resp = await client.get("/api/cost")
        assert resp.status == 200


@pytest.mark.asyncio
async def test_cost_endpoint_json_keys(cost_tracker: CostTracker) -> None:
    app = _make_app(cost_tracker)
    async with TestClient(TestServer(app)) as client:
        resp = await client.get("/api/cost")
        data = await resp.json()
        assert "total_spend_usd" in data
        assert "by_agent" in data
        assert "by_model" in data
        assert "record_count" in data


# ── Empty tracker returns zeros ──


@pytest.mark.asyncio
async def test_cost_endpoint_empty_tracker(cost_tracker: CostTracker) -> None:
    app = _make_app(cost_tracker)
    async with TestClient(TestServer(app)) as client:
        resp = await client.get("/api/cost")
        data = await resp.json()
        assert data["total_spend_usd"] == 0.0
        assert data["by_agent"] == {}
        assert data["by_model"] == {}
        assert data["record_count"] == 0


# ── Response reflects actual recorded usage data ──


@pytest.mark.asyncio
async def test_cost_endpoint_total_spend(populated_tracker: CostTracker) -> None:
    app = _make_app(populated_tracker)
    async with TestClient(TestServer(app)) as client:
        resp = await client.get("/api/cost")
        data = await resp.json()
        assert data["total_spend_usd"] == pytest.approx(0.18)


@pytest.mark.asyncio
async def test_cost_endpoint_by_agent(populated_tracker: CostTracker) -> None:
    app = _make_app(populated_tracker)
    async with TestClient(TestServer(app)) as client:
        resp = await client.get("/api/cost")
        data = await resp.json()
        assert data["by_agent"]["planner"] == pytest.approx(0.08)
        assert data["by_agent"]["coder"] == pytest.approx(0.10)


@pytest.mark.asyncio
async def test_cost_endpoint_by_model(populated_tracker: CostTracker) -> None:
    app = _make_app(populated_tracker)
    async with TestClient(TestServer(app)) as client:
        resp = await client.get("/api/cost")
        data = await resp.json()
        assert data["by_model"]["gpt-4o"] == pytest.approx(0.15)
        assert data["by_model"]["claude-sonnet-4-20250514"] == pytest.approx(0.03)


@pytest.mark.asyncio
async def test_cost_endpoint_record_count(populated_tracker: CostTracker) -> None:
    app = _make_app(populated_tracker)
    async with TestClient(TestServer(app)) as client:
        resp = await client.get("/api/cost")
        data = await resp.json()
        assert data["record_count"] == 3


@pytest.mark.asyncio
async def test_cost_endpoint_content_type(cost_tracker: CostTracker) -> None:
    app = _make_app(cost_tracker)
    async with TestClient(TestServer(app)) as client:
        resp = await client.get("/api/cost")
        assert "application/json" in resp.content_type

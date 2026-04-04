"""Tests for WebSocket agent-status broadcasting."""

from __future__ import annotations

import asyncio
import json

from unittest.mock import AsyncMock, MagicMock

from crazypumpkin.dashboard.ws import (
    WebSocketBroadcaster,
    broadcast_agent_status,
    emit_agent_status,
    subscribe_agent_status,
)
from crazypumpkin.framework.events import EventBus


# ── Helpers ──


def _mock_ws():
    """Return an AsyncMock that behaves like a websocket connection."""
    ws = AsyncMock()
    ws.send = AsyncMock()
    return ws


def _make_broadcaster(**kwargs):
    """Create a broadcaster with a mock EventBus."""
    bus = MagicMock(spec=EventBus)
    return WebSocketBroadcaster(bus, **kwargs)


# ── broadcast_agent_status ──


def test_broadcast_sends_agent_status_to_all_clients():
    broadcaster = _make_broadcaster()
    ws1, ws2 = _mock_ws(), _mock_ws()
    asyncio.run(broadcaster.connect(ws1))
    asyncio.run(broadcaster.connect(ws2))

    event = {"agent_id": "agent-1", "status": "active", "timestamp": "2026-04-01T00:00:00+00:00"}
    asyncio.run(broadcast_agent_status(broadcaster, event))

    ws1.send.assert_called_once()
    ws2.send.assert_called_once()

    data1 = json.loads(ws1.send.call_args[0][0])
    data2 = json.loads(ws2.send.call_args[0][0])
    assert data1 == data2
    assert data1["type"] == "agent_status"
    assert data1["agent_id"] == "agent-1"
    assert data1["status"] == "active"


def test_broadcast_payload_contains_required_fields():
    broadcaster = _make_broadcaster()
    ws = _mock_ws()
    asyncio.run(broadcaster.connect(ws))

    event = {"agent_id": "agent-x", "status": "idle", "timestamp": "2026-04-01T12:00:00+00:00"}
    asyncio.run(broadcast_agent_status(broadcaster, event))

    data = json.loads(ws.send.call_args[0][0])
    assert set(data.keys()) == {"type", "agent_id", "status", "timestamp"}
    assert data["type"] == "agent_status"
    assert data["agent_id"] == "agent-x"
    assert data["status"] == "idle"
    assert data["timestamp"] == "2026-04-01T12:00:00+00:00"


def test_broadcast_no_error_with_zero_clients():
    broadcaster = _make_broadcaster()
    event = {"agent_id": "agent-1", "status": "active", "timestamp": "2026-04-01T00:00:00+00:00"}
    # Must not raise
    asyncio.run(broadcast_agent_status(broadcaster, event))


def test_broadcast_removes_errored_client():
    broadcaster = _make_broadcaster()
    good_ws = _mock_ws()
    bad_ws = _mock_ws()
    bad_ws.send.side_effect = ConnectionError("gone")

    asyncio.run(broadcaster.connect(good_ws))
    asyncio.run(broadcaster.connect(bad_ws))

    event = {"agent_id": "a1", "status": "active", "timestamp": "2026-04-01T00:00:00+00:00"}
    asyncio.run(broadcast_agent_status(broadcaster, event))

    assert len(broadcaster._connections) == 1
    assert good_ws in broadcaster._connections


# ── emit_agent_status ──


def test_emit_agent_status_sends_message_with_timestamp():
    broadcaster = _make_broadcaster()
    ws = _mock_ws()
    asyncio.run(broadcaster.connect(ws))

    asyncio.run(emit_agent_status(broadcaster, "agent-alpha", "active"))

    data = json.loads(ws.send.call_args[0][0])
    assert data["type"] == "agent_status"
    assert data["agent_id"] == "agent-alpha"
    assert data["status"] == "active"
    # Timestamp is ISO format
    assert "T" in data["timestamp"]


def test_emit_agent_status_no_error_with_zero_clients():
    broadcaster = _make_broadcaster()
    asyncio.run(emit_agent_status(broadcaster, "agent-1", "disabled"))


# ── subscribe_agent_status (EventBus integration) ──


def test_subscribe_registers_handler_on_event_bus():
    bus = MagicMock(spec=EventBus)
    broadcaster = WebSocketBroadcaster(bus)

    subscribe_agent_status(broadcaster)

    bus.subscribe.assert_called_once_with("agent_status_changed", bus.subscribe.call_args[0][1])


def test_subscribe_wires_eventbus_to_broadcast():
    """When EventBus fires agent_status_changed, connected WS clients receive the message."""
    bus = EventBus()
    broadcaster = WebSocketBroadcaster(bus)
    ws = _mock_ws()

    async def _run():
        await broadcaster.connect(ws)
        subscribe_agent_status(broadcaster)
        # emit is sync but the handler schedules an async broadcast
        bus.emit(agent_id="agent-beta", action="agent_status_changed", detail="idle")
        # yield so the scheduled task runs
        await asyncio.sleep(0)

    asyncio.run(_run())

    ws.send.assert_called_once()
    data = json.loads(ws.send.call_args[0][0])
    assert data["type"] == "agent_status"
    assert data["agent_id"] == "agent-beta"
    assert data["status"] == "idle"
    assert data["timestamp"]  # non-empty


# ── WebSocket authentication ──


def test_connect_rejects_missing_token_when_auth_required():
    broadcaster = _make_broadcaster(auth_token="secret-123")
    ws = _mock_ws()
    result = asyncio.run(broadcaster.connect(ws))
    assert result is False
    assert ws not in broadcaster._connections


def test_connect_rejects_wrong_token():
    broadcaster = _make_broadcaster(auth_token="secret-123")
    ws = _mock_ws()
    result = asyncio.run(broadcaster.connect(ws, token="wrong"))
    assert result is False
    assert ws not in broadcaster._connections


def test_connect_accepts_correct_token():
    broadcaster = _make_broadcaster(auth_token="secret-123")
    ws = _mock_ws()
    result = asyncio.run(broadcaster.connect(ws, token="secret-123"))
    assert result is True
    assert ws in broadcaster._connections


def test_connect_allows_any_when_no_auth_token_set():
    broadcaster = _make_broadcaster()
    ws = _mock_ws()
    result = asyncio.run(broadcaster.connect(ws))
    assert result is True
    assert ws in broadcaster._connections

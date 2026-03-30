"""Tests for WebSocket broadcaster (live event streaming)."""

from __future__ import annotations

import asyncio
import json

from unittest.mock import AsyncMock, MagicMock

from crazypumpkin.dashboard.ws import WebSocketBroadcaster
from crazypumpkin.framework.events import EventBus


# ── Helpers ──


def _make_event(**overrides):
    """Create a lightweight mock event with default fields."""
    defaults = {
        "id": "evt-001",
        "timestamp": "2026-03-30T12:00:00",
        "agent_id": "agent-alpha",
        "action": "task.complete",
        "detail": "finished work",
        "result": "success",
        "risk_level": "low",
    }
    defaults.update(overrides)
    event = MagicMock()
    for k, v in defaults.items():
        setattr(event, k, v)
    return event


def _mock_ws():
    """Return an AsyncMock that behaves like a websocket connection."""
    ws = AsyncMock()
    ws.send = AsyncMock()
    return ws


def _make_broadcaster():
    """Create a broadcaster with a mock EventBus (no real subscriptions)."""
    bus = MagicMock(spec=EventBus)
    return WebSocketBroadcaster(bus)


# ── Tests ──


def test_connect_increases_client_count():
    broadcaster = _make_broadcaster()
    ws1, ws2, ws3 = _mock_ws(), _mock_ws(), _mock_ws()

    asyncio.run(broadcaster.connect(ws1))
    asyncio.run(broadcaster.connect(ws2))
    asyncio.run(broadcaster.connect(ws3))

    assert len(broadcaster._connections) == 3


def test_disconnect_removes_client():
    broadcaster = _make_broadcaster()
    ws = _mock_ws()

    asyncio.run(broadcaster.connect(ws))
    assert len(broadcaster._connections) == 1

    asyncio.run(broadcaster.disconnect(ws))
    assert len(broadcaster._connections) == 0


def test_broadcast_sends_to_all_clients():
    broadcaster = _make_broadcaster()
    ws1, ws2 = _mock_ws(), _mock_ws()

    asyncio.run(broadcaster.connect(ws1))
    asyncio.run(broadcaster.connect(ws2))

    event = _make_event()
    asyncio.run(broadcaster.broadcast(event))

    ws1.send.assert_called_once()
    ws2.send.assert_called_once()

    # Both received the same JSON payload
    sent1 = ws1.send.call_args[0][0]
    sent2 = ws2.send.call_args[0][0]
    assert json.loads(sent1) == json.loads(sent2)


def test_broadcast_removes_errored_client():
    broadcaster = _make_broadcaster()
    good_ws = _mock_ws()
    bad_ws = _mock_ws()
    bad_ws.send.side_effect = ConnectionError("gone")

    asyncio.run(broadcaster.connect(good_ws))
    asyncio.run(broadcaster.connect(bad_ws))
    assert len(broadcaster._connections) == 2

    event = _make_event()
    asyncio.run(broadcaster.broadcast(event))

    # The errored client should be removed
    assert len(broadcaster._connections) == 1
    assert good_ws in broadcaster._connections
    assert bad_ws not in broadcaster._connections


def test_broadcast_serializes_event_as_json():
    broadcaster = _make_broadcaster()
    ws = _mock_ws()
    asyncio.run(broadcaster.connect(ws))

    event = _make_event(
        id="evt-42",
        timestamp="2026-03-30T15:00:00",
        agent_id="agent-beta",
        action="file.write",
        detail="wrote config",
        result="success",
        risk_level="medium",
    )
    asyncio.run(broadcaster.broadcast(event))

    raw = ws.send.call_args[0][0]
    data = json.loads(raw)

    assert data["id"] == "evt-42"
    assert data["timestamp"] == "2026-03-30T15:00:00"
    assert data["agent_id"] == "agent-beta"
    assert data["action"] == "file.write"
    assert data["detail"] == "wrote config"
    assert data["result"] == "success"
    assert data["risk_level"] == "medium"

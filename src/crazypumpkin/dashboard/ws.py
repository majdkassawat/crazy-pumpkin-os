"""WebSocket broadcaster — streams live events to connected dashboard clients."""

from __future__ import annotations

import asyncio
import json
import logging
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from crazypumpkin.framework.events import EventBus

logger = logging.getLogger("crazypumpkin.dashboard.ws")


class WebSocketBroadcaster:
    """Broadcasts framework events to WebSocket clients.

    Parameters
    ----------
    event_bus:
        The ``EventBus`` instance to subscribe to for live events.
    """

    def __init__(self, event_bus: "EventBus", *, auth_token: str | None = None) -> None:
        self._event_bus = event_bus
        self._connections: list[Any] = []
        self._auth_token: str | None = auth_token

    async def connect(self, ws: Any, *, token: str | None = None) -> bool:
        """Register a new WebSocket connection.

        When *auth_token* was set on the broadcaster, the caller must supply a
        matching *token*.  Returns ``True`` on success, ``False`` if
        authentication failed.
        """
        if self._auth_token is not None and token != self._auth_token:
            logger.warning("Rejected WebSocket connection: invalid token")
            return False
        self._connections.append(ws)
        return True

    async def disconnect(self, ws: Any) -> None:
        """Remove a WebSocket connection."""
        if ws in self._connections:
            self._connections.remove(ws)

    async def broadcast(self, event: Any) -> None:
        """Serialize an event and send it to all connected clients.

        Clients that raise an exception during send are automatically
        removed from the connection list.
        """
        payload = json.dumps({
            "id": getattr(event, "id", ""),
            "timestamp": getattr(event, "timestamp", ""),
            "agent_id": getattr(event, "agent_id", ""),
            "action": getattr(event, "action", ""),
            "detail": getattr(event, "detail", ""),
            "result": getattr(event, "result", ""),
            "risk_level": getattr(event, "risk_level", ""),
        })

        to_remove: list[Any] = []
        for ws in self._connections:
            try:
                await ws.send(payload)
            except Exception:
                logger.warning("Removing errored WebSocket client")
                to_remove.append(ws)

        for ws in to_remove:
            if ws in self._connections:
                self._connections.remove(ws)


async def broadcast_agent_status(ws_manager: WebSocketBroadcaster, event: dict) -> None:
    """Broadcast an agent_status_changed event to all connected WebSocket clients."""
    payload = json.dumps({
        "type": "agent_status",
        "agent_id": event.get("agent_id", ""),
        "status": event.get("status", ""),
        "timestamp": event.get("timestamp", ""),
    })
    to_remove: list[Any] = []
    for ws in ws_manager._connections:
        try:
            await ws.send(payload)
        except Exception:
            logger.warning("Removing errored WebSocket client during agent status broadcast")
            to_remove.append(ws)
    for ws in to_remove:
        if ws in ws_manager._connections:
            ws_manager._connections.remove(ws)


async def emit_agent_status(
    broadcaster: WebSocketBroadcaster, agent_id: str, status: str,
) -> None:
    """Build an agent-status event dict with an ISO timestamp and broadcast it."""
    from crazypumpkin.framework.models import _now

    await broadcast_agent_status(broadcaster, {
        "agent_id": agent_id,
        "status": status,
        "timestamp": _now(),
    })


def subscribe_agent_status(broadcaster: WebSocketBroadcaster) -> None:
    """Subscribe to ``agent_status_changed`` on the EventBus so changes are
    automatically pushed to all connected WebSocket clients."""

    def _on_status_change(audit_event: Any) -> None:
        coro = broadcast_agent_status(broadcaster, {
            "agent_id": audit_event.agent_id,
            "status": audit_event.detail or audit_event.result,
            "timestamp": audit_event.timestamp,
        })
        try:
            loop = asyncio.get_running_loop()
            loop.create_task(coro)
        except RuntimeError:
            asyncio.run(coro)

    broadcaster._event_bus.subscribe("agent_status_changed", _on_status_change)

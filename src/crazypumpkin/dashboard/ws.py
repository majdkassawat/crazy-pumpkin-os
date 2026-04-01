"""WebSocket broadcaster — streams live events to connected dashboard clients."""

from __future__ import annotations

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

    def __init__(self, event_bus: "EventBus") -> None:
        self._event_bus = event_bus
        self._connections: list[Any] = []

    async def connect(self, ws: Any) -> None:
        """Register a new WebSocket connection."""
        self._connections.append(ws)

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

"""WebSocket broadcaster — streams live events to connected dashboard clients."""

from __future__ import annotations

import asyncio
import json
import logging
from typing import TYPE_CHECKING, Any

from crazypumpkin.agents.health import HealthChecker

if TYPE_CHECKING:
    from crazypumpkin.framework.events import EventBus

logger = logging.getLogger("crazypumpkin.dashboard.ws")


class WebSocketBroadcaster:
    """Broadcasts framework events to WebSocket clients.

    Parameters
    ----------
    event_bus:
        The ``EventBus`` instance to subscribe to for live events.
    health_interval:
        Seconds between health broadcasts (default 30).
    allowed_origins:
        Optional set of allowed origins. ``None`` disables origin checking.
    """

    def __init__(
        self,
        event_bus: "EventBus",
        health_interval: int = 30,
        allowed_origins: set[str] | None = None,
        auth_token: str | None = None,
    ) -> None:
        self._event_bus = event_bus
        self._connections: list[Any] = []
        self._health_interval = health_interval
        self._health_task: asyncio.Task[None] | None = None
        self._allowed_origins = allowed_origins
        self._auth_token: str | None = auth_token

    # ── Connection auth gate ──────────────────────────────────────────

    def _validate_connection(self, ws: Any) -> bool:
        """Validate incoming WebSocket connection before allowing access.

        Checks the ``origin`` attribute against *_allowed_origins* when the
        allowlist is configured.  Returns ``True`` when no allowlist is set
        (development / test mode) or when the origin is permitted.
        """
        if self._allowed_origins is None:
            return True
        origin = getattr(ws, "origin", None)
        if origin is None:
            return False
        return str(origin) in self._allowed_origins

    # ── Connection lifecycle ──────────────────────────────────────────

    async def connect(self, ws: Any, *, token: str | None = None) -> bool:
        """Register a new WebSocket connection.

        When *auth_token* was set on the broadcaster, the caller must supply a
        matching *token*.  Validates the connection origin before accepting.
        Starts the health broadcast loop when the first client connects.
        Returns ``True`` on success, ``False`` if authentication failed.
        """
        if self._auth_token is not None and token != self._auth_token:
            logger.warning("Rejected WebSocket connection: invalid token")
            return False
        if not self._validate_connection(ws):
            logger.warning("Rejected WebSocket connection: origin not allowed")
            return False

        self._connections.append(ws)
        if len(self._connections) == 1 and self._health_task is None:
            self._health_task = asyncio.ensure_future(
                self._health_broadcast_loop(self._health_interval)
            )
        return True

    async def disconnect(self, ws: Any) -> None:
        """Remove a WebSocket connection.

        Cancels the health broadcast loop when no clients remain.
        """
        if ws in self._connections:
            self._connections.remove(ws)
        if not self._connections and self._health_task is not None:
            self._health_task.cancel()
            try:
                await self._health_task
            except asyncio.CancelledError:
                pass
            self._health_task = None

    # ── Broadcasting ──────────────────────────────────────────────────

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

    async def broadcast_json(self, payload: dict[str, Any]) -> None:
        """Serialize *payload* as JSON and send to all connected clients."""
        raw = json.dumps(payload)
        to_remove: list[Any] = []
        for ws in self._connections:
            try:
                await ws.send(raw)
            except Exception:
                logger.warning("Removing errored WebSocket client")
                to_remove.append(ws)
        for ws in to_remove:
            if ws in self._connections:
                self._connections.remove(ws)

    # ── Health broadcast loop ─────────────────────────────────────────

    async def _health_broadcast_loop(self, interval: int = 30) -> None:
        """Broadcast health status to all connected clients every *interval* seconds.

        Sleeps first, then broadcasts — this prevents a duplicate send on the
        same tick as the initial connection.
        """
        checker = HealthChecker()
        while True:
            await asyncio.sleep(interval)
            try:
                results = await checker.check_all()
                payload = {
                    "type": "health_update",
                    "agents": [r.to_dict() for r in results],
                }
            except Exception:
                logger.exception("Error collecting health data; skipping broadcast")
                continue
            await self.broadcast_json(payload)

    async def shutdown(self) -> None:
        """Cancel the health broadcast loop (called on server shutdown)."""
        if self._health_task is not None:
            self._health_task.cancel()
            try:
                await self._health_task
            except asyncio.CancelledError:
                pass
            self._health_task = None


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

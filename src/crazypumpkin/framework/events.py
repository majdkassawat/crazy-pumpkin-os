"""
Event bus and audit logger.

Every meaningful action produces an AuditEvent.
Listeners can subscribe to specific action types.
"""

from __future__ import annotations

import asyncio
import json
import logging
import uuid
from pathlib import Path
from typing import Any, Awaitable, Callable, Generic, TypeVar

from crazypumpkin.framework.models import AuditEvent, _now, _uid
from crazypumpkin.notifications import notify as _notify

T = TypeVar("T")

logger = logging.getLogger("crazypumpkin.events")

# ---------------------------------------------------------------------------
# Event type constants
# ---------------------------------------------------------------------------
CONFIG_RELOADED = "config.reloaded"

EventHandler = Callable[[AuditEvent], None]


class EventBus:
    """Publish-subscribe event system with persistent audit log."""

    def __init__(self, log_dir: Path | None = None):
        self._handlers: dict[str, list[EventHandler]] = {}
        self._global_handlers: list[EventHandler] = []
        self._log: list[AuditEvent] = []
        self._log_file: Path | None = None

        if log_dir:
            log_dir.mkdir(parents=True, exist_ok=True)
            self._log_file = log_dir / "audit.jsonl"

    def subscribe(self, action: str, handler: EventHandler) -> None:
        self._handlers.setdefault(action, []).append(handler)

    def subscribe_all(self, handler: EventHandler) -> None:
        self._global_handlers.append(handler)

    def emit(
        self,
        agent_id: str,
        action: str,
        entity_type: str = "",
        entity_id: str = "",
        detail: str = "",
        result: str = "success",
        confidence: float | None = None,
        risk_level: str = "low",
        metadata: dict[str, Any] | None = None,
    ) -> AuditEvent:
        event = AuditEvent(
            id=_uid(),
            timestamp=_now(),
            agent_id=agent_id,
            action=action,
            entity_type=entity_type,
            entity_id=entity_id,
            detail=detail,
            result=result,
            confidence=confidence,
            risk_level=risk_level,
            metadata=metadata or {},
        )

        self._log.append(event)
        self._persist(event)

        logger.info(
            "[%s] %s %s/%s: %s -> %s",
            event.agent_id[:8], event.action,
            event.entity_type, event.entity_id[:8] if event.entity_id else "-",
            event.detail[:80], event.result,
        )

        for handler in self._global_handlers:
            handler(event)
        for handler in self._handlers.get(action, []):
            handler(event)

        # Console notification for lifecycle events.
        _notify({
            "action": event.action,
            "timestamp": event.timestamp,
            "entity_type": event.entity_type,
            "entity_id": event.entity_id,
            "agent_id": event.agent_id,
            "detail": event.detail,
        })

        return event

    def _persist(self, event: AuditEvent) -> None:
        if not self._log_file:
            return
        try:
            with open(self._log_file, "a", encoding="utf-8") as f:
                row = {
                    "id": event.id, "timestamp": event.timestamp,
                    "agent_id": event.agent_id, "action": event.action,
                    "entity_type": event.entity_type, "entity_id": event.entity_id,
                    "detail": event.detail, "result": event.result,
                    "confidence": event.confidence, "risk_level": event.risk_level,
                    "metadata": event.metadata,
                }
                f.write(json.dumps(row) + "\n")
        except OSError:
            pass

    def load(self, tail: int = 1000) -> None:
        """Load persisted events from audit.jsonl into the in-memory log.

        Only keeps the last *tail* events to avoid excessive memory usage.
        """
        if not self._log_file or not self._log_file.exists():
            return
        from collections import deque
        buf: deque[dict] = deque(maxlen=tail)
        try:
            with open(self._log_file, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        buf.append(json.loads(line))
                    except json.JSONDecodeError:
                        continue
        except OSError:
            return
        for row in buf:
            try:
                event = AuditEvent(
                    id=row.get("id", ""),
                    timestamp=row.get("timestamp", ""),
                    agent_id=row.get("agent_id", ""),
                    action=row.get("action", ""),
                    entity_type=row.get("entity_type", ""),
                    entity_id=row.get("entity_id", ""),
                    detail=row.get("detail", ""),
                    result=row.get("result", "success"),
                    confidence=row.get("confidence"),
                    risk_level=row.get("risk_level", "low"),
                    metadata=row.get("metadata", {}),
                )
                self._log.append(event)
            except TypeError:
                continue
        if buf:
            logger.debug("Loaded %d events from %s", len(buf), self._log_file)

    def recent(self, n: int = 50, action: str | None = None) -> list[AuditEvent]:
        events = self._log
        if action:
            events = [e for e in events if e.action == action]
        return events[-n:]

    @property
    def total_events(self) -> int:
        return len(self._log)


# ---------------------------------------------------------------------------
# Typed event channels
# ---------------------------------------------------------------------------


class EventChannel(Generic[T]):
    """A typed publish-subscribe channel for a single event type."""

    def __init__(self, name: str, event_type: type[T]) -> None:
        self.name = name
        self.event_type = event_type
        self._subscribers: dict[str, tuple[Callable[[T], Awaitable[None]], Callable[[T], bool] | None]] = {}
        self._pending_tasks: set[asyncio.Task[None]] = set()

    async def publish(self, event: T) -> None:
        """Publish an event to all matching subscribers."""
        tasks: list[asyncio.Task[None]] = []
        for _sub_id, (handler, filter_fn) in list(self._subscribers.items()):
            if filter_fn is not None and not filter_fn(event):
                continue
            task = asyncio.create_task(handler(event))
            self._pending_tasks.add(task)
            task.add_done_callback(self._pending_tasks.discard)
            tasks.append(task)
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)

    def subscribe(
        self,
        handler: Callable[[T], Awaitable[None]],
        filter_fn: Callable[[T], bool] | None = None,
    ) -> str:
        """Subscribe a handler. Returns a subscription_id."""
        subscription_id = str(uuid.uuid4())
        self._subscribers[subscription_id] = (handler, filter_fn)
        return subscription_id

    def unsubscribe(self, subscription_id: str) -> None:
        """Remove a subscription by its id."""
        self._subscribers.pop(subscription_id, None)


class ChannelRegistry:
    """Registry that manages named event channels."""

    def __init__(self) -> None:
        self._channels: dict[str, EventChannel[Any]] = {}

    def get_or_create(self, name: str, event_type: type) -> EventChannel:
        """Return existing channel or create a new one.

        Raises TypeError if a channel with *name* already exists but was
        created with a different *event_type*.
        """
        existing = self._channels.get(name)
        if existing is not None:
            if existing.event_type is not event_type:
                raise TypeError(
                    f"Channel {name!r} already registered with event_type "
                    f"{existing.event_type!r}, cannot re-register with {event_type!r}"
                )
            return existing
        channel: EventChannel = EventChannel(name, event_type)
        self._channels[name] = channel
        return channel

    def list_channels(self) -> list[str]:
        """Return names of all registered channels."""
        return list(self._channels.keys())

    async def shutdown(self) -> None:
        """Cancel all pending deliveries across all channels."""
        for channel in self._channels.values():
            for task in list(channel._pending_tasks):
                task.cancel()
            # Wait for cancellations to propagate
            if channel._pending_tasks:
                await asyncio.gather(*channel._pending_tasks, return_exceptions=True)
        self._channels.clear()

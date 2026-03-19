"""
Event bus and audit logger.

Every meaningful action produces an AuditEvent.
Listeners can subscribe to specific action types.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any, Callable

from crazypumpkin.framework.models import AuditEvent, _now, _uid

logger = logging.getLogger("crazypumpkin.events")

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

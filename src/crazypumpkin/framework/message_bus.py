"""
Message bus — publish/subscribe pattern for inter-agent communication.

Messages are stored in memory with optional persistence to a Store.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Callable

from crazypumpkin.framework.models import _now, _uid

logger = logging.getLogger("crazypumpkin.message_bus")

MessageHandler = Callable[["Message"], None]


@dataclass
class Message:
    """A message published on the bus."""
    id: str = field(default_factory=_uid)
    topic: str = ""
    content: Any = None
    sender: str = ""
    timestamp: str = field(default_factory=_now)


class MessageBus:
    """Publish-subscribe message bus with in-memory storage and optional persistence."""

    def __init__(self, store: Any | None = None, max_messages: int = 10000):
        self._messages: list[Message] = []
        self._handlers: dict[str, list[MessageHandler]] = {}
        self._store = store
        self._max_messages = max_messages

    def publish(self, topic: str, message: Any, sender: str = "") -> Message:
        """Publish a message to a topic.

        Stores the message in memory, notifies subscribers, and optionally
        persists to the store.
        """
        msg = Message(topic=topic, content=message, sender=sender)
        self._messages.append(msg)
        if len(self._messages) > self._max_messages:
            self._messages = self._messages[-self._max_messages:]

        for handler in self._handlers.get(topic, []):
            try:
                handler(msg)
            except Exception:
                logger.exception("Handler error on topic '%s'", topic)

        if self._store is not None:
            self._persist(msg)

        logger.debug(
            "Published to '%s' from '%s': %s", topic, sender, msg.id,
        )
        return msg

    def subscribe(self, topic: str, handler: MessageHandler) -> None:
        """Subscribe a handler to a topic."""
        self._handlers.setdefault(topic, []).append(handler)

    def get_messages(
        self, topic: str, since: str | None = None,
    ) -> list[Message]:
        """Return messages for a topic, optionally filtered to those after *since* timestamp."""
        msgs = [m for m in self._messages if m.topic == topic]
        if since is not None:
            msgs = [m for m in msgs if m.timestamp > since]
        return msgs

    def _persist(self, msg: Message) -> None:
        """Persist a message via the store if available."""
        try:
            if hasattr(self._store, "save"):
                self._store.save()
        except Exception:
            logger.exception("Failed to persist message %s", msg.id)

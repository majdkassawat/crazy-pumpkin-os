"""Notification dispatcher — routes lifecycle events and alerts to channels."""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

from .base import NotificationChannel
from .slack import SlackWebhookChannel

logger = logging.getLogger("crazypumpkin.notifications")

# Event actions considered lifecycle notifications.
_LIFECYCLE_ACTIONS = frozenset({
    "task_start", "task_complete", "task_fail",
    "agent_start", "agent_complete", "agent_fail",
})

# Map lifecycle actions to alert severity levels.
_ACTION_LEVEL = {
    "task_start": "info",
    "task_complete": "info",
    "task_fail": "error",
    "agent_start": "info",
    "agent_complete": "info",
    "agent_fail": "error",
}

# Map health statuses to alert severity levels.
_HEALTH_LEVEL = {
    "healthy": "info",
    "degraded": "warning",
    "unhealthy": "error",
    "critical": "critical",
}


class NotificationRouter:
    """Central dispatcher that routes notifications to registered channels."""

    def __init__(self) -> None:
        self._channels: list[NotificationChannel] = []

    @property
    def channels(self) -> list[NotificationChannel]:
        """Return a copy of the registered channels list."""
        return list(self._channels)

    def add_channel(self, channel: NotificationChannel) -> None:
        """Register a notification channel."""
        self._channels.append(channel)

    def remove_channel(self, channel: NotificationChannel) -> None:
        """Remove a previously registered channel."""
        self._channels.remove(channel)

    def clear(self) -> None:
        """Remove all registered channels."""
        self._channels.clear()

    def notify_event(self, event: dict[str, Any]) -> None:
        """Route a lifecycle event to all registered channels.

        Parameters
        ----------
        event:
            A dict with at least ``action`` and optionally ``timestamp``,
            ``entity_type``, ``entity_id``, ``agent_id``, and ``detail``.
        """
        action = event.get("action", "")
        if action not in _LIFECYCLE_ACTIONS:
            return

        timestamp = event.get("timestamp") or datetime.now(timezone.utc).isoformat()
        subject = event.get("entity_id") or event.get("agent_id") or "unknown"
        detail = event.get("detail", "")

        parts = [timestamp, action, subject]
        if detail:
            parts.append(detail)
        message = " | ".join(parts)

        level = _ACTION_LEVEL.get(action, "info")
        for channel in self._channels:
            try:
                channel.send_alert(message, level=level)
            except Exception:
                logger.exception("Failed to send event notification via %s", type(channel).__name__)

    def notify_health(self, report: Any) -> None:
        """Route a health report to all registered channels.

        Parameters
        ----------
        report:
            A ``HealthReport`` or ``SystemHealth`` object with ``status``,
            ``message``, and optionally ``details`` attributes.
        """
        status = getattr(report, "status", "unknown")
        message = getattr(report, "message", "") or getattr(report, "summary", "")
        level = _HEALTH_LEVEL.get(status, "warning")

        text = f"[Health: {status}] {message}"
        for channel in self._channels:
            try:
                channel.send_alert(text, level=level)
            except Exception:
                logger.exception("Failed to send health notification via %s", type(channel).__name__)


# Global router instance.
_router = NotificationRouter()


def get_router() -> NotificationRouter:
    """Return the global notification router."""
    return _router


def configure_slack(config: dict[str, Any]) -> SlackWebhookChannel | None:
    """Configure and register a Slack channel from a notifications config dict.

    Parameters
    ----------
    config:
        The ``notifications`` section of the framework config. Expected
        to contain a ``slack`` key with at least ``webhook_url``.

    Returns
    -------
    The created ``SlackWebhookChannel``, or *None* if Slack is not configured.
    """
    slack_cfg = config.get("slack")
    if not slack_cfg or not isinstance(slack_cfg, dict):
        return None
    webhook_url = slack_cfg.get("webhook_url", "")
    if not webhook_url or not str(webhook_url).strip():
        return None
    channel = SlackWebhookChannel.from_config(slack_cfg)
    _router.add_channel(channel)
    return channel


def notify(event: dict[str, Any]) -> None:
    """Print a structured notification line for a lifecycle event and
    forward to all registered channels.

    Parameters
    ----------
    event:
        A dict with at least ``action`` and optionally ``timestamp``,
        ``entity_type``, ``entity_id``, ``agent_id``, and ``detail``.
    """
    action = event.get("action", "")
    if action not in _LIFECYCLE_ACTIONS:
        return

    timestamp = event.get("timestamp") or datetime.now(timezone.utc).isoformat()
    subject = event.get("entity_id") or event.get("agent_id") or "unknown"
    detail = event.get("detail", "")

    parts = [f"[NOTIFY] {timestamp}", action, subject]
    if detail:
        parts.append(detail)
    print(" | ".join(parts))

    # Forward to registered channels.
    _router.notify_event(event)

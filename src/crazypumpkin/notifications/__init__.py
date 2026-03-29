"""Console notifier — prints structured notification lines to stdout."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any


# Event actions considered lifecycle notifications.
_LIFECYCLE_ACTIONS = frozenset({
    "task_start", "task_complete", "task_fail",
    "agent_start", "agent_complete", "agent_fail",
})


def notify(event: dict[str, Any]) -> None:
    """Print a structured notification line for a lifecycle event.

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

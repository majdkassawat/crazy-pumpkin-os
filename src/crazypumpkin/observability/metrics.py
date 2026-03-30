"""Simple in-process metrics: counters and gauges.

Tracks task throughput, agent uptime, and error rates using plain
counters and gauges protected by a threading lock so the module is
safe to call from multiple threads.
"""

from __future__ import annotations

import threading
import time
from typing import Any

_lock = threading.Lock()

# Counters
_tasks_completed: int = 0
_errors: int = 0
_errors_by_type: dict[str, int] = {}

# Gauges  (agent_id -> start-timestamp)
_agent_start_times: dict[str, float] = {}


def record_task_completed(count: int = 1) -> None:
    """Increment the completed-tasks counter.

    Args:
        count: Number of tasks to add (default 1).
    """
    global _tasks_completed
    with _lock:
        _tasks_completed += count


def record_error(error_type: str = "unknown") -> None:
    """Increment the global error counter and the per-type sub-counter.

    Args:
        error_type: A short label for the kind of error (e.g. ``"timeout"``).
    """
    global _errors
    with _lock:
        _errors += 1
        _errors_by_type[error_type] = _errors_by_type.get(error_type, 0) + 1


def record_agent_uptime(agent_id: str) -> None:
    """Mark *agent_id* as started (or update its start time) to track uptime.

    Call this when an agent begins running.  The uptime for each agent is
    computed as ``now - start_time`` when :func:`get_metrics_snapshot` is
    called.

    Args:
        agent_id: Unique agent identifier.
    """
    with _lock:
        _agent_start_times[agent_id] = time.monotonic()


def get_metrics_snapshot() -> dict[str, Any]:
    """Return a point-in-time snapshot of all tracked metrics.

    Returns:
        A dict with the following keys:

        * ``tasks_completed`` – total tasks finished.
        * ``errors`` – total errors recorded.
        * ``errors_by_type`` – ``{error_type: count}`` breakdown.
        * ``agent_uptime`` – ``{agent_id: seconds}`` for every tracked agent.
    """
    now = time.monotonic()
    with _lock:
        return {
            "tasks_completed": _tasks_completed,
            "errors": _errors,
            "errors_by_type": dict(_errors_by_type),
            "agent_uptime": {
                aid: now - start
                for aid, start in _agent_start_times.items()
            },
        }


def reset() -> None:
    """Reset all metrics to zero.  Intended for testing."""
    global _tasks_completed, _errors
    with _lock:
        _tasks_completed = 0
        _errors = 0
        _errors_by_type.clear()
        _agent_start_times.clear()

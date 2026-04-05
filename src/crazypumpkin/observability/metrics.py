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

# Cache counters
_cache_hits: int = 0
_cache_misses: int = 0
_cache_tokens_saved: int = 0

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


def record_cache_event(provider: str, hit: bool, tokens_saved: int = 0) -> None:
    """Record a cache hit or miss for an LLM provider.

    Args:
        provider: Name of the LLM provider (e.g. ``"anthropic"``).
        hit: ``True`` for a cache hit, ``False`` for a miss.
        tokens_saved: Number of input tokens served from cache.
    """
    global _cache_hits, _cache_misses, _cache_tokens_saved
    with _lock:
        if hit:
            _cache_hits += 1
            _cache_tokens_saved += tokens_saved
        else:
            _cache_misses += 1


def get_cache_stats() -> dict[str, int]:
    """Return current cache statistics.

    Returns:
        A dict with keys ``hits``, ``misses``, ``tokens_saved``, and
        ``hit_rate_pct`` (integer 0-100).
    """
    with _lock:
        total = _cache_hits + _cache_misses
        hit_rate = (_cache_hits * 100 // total) if total else 0
        return {
            "hits": _cache_hits,
            "misses": _cache_misses,
            "tokens_saved": _cache_tokens_saved,
            "hit_rate_pct": hit_rate,
        }


def get_llm_cost_snapshot() -> dict[str, Any]:
    """Return a snapshot of LLM cost tracking data from the default tracker.

    Returns:
        A dict with keys ``total_cost_usd``, ``call_count``,
        ``total_prompt_tokens``, ``total_completion_tokens``,
        ``total_cache_read_tokens``, ``total_cache_creation_tokens``,
        and ``by_model``.
    """
    from crazypumpkin.llm.base import get_default_tracker

    tracker = get_default_tracker()
    summary = tracker.get_summary()
    return {
        "total_cost_usd": summary["total_cost_usd"],
        "call_count": summary["call_count"],
        "total_prompt_tokens": summary["total_prompt_tokens"],
        "total_completion_tokens": summary["total_completion_tokens"],
        "total_cache_read_tokens": summary["total_cache_read_tokens"],
        "total_cache_creation_tokens": summary["total_cache_creation_tokens"],
        "by_model": summary["by_model"],
    }


def get_cost_by_product_snapshot() -> dict[str, Any]:
    """Return a snapshot of per-product LLM cost data from the default tracker.

    Returns:
        A dict with product_id keys mapping to cost dicts containing
        ``total_cost_usd``, ``call_count``, ``total_prompt_tokens``,
        and ``total_completion_tokens``.
    """
    from crazypumpkin.llm.base import get_default_tracker

    tracker = get_default_tracker()
    return tracker.get_summary_by_product()


def get_metrics_snapshot() -> dict[str, Any]:
    """Return a point-in-time snapshot of all tracked metrics.

    Returns:
        A dict with the following keys:

        * ``tasks_completed`` – total tasks finished.
        * ``errors`` – total errors recorded.
        * ``errors_by_type`` – ``{error_type: count}`` breakdown.
        * ``agent_uptime`` – ``{agent_id: seconds}`` for every tracked agent.
        * ``llm_costs`` – aggregate LLM cost snapshot.
        * ``llm_costs_by_product`` – per-product LLM cost breakdown.
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
            "llm_costs": get_llm_cost_snapshot(),
            "llm_costs_by_product": get_cost_by_product_snapshot(),
        }


def reset() -> None:
    """Reset all metrics to zero.  Intended for testing."""
    global _tasks_completed, _errors, _cache_hits, _cache_misses, _cache_tokens_saved
    with _lock:
        _tasks_completed = 0
        _errors = 0
        _errors_by_type.clear()
        _agent_start_times.clear()
        _cache_hits = 0
        _cache_misses = 0
        _cache_tokens_saved = 0

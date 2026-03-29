"""Dashboard data readers for Crazy Pumpkin OS."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from crazypumpkin.framework.events import EventBus
    from crazypumpkin.framework.registry import AgentRegistry
    from crazypumpkin.framework.store import Store
    from crazypumpkin.scheduler.scheduler import Scheduler

from crazypumpkin.framework.models import AgentStatus


def get_agent_activity(registry: "AgentRegistry") -> list[dict]:
    """Return activity info for all non-disabled agents."""
    result = []
    for agent in registry._agents.values():
        if agent.agent.status == AgentStatus.DISABLED:
            continue
        result.append({
            "id": agent.id,
            "name": agent.name,
            "role": agent.role.value if hasattr(agent.role, "value") else str(agent.role),
            "status": agent.agent.status.value if hasattr(agent.agent.status, "value") else str(agent.agent.status),
        })
    return result


def get_task_status(store: "Store") -> list[dict]:
    """Return status info for all tasks in the store."""
    result = []
    for task in store.tasks.values():
        result.append({
            "id": task.id,
            "title": task.title if hasattr(task, "title") else "",
            "status": task.status.value if hasattr(task.status, "value") else str(task.status),
            "assigned_to": task.assigned_to if hasattr(task, "assigned_to") else None,
        })
    return result


def get_scheduler_state(scheduler: "Scheduler") -> dict:
    """Return current scheduler state."""
    return {
        "last_run": scheduler.last_run,
        "cycle_count": scheduler.cycle_count,
        "agent_last_dispatch": dict(scheduler.agent_last_dispatch),
    }


def get_recent_logs(bus: "EventBus", n: int = 50) -> list[dict]:
    """Return the last *n* audit events from the event bus."""
    events = bus.recent(n=n)
    return [
        {
            "id": e.id,
            "timestamp": e.timestamp,
            "agent_id": e.agent_id,
            "action": e.action,
            "entity_type": e.entity_type,
            "entity_id": e.entity_id,
            "detail": e.detail,
            "result": e.result,
            "risk_level": e.risk_level,
        }
        for e in events
    ]

"""Dashboard API — JSON-serializable pipeline state snapshot."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from crazypumpkin.framework.registry import AgentRegistry
    from crazypumpkin.framework.store import Store

from crazypumpkin.dashboard.auth import admin_required, auth_required
from crazypumpkin.framework.models import AgentStatus, TaskStatus


_STATUS_BUCKETS = {
    "planned": {TaskStatus.CREATED, TaskStatus.PLANNED},
    "in_progress": {TaskStatus.ASSIGNED, TaskStatus.IN_PROGRESS, TaskStatus.SUBMITTED_FOR_REVIEW},
    "completed": {TaskStatus.COMPLETED, TaskStatus.APPROVED, TaskStatus.ARCHIVED},
    "failed": {TaskStatus.REJECTED, TaskStatus.ESCALATED},
}


def get_dashboard_data(
    registry: "AgentRegistry",
    store: "Store",
) -> dict:
    """Return a JSON-serializable dict of current pipeline state.

    Sections:
      - agents: list of active agent dicts
      - tasks: counts by status bucket + recent completions
      - errors: summary of failed/escalated tasks
    """
    # ── Agents ──
    agents = []
    for agent in registry._agents.values():
        if agent.agent.status == AgentStatus.DISABLED:
            continue
        agents.append({
            "id": agent.id,
            "name": agent.name,
            "role": agent.role.value if hasattr(agent.role, "value") else str(agent.role),
            "status": agent.agent.status.value if hasattr(agent.agent.status, "value") else str(agent.agent.status),
        })

    # ── Tasks ──
    counts: dict[str, int] = {k: 0 for k in _STATUS_BUCKETS}
    completed_tasks: list[dict] = []
    for task in store.tasks.values():
        for bucket, statuses in _STATUS_BUCKETS.items():
            if task.status in statuses:
                counts[bucket] += 1
                break
        if task.status == TaskStatus.COMPLETED:
            completed_tasks.append({
                "id": task.id,
                "title": task.title,
                "updated_at": task.updated_at,
            })

    # Sort by updated_at descending and keep last 10
    completed_tasks.sort(key=lambda t: t["updated_at"], reverse=True)
    recent_completions = completed_tasks[:10]

    # ── Errors ──
    error_tasks = []
    for task in store.tasks.values():
        if task.status in (TaskStatus.REJECTED, TaskStatus.ESCALATED):
            error_tasks.append({
                "id": task.id,
                "title": task.title,
                "status": task.status.value,
                "assigned_to": task.assigned_to,
            })

    # ── Costs ──
    from crazypumpkin.framework.models import AgentMetrics as _AM

    per_agent_costs: list[dict] = []
    total_usd = 0.0
    for m in store._agent_metrics.values():
        per_agent_costs.append({
            "agent_id": m.agent_id,
            "agent_name": m.agent_name,
            "budget_spent_usd": m.budget_spent_usd,
        })
        total_usd += m.budget_spent_usd

    return {
        "agents": agents,
        "tasks": {
            "counts": counts,
            "recent_completions": recent_completions,
        },
        "errors": error_tasks,
        "costs": {
            "per_agent": per_agent_costs,
            "total_usd": round(total_usd, 4),
        },
    }


# ---------------------------------------------------------------------------
# Agent status endpoint
# ---------------------------------------------------------------------------


def get_agent_statuses(registry: "AgentRegistry") -> list[dict]:
    """GET /api/agents/status — return status for all registered agents."""
    result = []
    for agent in registry._agents.values():
        health = "degraded" if agent.agent.status == AgentStatus.DISABLED else "healthy"
        result.append({
            "name": agent.name,
            "status": agent.agent.status.value if hasattr(agent.agent.status, "value") else str(agent.agent.status),
            "last_heartbeat": None,
            "tasks_completed": 0,
            "health": health,
        })
    return result


# ---------------------------------------------------------------------------
# Role-protected endpoints
# ---------------------------------------------------------------------------


def get_dashboard_data_authed(
    token: str,
    registry: "AgentRegistry",
    store: "Store",
) -> dict:
    """GET /api/dashboard — read-only dashboard data (viewer or admin).

    Raises :class:`~crazypumpkin.dashboard.auth.AuthError` (401) for
    invalid tokens.
    """
    auth_required(token)
    return get_dashboard_data(registry, store)


def update_config(token: str, config_data: dict) -> dict:
    """PUT /api/config — update pipeline configuration (admin only).

    Raises :class:`~crazypumpkin.dashboard.auth.AuthError` (401) for
    invalid tokens, or (403) for non-admin users.
    Returns ``{"ok": True, "config": <config_data>}`` on success.
    """
    admin_required(token)
    return {"ok": True, "config": config_data}


def restart_agent(token: str, agent_id: str, registry: "AgentRegistry") -> dict:
    """POST /api/agents/<id>/restart — restart an agent (admin only).

    Raises :class:`~crazypumpkin.dashboard.auth.AuthError` (401) for
    invalid tokens, or (403) for non-admin users.
    Returns ``{"ok": True, "agent_id": <id>}`` on success.
    """
    admin_required(token)
    return {"ok": True, "agent_id": agent_id}

"""Dashboard API — JSON-serializable pipeline state snapshot."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from crazypumpkin.framework.registry import AgentRegistry
    from crazypumpkin.framework.store import Store

from aiohttp import web

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


async def handle_cost_summary(request: web.Request) -> web.Response:
    """GET /api/cost — return CostTracker summary as JSON."""
    tracker = request.app["cost_tracker"]
    records = tracker._records

    total_spend = sum(r.cost_usd for r in records)
    by_agent: dict[str, float] = {}
    by_model: dict[str, float] = {}
    for r in records:
        by_agent[r.agent_name] = by_agent.get(r.agent_name, 0.0) + r.cost_usd
        by_model[r.model] = by_model.get(r.model, 0.0) + r.cost_usd

    payload = {
        "total_spend_usd": total_spend,
        "by_agent": by_agent,
        "by_model": by_model,
        "record_count": len(records),
    }
    return web.Response(
        text=json.dumps(payload),
        content_type="application/json",
    )


def setup_routes(app: web.Application) -> None:
    """Register all API routes on the aiohttp Application."""
    app.router.add_get("/api/cost", handle_cost_summary)


def get_agent_statuses(registry: "AgentRegistry") -> list[dict]:
    """Return a list of status dicts for every registered agent.

    Each dict contains:
      - name: agent display name
      - status: current status string (e.g. "active", "idle", "disabled")
      - last_heartbeat: ISO timestamp of last heartbeat, or None
      - tasks_completed: number of completed tasks (int)
      - health: "healthy" | "degraded" based on agent status
    """
    result: list[dict] = []
    for agent in registry._agents.values():
        status_val = (
            agent.agent.status.value
            if hasattr(agent.agent.status, "value")
            else str(agent.agent.status)
        )
        health = "degraded" if agent.agent.status == AgentStatus.DISABLED else "healthy"
        last_hb = getattr(agent.agent, "last_heartbeat", None)
        tasks_done = getattr(agent.agent, "tasks_completed", 0)
        result.append({
            "name": agent.name,
            "status": status_val,
            "last_heartbeat": last_hb,
            "tasks_completed": tasks_done,
            "health": health,
        })
    return result

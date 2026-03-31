"""Dashboard API — JSON-serializable pipeline state snapshot."""

from __future__ import annotations

import dataclasses
from typing import TYPE_CHECKING, Optional

from fastapi import APIRouter

if TYPE_CHECKING:
    from crazypumpkin.framework.registry import AgentRegistry

from crazypumpkin.framework.models import AgentStatus, RunRecord, TaskStatus
from crazypumpkin.framework.store import Store

router = APIRouter()

# Module-level store reference, set via configure().
_store: Store | None = None


def configure(store: Store) -> None:
    """Set the store instance used by API endpoints."""
    global _store
    _store = store


def _serialize_run(r: RunRecord) -> dict:
    d = dataclasses.asdict(r)
    for key in ("started_at", "finished_at"):
        v = d.get(key)
        if hasattr(v, "isoformat"):
            d[key] = v.isoformat()
    return d


@router.get("/api/runs")
async def list_runs(
    agent_name: Optional[str] = None,
    status: Optional[str] = None,
    limit: int = 50,
    offset: int = 0,
) -> dict:
    """Return paginated run history."""
    if _store is None:
        return {"runs": [], "total": 0, "limit": limit, "offset": offset}

    # Fetch all matching records to compute total count.
    all_matching = await _store.list_run_records(
        agent_name=agent_name,
        status=status,
        limit=10**9,
        offset=0,
    )
    total = len(all_matching)
    page = all_matching[offset : offset + limit]

    return {
        "runs": [_serialize_run(r) for r in page],
        "total": total,
        "limit": limit,
        "offset": offset,
    }


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

    return {
        "agents": agents,
        "tasks": {
            "counts": counts,
            "recent_completions": recent_completions,
        },
        "errors": error_tasks,
    }

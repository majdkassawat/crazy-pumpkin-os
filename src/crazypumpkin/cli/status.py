"""Status data collector — gathers agent runtime status for CLI display."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from crazypumpkin.framework.config import load_config
from crazypumpkin.framework.metrics import default_metrics


def collect_status(project_dir: Path) -> dict[str, Any]:
    """Return dict with keys: agents (list of dicts with name, state, last_run,
    error_count), triggers (list of active trigger summaries), metrics (dict of
    counters)."""
    agents: list[dict[str, Any]] = []
    triggers: list[dict[str, Any]] = []
    metrics: dict[str, Any] = {}

    try:
        config = load_config(project_dir)
    except (FileNotFoundError, ValueError, KeyError):
        return {"agents": agents, "triggers": triggers, "metrics": metrics}

    for agent_def in config.agents:
        agent_info: dict[str, Any] = {
            "name": agent_def.name,
            "state": "configured",
            "last_run": None,
            "error_count": 0,
        }
        agents.append(agent_info)

        if agent_def.trigger:
            triggers.append({
                "agent": agent_def.name,
                "expression": agent_def.trigger,
            })

    # Collect metrics counters from the global metrics instance
    for agent_id, count in default_metrics.execution_count.items():
        metrics[agent_id] = {
            "executions": count,
            "errors": default_metrics.error_count.get(agent_id, 0),
            "total_duration": default_metrics.total_duration.get(agent_id, 0.0),
        }

    return {"agents": agents, "triggers": triggers, "metrics": metrics}


def format_status_table(status: dict[str, Any]) -> str:
    """Return a formatted multi-section string for terminal display with agent
    table, trigger summary, and metrics summary."""
    lines: list[str] = []

    # -- Agents section --
    lines.append("Agents")
    lines.append("-" * 60)
    agents = status.get("agents", [])
    if agents:
        lines.append(f"{'Name':<25} {'State':<15} {'Last Run':<12} {'Errors':<6}")
        for a in agents:
            last_run = a.get("last_run") or "never"
            lines.append(
                f"{a['name']:<25} {a['state']:<15} {last_run:<12} {a['error_count']:<6}"
            )
    else:
        lines.append("  No agents configured.")
    lines.append("")

    # -- Triggers section --
    lines.append("Triggers")
    lines.append("-" * 60)
    triggers = status.get("triggers", [])
    if triggers:
        for t in triggers:
            lines.append(f"  {t['agent']}: {t['expression']}")
    else:
        lines.append("  No active triggers.")
    lines.append("")

    # -- Metrics section --
    lines.append("Metrics")
    lines.append("-" * 60)
    metrics = status.get("metrics", {})
    if metrics:
        for agent_id, counters in metrics.items():
            lines.append(
                f"  {agent_id}: "
                f"executions={counters['executions']}, "
                f"errors={counters['errors']}, "
                f"duration={counters['total_duration']:.1f}s"
            )
    else:
        lines.append("  No metrics collected.")

    return "\n".join(lines)

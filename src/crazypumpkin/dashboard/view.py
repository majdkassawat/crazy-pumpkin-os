"""Text-mode dashboard views for Crazy Pumpkin OS."""

from __future__ import annotations

import json
from pathlib import Path


def agents_table(config) -> str:
    """Return a text table of configured agents."""
    agents = getattr(config, "agents", [])
    if not agents:
        return "Agents\n  no agents configured\n"

    lines = ["Agents"]
    lines.append(f"  {'Name':<20} {'Role':<15} {'Model':<10} {'Group':<15}")
    lines.append("  " + "-" * 60)
    for agent in agents:
        name = getattr(agent, "name", "")
        role = getattr(agent, "role", "")
        model = getattr(agent, "model", "")
        group = getattr(agent, "group", "")
        lines.append(f"  {name:<20} {role:<15} {model:<10} {group:<15}")
    return "\n".join(lines) + "\n"


def tasks_table(store) -> str:
    """Return a text table of tasks in the store."""
    tasks = getattr(store, "tasks", {}) if store is not None else {}
    if not tasks:
        return "Tasks\n  no tasks in store\n"

    lines = ["Tasks"]
    lines.append(f"  {'ID':<12} {'Title':<30} {'Status':<15} {'Assigned':<15}")
    lines.append("  " + "-" * 72)
    for task in tasks.values():
        tid = getattr(task, "id", "")
        title = getattr(task, "title", "")
        status = task.status.value if hasattr(task.status, "value") else str(getattr(task, "status", ""))
        assigned = getattr(task, "assigned_to", "") or ""
        lines.append(f"  {tid:<12} {title:<30} {status:<15} {assigned:<15}")
    return "\n".join(lines) + "\n"


def scheduler_table(data_dir: Path) -> str:
    """Return a text table of scheduler state from data_dir/scheduler_state.json."""
    state_file = Path(data_dir) / "scheduler_state.json"
    if not state_file.exists():
        return "Scheduler\n  scheduler state not found\n"

    try:
        state = json.loads(state_file.read_text(encoding="utf-8"))
    except Exception:
        return "Scheduler\n  scheduler state not found\n"

    lines = ["Scheduler"]
    last_run = state.get("last_run", "—")
    cycle_count = state.get("cycle_count", 0)
    lines.append(f"  Last run:    {last_run}")
    lines.append(f"  Cycle count: {cycle_count}")
    dispatches = state.get("agent_last_dispatch", {})
    if dispatches:
        lines.append("  Agent dispatches:")
        for agent, ts in dispatches.items():
            lines.append(f"    {agent}: {ts}")
    return "\n".join(lines) + "\n"


def logs_table(data_dir: Path, n: int = 20) -> str:
    """Return a text table of recent log lines from data_dir/pipeline.log."""
    log_file = Path(data_dir) / "pipeline.log"
    if not log_file.exists():
        return "Logs\n  no log file found\n"

    try:
        content = log_file.read_text(encoding="utf-8")
        log_lines = [line for line in content.splitlines() if line.strip()][-n:]
    except Exception:
        return "Logs\n  no log file found\n"

    lines = ["Logs"]
    for line in log_lines:
        lines.append(f"  {line}")
    return "\n".join(lines) + "\n"


def render_dashboard(config, data_dir: Path, store=None) -> str:
    """Render a complete dashboard snapshot as a string."""
    company = getattr(config, "company", {})
    company_name = company.get("name", "Unknown") if isinstance(company, dict) else str(company)

    sections = [
        f"=== Crazy Pumpkin OS — {company_name} ===",
        "",
        agents_table(config),
        tasks_table(store),
        scheduler_table(data_dir),
        logs_table(data_dir),
    ]
    return "\n".join(sections)

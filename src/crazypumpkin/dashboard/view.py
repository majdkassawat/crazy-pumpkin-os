"""Dashboard view — stdlib-only formatted summary tables for agents, tasks, scheduler, and logs."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def _table(headers: list[str], rows: list[list[str]], *, title: str = "") -> str:
    """Render a plain-text table using stdlib only."""
    all_rows = [headers] + rows
    widths = [max(len(str(r[i])) for r in all_rows) for i in range(len(headers))]
    sep = "+" + "+".join("-" * (w + 2) for w in widths) + "+"
    fmt = "|" + "|".join(f" {{:<{w}}} " for w in widths) + "|"

    lines = []
    if title:
        lines.append(f"\n  {title}")
    lines.append(sep)
    lines.append(fmt.format(*headers))
    lines.append(sep)
    for row in rows:
        lines.append(fmt.format(*[str(v) for v in row]))
    lines.append(sep)
    return "\n".join(lines)


# ── Accessors ────────────────────────────────────────────────────────────────

def agents_table(config: Any) -> str:
    """Formatted table of configured agents."""
    headers = ["Name", "Role", "Model", "Group", "Class"]
    rows = []
    for a in getattr(config, "agents", []):
        rows.append([
            getattr(a, "name", ""),
            getattr(a, "role", ""),
            getattr(a, "model", ""),
            getattr(a, "group", ""),
            getattr(a, "class_path", ""),
        ])
    if not rows:
        return "  [no agents configured]"
    return _table(headers, rows, title="Agents")


def tasks_table(store: Any) -> str:
    """Formatted table of tasks from the store."""
    headers = ["ID", "Title", "Status", "Assigned To", "Project"]
    rows = []
    for task in store.tasks.values():
        status = task.status.value if hasattr(task.status, "value") else str(task.status)
        rows.append([
            str(task.id)[:10],
            str(task.title)[:40],
            status,
            str(task.assigned_to or "")[:16],
            str(task.project_id)[:10],
        ])
    if not rows:
        return "  [no tasks in store]"
    return _table(headers, rows, title="Tasks")


def scheduler_table(data_dir: Path) -> str:
    """Formatted scheduler status from scheduler_state.json."""
    state_path = data_dir / "scheduler_state.json"
    if not state_path.exists():
        return "  [scheduler state not found — pipeline not yet run]"
    try:
        state: dict[str, Any] = json.loads(state_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return "  [scheduler state unreadable]"

    headers = ["Key", "Value"]
    rows = [
        ["last_run", state.get("last_run") or "never"],
        ["cycle_count", str(state.get("cycle_count", 0))],
    ]
    for agent, ts in state.get("agent_last_dispatch", {}).items():
        rows.append([f"  last_dispatch/{agent}", str(ts)])
    return _table(headers, rows, title="Scheduler")


def logs_table(data_dir: Path, *, n: int = 20) -> str:
    """Last *n* lines from the pipeline log file (if present)."""
    log_path = data_dir / "pipeline.log"
    if not log_path.exists():
        return "  [no log file found at data/pipeline.log]"
    try:
        lines = log_path.read_text(encoding="utf-8", errors="replace").splitlines()
        recent = lines[-n:] if len(lines) > n else lines
    except OSError:
        return "  [log file unreadable]"

    if not recent:
        return "  [log file is empty]"
    return "\n  Logs (last {})\n  {}\n  {}".format(
        len(recent),
        "-" * 60,
        "\n  ".join(recent),
    )


def render_dashboard(config: Any, data_dir: Path, store: Any | None = None) -> str:
    """Return a full dashboard string for the given config and data directory."""
    sections: list[str] = []
    company_name = config.company.get("name", "?") if hasattr(config, "company") else "?"
    sections.append(f"\n{'='*60}")
    sections.append(f"  Crazy Pumpkin OS — {company_name}")
    sections.append(f"{'='*60}")

    sections.append(agents_table(config))

    if store is not None:
        sections.append(tasks_table(store))

    sections.append(scheduler_table(data_dir))
    sections.append(logs_table(data_dir))
    return "\n".join(sections)

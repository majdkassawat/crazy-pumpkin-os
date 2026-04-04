"""Tests for dashboard text-mode view rendering."""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from crazypumpkin.dashboard.view import (
    agents_table,
    logs_table,
    render_dashboard,
    scheduler_table,
    tasks_table,
)
from crazypumpkin.framework.models import TaskStatus


# ── Helpers ──


def _make_agent_ns(name="agent-1", role="execution", model="gpt-4", group="core"):
    return SimpleNamespace(name=name, role=role, model=model, group=group)


def _make_config(agents=None, company=None):
    if company is None:
        company = {"name": "TestCo"}
    return SimpleNamespace(agents=agents or [], company=company)


def _make_task(tid="t1", title="Fix bug", status=TaskStatus.CREATED, assigned_to="agent-1"):
    return SimpleNamespace(id=tid, title=title, status=status, assigned_to=assigned_to)


def _make_store(tasks=None):
    store = SimpleNamespace()
    if tasks is None:
        store.tasks = {}
    else:
        store.tasks = {t.id: t for t in tasks}
    return store


# ── agents_table ──


class TestAgentsTable:
    def test_empty_agents_list(self):
        config = _make_config(agents=[])
        result = agents_table(config)
        assert "no agents configured" in result

    def test_single_agent_row(self):
        config = _make_config(agents=[_make_agent_ns(name="writer")])
        result = agents_table(config)
        assert "writer" in result
        assert "Agents" in result

    def test_multiple_agents(self):
        agents = [
            _make_agent_ns(name="writer", role="execution"),
            _make_agent_ns(name="reviewer", role="review"),
        ]
        config = _make_config(agents=agents)
        result = agents_table(config)
        assert "writer" in result
        assert "reviewer" in result

    def test_header_present(self):
        config = _make_config(agents=[_make_agent_ns()])
        result = agents_table(config)
        assert "Name" in result
        assert "Role" in result

    def test_no_agents_attr(self):
        """Config with no agents attribute shows empty state."""
        config = SimpleNamespace()
        result = agents_table(config)
        assert "no agents configured" in result


# ── tasks_table ──


class TestTasksTable:
    def test_empty_tasks(self):
        store = _make_store()
        result = tasks_table(store)
        assert "no tasks in store" in result

    def test_single_task(self):
        store = _make_store([_make_task(tid="t1", title="Fix bug")])
        result = tasks_table(store)
        assert "Fix bug" in result
        assert "t1" in result

    def test_none_store(self):
        result = tasks_table(None)
        assert "no tasks in store" in result

    def test_multiple_tasks_with_mixed_status(self):
        tasks = [
            _make_task(tid="t1", title="Task A", status=TaskStatus.COMPLETED),
            _make_task(tid="t2", title="Task B", status=TaskStatus.REJECTED),
            _make_task(tid="t3", title="Task C", status=TaskStatus.IN_PROGRESS),
        ]
        store = _make_store(tasks)
        result = tasks_table(store)
        assert "Task A" in result
        assert "Task B" in result
        assert "Task C" in result

    def test_header_row(self):
        store = _make_store([_make_task()])
        result = tasks_table(store)
        assert "ID" in result
        assert "Title" in result
        assert "Status" in result


# ── scheduler_table ──


class TestSchedulerTable:
    def test_missing_state_file(self, tmp_path):
        result = scheduler_table(tmp_path)
        assert "scheduler state not found" in result

    def test_valid_state_file(self, tmp_path):
        state = {"last_run": "2026-01-01T00:00:00", "cycle_count": 5}
        (tmp_path / "scheduler_state.json").write_text(json.dumps(state))
        result = scheduler_table(tmp_path)
        assert "2026-01-01" in result
        assert "5" in result

    def test_corrupt_state_file(self, tmp_path):
        (tmp_path / "scheduler_state.json").write_text("not json at all {{{")
        result = scheduler_table(tmp_path)
        assert "scheduler state not found" in result


# ── logs_table ──


class TestLogsTable:
    def test_missing_log_file(self, tmp_path):
        result = logs_table(tmp_path)
        assert "no log file found" in result

    def test_log_lines_shown(self, tmp_path):
        (tmp_path / "pipeline.log").write_text("line1\nline2\nline3\n")
        result = logs_table(tmp_path)
        assert "line1" in result
        assert "line3" in result

    def test_respects_n_limit(self, tmp_path):
        lines = "\n".join(f"log-{i}" for i in range(50))
        (tmp_path / "pipeline.log").write_text(lines)
        result = logs_table(tmp_path, n=5)
        # Should only contain the last 5 lines
        assert "log-49" in result
        assert "log-45" in result
        assert "log-0" not in result


# ── render_dashboard ──


class TestRenderDashboard:
    def test_includes_company_name(self, tmp_path):
        config = _make_config(company={"name": "Acme"})
        result = render_dashboard(config, tmp_path, store=_make_store())
        assert "Acme" in result

    def test_includes_agents_section(self, tmp_path):
        config = _make_config(agents=[_make_agent_ns(name="bot-1")])
        result = render_dashboard(config, tmp_path, store=_make_store())
        assert "bot-1" in result

    def test_empty_dashboard(self, tmp_path):
        config = _make_config()
        result = render_dashboard(config, tmp_path, store=_make_store())
        assert "Crazy Pumpkin OS" in result
        assert "no agents configured" in result
        assert "no tasks in store" in result

    def test_mixed_health_agents(self, tmp_path):
        """Dashboard with agents of various health states renders without error."""
        agents = [
            _make_agent_ns(name="healthy-1"),
            _make_agent_ns(name="degraded-1"),
        ]
        tasks = [
            _make_task(tid="t1", title="OK task", status=TaskStatus.COMPLETED),
            _make_task(tid="t2", title="Bad task", status=TaskStatus.REJECTED),
        ]
        config = _make_config(agents=agents)
        store = _make_store(tasks)
        result = render_dashboard(config, tmp_path, store=store)
        assert "healthy-1" in result
        assert "degraded-1" in result
        assert "OK task" in result
        assert "Bad task" in result

    def test_unknown_company_fallback(self, tmp_path):
        config = _make_config(company={})
        result = render_dashboard(config, tmp_path)
        assert "Unknown" in result

    def test_output_is_string(self, tmp_path):
        config = _make_config()
        result = render_dashboard(config, tmp_path)
        assert isinstance(result, str)

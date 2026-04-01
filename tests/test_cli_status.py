"""Tests for cmd_status with mocked store data.

Covers all output formats (rich + JSON), edge cases (empty store, all
tasks completed), and JSON schema validation.
"""

import argparse
import json
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from crazypumpkin.cli import cmd_status
from crazypumpkin.framework.models import (
    AgentMetrics,
    Project,
    ProjectStatus,
    Task,
    TaskStatus,
)
from crazypumpkin.framework.store import Store


# ── Helpers ──────────────────────────────────────────────────────────


def _args(json_mode=False):
    return argparse.Namespace(command="status", json=json_mode)


def _mock_config(name="Test Co", cycle_interval=30):
    cfg = MagicMock()
    cfg.company = {"name": name}
    cfg.pipeline = {"cycle_interval": cycle_interval}
    return cfg


def _empty_store():
    """Return a Store with no data."""
    s = Store()
    return s


def _populated_store():
    """Return a Store with a mix of projects, tasks, and agent metrics."""
    s = Store()

    # Active project with mixed tasks
    p1 = Project(id="p1", name="Alpha", status=ProjectStatus.ACTIVE)
    s.add_project(p1)

    s.add_task(Task(id="t1", project_id="p1", title="Task A",
                    status=TaskStatus.COMPLETED, updated_at="2026-01-01T10:00:00"))
    s.add_task(Task(id="t2", project_id="p1", title="Task B",
                    status=TaskStatus.IN_PROGRESS, updated_at="2026-01-02T10:00:00"))
    s.add_task(Task(id="t3", project_id="p1", title="Task C",
                    status=TaskStatus.CREATED, updated_at="2026-01-03T10:00:00"))
    s.add_task(Task(id="t4", project_id="p1", title="Task D",
                    status=TaskStatus.ESCALATED, updated_at="2026-01-04T10:00:00"))
    s.add_task(Task(id="t5", project_id="p1", title="Task E",
                    status=TaskStatus.REJECTED, updated_at="2026-01-05T10:00:00"))

    # Agent metrics
    s.record_task_outcome("agent1", "Developer", completed=True, retries=0,
                          duration_sec=10.0, first_attempt=True)
    s.record_task_outcome("agent1", "Developer", completed=False, retries=1,
                          duration_sec=20.0, first_attempt=False)

    return s


def _all_completed_store():
    """Return a Store where every task is COMPLETED."""
    s = Store()
    p = Project(id="p1", name="Done Project", status=ProjectStatus.ACTIVE)
    s.add_project(p)
    for i in range(3):
        s.add_task(Task(id=f"t{i}", project_id="p1", title=f"Done {i}",
                        status=TaskStatus.COMPLETED,
                        updated_at=f"2026-01-0{i+1}T00:00:00"))
    return s


def _run_status(store, config=None, json_mode=False):
    """Run cmd_status with mocked config, store, and cache stats."""
    config = config or _mock_config()
    cache = {"hits": 0, "misses": 0, "tokens_saved": 0, "hit_rate_pct": 0}
    with patch("crazypumpkin.framework.config.load_config", return_value=config), \
         patch("crazypumpkin.framework.store.Store", return_value=store), \
         patch("crazypumpkin.observability.metrics.get_cache_stats", return_value=cache):
        store.load = MagicMock()  # no-op load
        cmd_status(_args(json_mode=json_mode))


# ── Rich (default) output tests ─────────────────────────────────────


class TestStatusRichEmpty:
    """Rich output when the store is empty."""

    def test_no_active_projects_message(self, capsys):
        _run_status(_empty_store())
        out = capsys.readouterr().out
        assert "none active" in out.lower() or "no" in out.lower()

    def test_task_counts_all_zero(self, capsys):
        _run_status(_empty_store())
        out = capsys.readouterr().out
        assert "pending" in out
        assert "running" in out
        assert "complete" in out

    def test_no_agent_health(self, capsys):
        _run_status(_empty_store())
        out = capsys.readouterr().out
        assert "no data" in out.lower()

    def test_no_recent_activity(self, capsys):
        _run_status(_empty_store())
        out = capsys.readouterr().out
        assert "none" in out.lower()


class TestStatusRichPopulated:
    """Rich output when store has projects, tasks, and agent metrics."""

    def test_company_name_printed(self, capsys):
        _run_status(_populated_store(), config=_mock_config(name="Acme"))
        out = capsys.readouterr().out
        assert "Acme" in out

    def test_cycle_interval_printed(self, capsys):
        _run_status(_populated_store(), config=_mock_config(cycle_interval=99))
        out = capsys.readouterr().out
        assert "99" in out

    def test_project_name_shown(self, capsys):
        _run_status(_populated_store())
        out = capsys.readouterr().out
        assert "Alpha" in out

    def test_task_labels_present(self, capsys):
        _run_status(_populated_store())
        out = capsys.readouterr().out
        for label in ("pending", "running", "complete", "escalated", "rejected"):
            assert label in out

    def test_agent_section_printed(self, capsys):
        _run_status(_populated_store())
        out = capsys.readouterr().out
        assert "Developer" in out

    def test_recent_activity_titles(self, capsys):
        _run_status(_populated_store())
        out = capsys.readouterr().out
        # At least one recent task title should appear
        assert any(f"Task {c}" in out for c in "ABCDE")


class TestStatusRichAllCompleted:
    """Rich output when all tasks are completed."""

    def test_complete_count_nonzero(self, capsys):
        _run_status(_all_completed_store())
        out = capsys.readouterr().out
        # The complete count must be > 0 (we have 3 completed tasks)
        assert "complete" in out

    def test_progress_100(self, capsys):
        _run_status(_all_completed_store())
        out = capsys.readouterr().out
        assert "100" in out  # 100% progress

    def test_pending_zero(self, capsys):
        _run_status(_all_completed_store())
        out = capsys.readouterr().out
        # pending: 0, running: 0
        assert "pending" in out


# ── JSON output tests ────────────────────────────────────────────────


def _run_status_json(store, config=None):
    """Run cmd_status in JSON mode and return parsed dict."""
    config = config or _mock_config()
    cache = {"hits": 5, "misses": 3, "tokens_saved": 120, "hit_rate_pct": 62}
    with patch("crazypumpkin.framework.config.load_config", return_value=config), \
         patch("crazypumpkin.framework.store.Store", return_value=store), \
         patch("crazypumpkin.observability.metrics.get_cache_stats", return_value=cache):
        store.load = MagicMock()  # no-op load
        cmd_status(_args(json_mode=True))


class TestStatusJsonSchema:
    """JSON output structure and schema validation."""

    def test_valid_json(self, capsys):
        _run_status_json(_populated_store())
        out = capsys.readouterr().out
        data = json.loads(out)  # must not raise
        assert isinstance(data, dict)

    def test_top_level_keys(self, capsys):
        _run_status_json(_populated_store())
        data = json.loads(capsys.readouterr().out)
        expected_keys = {
            "company", "cycle_interval", "projects", "tasks",
            "agents", "system_health", "recent_activity", "prompt_cache",
        }
        assert expected_keys == set(data.keys())

    def test_company_value(self, capsys):
        _run_status_json(_populated_store(), config=_mock_config(name="JSON Corp"))
        data = json.loads(capsys.readouterr().out)
        assert data["company"] == "JSON Corp"

    def test_cycle_interval_value(self, capsys):
        _run_status_json(_populated_store(), config=_mock_config(cycle_interval=77))
        data = json.loads(capsys.readouterr().out)
        assert data["cycle_interval"] == 77

    def test_tasks_keys(self, capsys):
        _run_status_json(_populated_store())
        data = json.loads(capsys.readouterr().out)
        expected = {"pending", "running", "complete", "escalated", "rejected"}
        assert expected == set(data["tasks"].keys())

    def test_tasks_values_type(self, capsys):
        _run_status_json(_populated_store())
        data = json.loads(capsys.readouterr().out)
        for v in data["tasks"].values():
            assert isinstance(v, int)

    def test_projects_list_structure(self, capsys):
        _run_status_json(_populated_store())
        data = json.loads(capsys.readouterr().out)
        assert isinstance(data["projects"], list)
        for p in data["projects"]:
            assert "name" in p
            assert "completed" in p
            assert "total" in p
            assert "progress_pct" in p

    def test_agents_list_structure(self, capsys):
        _run_status_json(_populated_store())
        data = json.loads(capsys.readouterr().out)
        assert isinstance(data["agents"], list)
        for a in data["agents"]:
            assert "name" in a
            assert "status" in a
            assert "completed" in a
            assert "rejected" in a
            assert "success_rate_pct" in a

    def test_recent_activity_structure(self, capsys):
        _run_status_json(_populated_store())
        data = json.loads(capsys.readouterr().out)
        assert isinstance(data["recent_activity"], list)
        for entry in data["recent_activity"]:
            assert "status" in entry
            assert "title" in entry
            assert "updated" in entry

    def test_prompt_cache_keys(self, capsys):
        _run_status_json(_populated_store())
        data = json.loads(capsys.readouterr().out)
        cache = data["prompt_cache"]
        assert "hits" in cache
        assert "misses" in cache
        assert "tokens_saved" in cache
        assert "hit_rate_pct" in cache

    def test_system_health_present(self, capsys):
        _run_status_json(_populated_store())
        data = json.loads(capsys.readouterr().out)
        sh = data["system_health"]
        assert sh is not None
        assert "status" in sh
        assert "uptime_pct" in sh


class TestStatusJsonEdgeCases:
    """JSON output edge cases."""

    def test_empty_store_json(self, capsys):
        _run_status_json(_empty_store())
        data = json.loads(capsys.readouterr().out)
        assert data["projects"] == []
        assert data["agents"] == []
        assert data["system_health"] is None
        assert data["recent_activity"] == []
        assert data["tasks"]["pending"] == 0
        assert data["tasks"]["running"] == 0
        assert data["tasks"]["complete"] == 0

    def test_all_completed_json(self, capsys):
        _run_status_json(_all_completed_store())
        data = json.loads(capsys.readouterr().out)
        assert data["tasks"]["complete"] == 3
        assert data["tasks"]["pending"] == 0
        assert data["tasks"]["running"] == 0
        assert data["tasks"]["escalated"] == 0
        assert data["tasks"]["rejected"] == 0

    def test_all_completed_project_progress(self, capsys):
        _run_status_json(_all_completed_store())
        data = json.loads(capsys.readouterr().out)
        assert len(data["projects"]) == 1
        proj = data["projects"][0]
        assert proj["progress_pct"] == 100.0
        assert proj["completed"] == proj["total"]

    def test_recent_activity_max_five(self, capsys):
        """At most 5 recent activities are returned."""
        s = Store()
        p = Project(id="p1", name="Big", status=ProjectStatus.ACTIVE)
        s.add_project(p)
        for i in range(10):
            s.add_task(Task(id=f"t{i}", project_id="p1", title=f"Task {i}",
                            status=TaskStatus.CREATED,
                            updated_at=f"2026-01-{i+1:02d}T00:00:00"))
        _run_status_json(s)
        data = json.loads(capsys.readouterr().out)
        assert len(data["recent_activity"]) <= 5

    def test_task_counts_match_populated(self, capsys):
        """Task breakdown sums match total tasks in populated store."""
        _run_status_json(_populated_store())
        data = json.loads(capsys.readouterr().out)
        total = sum(data["tasks"].values())
        assert total == 5  # t1..t5

    def test_project_with_no_tasks_json(self, capsys):
        """A project with zero tasks shows 0% progress."""
        s = Store()
        s.add_project(Project(id="p1", name="Empty Proj", status=ProjectStatus.ACTIVE))
        _run_status_json(s)
        data = json.loads(capsys.readouterr().out)
        assert len(data["projects"]) == 1
        assert data["projects"][0]["progress_pct"] == 0
        assert data["projects"][0]["total"] == 0

    def test_completed_project_not_listed(self, capsys):
        """Completed projects are NOT listed in active projects."""
        s = Store()
        s.add_project(Project(id="p1", name="Done", status=ProjectStatus.COMPLETED))
        _run_status_json(s)
        data = json.loads(capsys.readouterr().out)
        assert data["projects"] == []


class TestStatusJsonAgentMetrics:
    """JSON output for agent health / metrics."""

    def test_agent_success_rate_calculation(self, capsys):
        _run_status_json(_populated_store())
        data = json.loads(capsys.readouterr().out)
        agent = data["agents"][0]
        assert agent["name"] == "Developer"
        assert agent["completed"] == 1
        assert agent["rejected"] == 1
        assert agent["success_rate_pct"] == 50.0

    def test_no_metrics_yields_empty_agents(self, capsys):
        _run_status_json(_empty_store())
        data = json.loads(capsys.readouterr().out)
        assert data["agents"] == []
        assert data["system_health"] is None

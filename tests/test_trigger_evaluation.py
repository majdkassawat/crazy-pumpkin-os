"""Tests for trigger expression parsing, evaluation, and integration with Scheduler."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from unittest import mock

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from crazypumpkin.framework.config import Config
from crazypumpkin.scheduler.scheduler import Scheduler, _eval_trigger


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_config(products=None):
    return Config(
        company={"name": "TestCo"},
        products=products or [],
        llm={
            "default_provider": "anthropic_api",
            "providers": {"anthropic_api": {"api_key": "fake"}},
            "agent_models": {},
        },
        agents=[{"name": "TestAgent", "role": "strategy"}],
    )


def _seed_store(data_dir: Path, n_tasks: int = 3) -> None:
    """Write a state.json with *n_tasks* CREATED tasks (pending goals)."""
    tasks = {}
    for i in range(n_tasks):
        tid = f"task{i}"
        tasks[tid] = {
            "id": tid,
            "project_id": "proj1",
            "title": f"Task {i}",
            "description": f"Description {i}",
            "status": "created",
            "assigned_to": "",
            "priority": 3,
            "dependencies": [],
            "acceptance_criteria": ["criterion"],
            "output": None,
            "created_at": "2025-01-01T00:00:00+00:00",
            "updated_at": "2025-01-01T00:00:00+00:00",
            "history": [],
            "blocked_by": "",
        }
    state = {
        "projects": {},
        "tasks": tasks,
        "reviews": {},
        "approvals": {},
        "proposals": {},
        "agent_metrics": {},
    }
    data_dir.mkdir(parents=True, exist_ok=True)
    (data_dir / "state.json").write_text(json.dumps(state), encoding="utf-8")


# ---------------------------------------------------------------------------
# Unit tests — _eval_trigger: comparison operators
# ---------------------------------------------------------------------------


class TestEvalTriggerOperators:
    """Each of the six comparison operators has at least one passing test."""

    def test_gt_true(self):
        assert _eval_trigger("x > 5", {"x": 10}) is True

    def test_gt_false(self):
        assert _eval_trigger("x > 5", {"x": 5}) is False

    def test_lt_true(self):
        assert _eval_trigger("x < 5", {"x": 3}) is True

    def test_lt_false(self):
        assert _eval_trigger("x < 5", {"x": 5}) is False

    def test_gte_true_equal(self):
        assert _eval_trigger("x >= 5", {"x": 5}) is True

    def test_gte_true_greater(self):
        assert _eval_trigger("x >= 5", {"x": 6}) is True

    def test_gte_false(self):
        assert _eval_trigger("x >= 5", {"x": 4}) is False

    def test_lte_true_equal(self):
        assert _eval_trigger("x <= 5", {"x": 5}) is True

    def test_lte_true_less(self):
        assert _eval_trigger("x <= 5", {"x": 4}) is True

    def test_lte_false(self):
        assert _eval_trigger("x <= 5", {"x": 6}) is False

    def test_eq_true(self):
        assert _eval_trigger("x == 7", {"x": 7}) is True

    def test_eq_false(self):
        assert _eval_trigger("x == 7", {"x": 8}) is False

    def test_ne_true(self):
        assert _eval_trigger("x != 7", {"x": 8}) is True

    def test_ne_false(self):
        assert _eval_trigger("x != 7", {"x": 7}) is False


# ---------------------------------------------------------------------------
# Unit tests — _eval_trigger: edge cases
# ---------------------------------------------------------------------------


class TestEvalTriggerEdgeCases:
    """Empty string, unknown keys, malformed input."""

    def test_empty_string_returns_true(self):
        assert _eval_trigger("", {}) is True

    def test_whitespace_only_returns_true(self):
        assert _eval_trigger("   ", {}) is True

    def test_none_like_empty_returns_true(self):
        # Empty string with context still returns True
        assert _eval_trigger("", {"backlog": 5}) is True

    def test_unknown_context_key_raises_valueerror(self):
        """An unknown key in the expression raises ValueError."""
        with pytest.raises(ValueError, match="Unknown context key"):
            _eval_trigger("missing_key > 0", {"backlog": 1})

    def test_unknown_key_defaults_to_zero_in_scheduler_context(self):
        """Scheduler provides cycle_count defaulting to 0 for a fresh instance."""
        scheduler = Scheduler(_make_config())
        # cycle_count defaults to 0 on a fresh scheduler
        assert scheduler.cycle_count == 0
        agent_def = {"name": "a", "trigger": "cycle_count == 0"}
        assert scheduler._has_priority_backlog(agent_def, 0) is True

    def test_malformed_expression_raises_valueerror(self):
        with pytest.raises(ValueError, match="Malformed trigger expression"):
            _eval_trigger("this is not valid", {"x": 1})

    def test_malformed_no_operator_raises(self):
        with pytest.raises(ValueError, match="Malformed trigger expression"):
            _eval_trigger("backlog", {"backlog": 1})

    def test_malformed_operator_only_raises(self):
        with pytest.raises(ValueError, match="Malformed trigger expression"):
            _eval_trigger("> 5", {"x": 1})

    def test_float_coercion(self):
        assert _eval_trigger("score >= 0.5", {"score": 0.75}) is True

    def test_string_equality(self):
        assert _eval_trigger("status == active", {"status": "active"}) is True

    def test_string_inequality(self):
        assert _eval_trigger("status != active", {"status": "idle"}) is True


# ---------------------------------------------------------------------------
# Integration test — Scheduler._has_priority_backlog with seeded store
# ---------------------------------------------------------------------------


class TestHasPriorityBacklogIntegration:
    """Integration: seed a store, build a Scheduler, and verify trigger-bearing
    agents are correctly skipped or run based on pending task count."""

    def test_agent_with_trigger_runs_when_backlog_present(self, tmp_path):
        workspace = tmp_path / "ws"
        data_dir = workspace / "data"
        _seed_store(data_dir, n_tasks=3)

        config = _make_config(
            products=[{"name": "App", "workspace": str(workspace)}]
        )
        scheduler = Scheduler(config)

        # Agent has a trigger requiring backlog > 0
        agent_def = {"name": "dev", "trigger": "backlog > 0"}
        assert scheduler._has_priority_backlog(agent_def, pending_count=3) is True

    def test_agent_with_trigger_skipped_when_no_backlog(self, tmp_path):
        workspace = tmp_path / "ws"
        data_dir = workspace / "data"
        _seed_store(data_dir, n_tasks=0)

        config = _make_config(
            products=[{"name": "App", "workspace": str(workspace)}]
        )
        scheduler = Scheduler(config)

        agent_def = {"name": "dev", "trigger": "backlog > 0"}
        assert scheduler._has_priority_backlog(agent_def, pending_count=0) is False

    def test_agent_without_trigger_always_runs(self, tmp_path):
        workspace = tmp_path / "ws"
        data_dir = workspace / "data"
        _seed_store(data_dir, n_tasks=0)

        config = _make_config(
            products=[{"name": "App", "workspace": str(workspace)}]
        )
        scheduler = Scheduler(config)

        agent_def = {"name": "dev"}
        assert scheduler._has_priority_backlog(agent_def, pending_count=0) is True

    def test_agent_trigger_cycle_count_threshold(self, tmp_path):
        workspace = tmp_path / "ws"
        data_dir = workspace / "data"
        _seed_store(data_dir, n_tasks=1)

        config = _make_config(
            products=[{"name": "App", "workspace": str(workspace)}]
        )
        scheduler = Scheduler(config)
        scheduler.cycle_count = 5

        # Only run when cycle_count >= 5
        agent_def = {"name": "weekly", "trigger": "cycle_count >= 5"}
        assert scheduler._has_priority_backlog(agent_def, pending_count=1) is True

        scheduler.cycle_count = 4
        assert scheduler._has_priority_backlog(agent_def, pending_count=1) is False

    def test_agent_trigger_combined_with_seeded_store_load(self, tmp_path):
        """Full integration: seed store, load it, count pending tasks, check trigger."""
        from crazypumpkin.framework.store import Store

        workspace = tmp_path / "ws"
        data_dir = workspace / "data"
        _seed_store(data_dir, n_tasks=5)

        # Load the store and count pending tasks
        store = Store(data_dir=data_dir)
        store.load()
        pending = [t for t in store.tasks.values() if t.status.value == "created"]
        pending_count = len(pending)
        assert pending_count == 5

        config = _make_config(
            products=[{"name": "App", "workspace": str(workspace)}]
        )
        scheduler = Scheduler(config)

        # Agent that only runs when backlog >= 3
        agent_def = {"name": "bulk_dev", "trigger": "backlog >= 3"}
        assert scheduler._has_priority_backlog(agent_def, pending_count) is True

        # Agent that only runs when backlog < 2 — should be skipped
        agent_def_selective = {"name": "small_dev", "trigger": "backlog < 2"}
        assert scheduler._has_priority_backlog(agent_def_selective, pending_count) is False

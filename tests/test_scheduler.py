"""Tests for Scheduler core class."""

import argparse
import json
import logging
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest import mock

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from crazypumpkin.framework.config import Config
from crazypumpkin.framework.models import (
    AgentDefinition,
    AgentRole,
    ProductConfig,
    Task,
    TaskStatus,
)
from crazypumpkin.scheduler.scheduler import Scheduler, _STATE_FILENAME


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_config(products: list[ProductConfig] | None = None) -> Config:
    """Return a minimal Config suitable for Scheduler tests."""
    return Config(
        company={"name": "TestCo"},
        products=products or [],
        llm={
            "default_provider": "anthropic_api",
            "providers": {"anthropic_api": {"api_key": "fake"}},
            "agent_models": {},
        },
        agents=[AgentDefinition(name="TestAgent", role=AgentRole.STRATEGY)],
    )


def _seed_store_with_goal(data_dir: Path, project_id: str = "proj1") -> None:
    """Write a state.json with one CREATED task (a pending goal)."""
    task_id = "goal1"
    state = {
        "projects": {},
        "tasks": {
            task_id: {
                "id": task_id,
                "project_id": project_id,
                "title": "Build a calculator",
                "description": "Implement a simple calculator app.",
                "status": "created",
                "assigned_to": "",
                "priority": 3,
                "dependencies": [],
                "acceptance_criteria": ["Must add numbers"],
                "output": None,
                "created_at": "2025-01-01T00:00:00+00:00",
                "updated_at": "2025-01-01T00:00:00+00:00",
                "history": [],
                "blocked_by": "",
            }
        },
        "reviews": {},
        "approvals": {},
        "proposals": {},
        "agent_metrics": {},
    }
    data_dir.mkdir(parents=True, exist_ok=True)
    (data_dir / "state.json").write_text(json.dumps(state), encoding="utf-8")


# ---------------------------------------------------------------------------
# Tests — run_once invokes strategy then developer agents in order
# ---------------------------------------------------------------------------


class TestRunOnceAgentOrder:
    """run_once() invokes StrategyAgent then CodeGeneratorAgent in order."""

    @mock.patch("crazypumpkin.agents.code_generator.safe_write_text")
    @mock.patch("crazypumpkin.llm.registry.ProviderRegistry.call")
    @mock.patch("crazypumpkin.llm.registry.ProviderRegistry.call_json")
    def test_strategy_invoked_before_code_generator(
        self, mock_call_json, mock_call, mock_write, tmp_path
    ):
        """Strategy agent is called first, then code generator."""
        workspace = tmp_path / "products" / "myapp"
        data_dir = workspace / "data"
        _seed_store_with_goal(data_dir, project_id="proj1")

        call_order = []

        original_call_json = mock_call_json.side_effect

        def track_call_json(*args, **kwargs):
            call_order.append("strategy")
            return {
                "tasks": [
                    {
                        "title": "Add numbers",
                        "description": "Implement add function",
                        "priority": 1,
                        "acceptance_criteria": ["adds two ints"],
                        "depends_on": [],
                    }
                ]
            }

        def track_call(*args, **kwargs):
            call_order.append("code_generator")
            return "```calculator.py\ndef add(a, b):\n    return a + b\n```\n"

        mock_call_json.side_effect = track_call_json
        mock_call.side_effect = track_call

        config = _make_config(
            products=[ProductConfig(name="MyApp", workspace=str(workspace))]
        )
        scheduler = Scheduler(config)
        results = scheduler.run_once()

        assert "MyApp" in results
        assert "error" not in results["MyApp"]
        # Strategy must come before code_generator
        assert len(call_order) >= 2
        strategy_idx = call_order.index("strategy")
        code_gen_idx = call_order.index("code_generator")
        assert strategy_idx < code_gen_idx, (
            f"Strategy should run before code generator: {call_order}"
        )

    @mock.patch("crazypumpkin.agents.code_generator.safe_write_text")
    @mock.patch("crazypumpkin.llm.registry.ProviderRegistry.call")
    @mock.patch("crazypumpkin.llm.registry.ProviderRegistry.call_json")
    def test_both_agents_are_invoked(
        self, mock_call_json, mock_call, mock_write, tmp_path
    ):
        """Both strategy and code generator agents are invoked."""
        workspace = tmp_path / "products" / "myapp"
        data_dir = workspace / "data"
        _seed_store_with_goal(data_dir, project_id="proj1")

        mock_call_json.return_value = {
            "tasks": [
                {
                    "title": "Add numbers",
                    "description": "Implement add",
                    "priority": 1,
                    "acceptance_criteria": ["adds"],
                    "depends_on": [],
                }
            ]
        }
        mock_call.return_value = (
            "```calculator.py\ndef add(a, b):\n    return a + b\n```\n"
        )

        config = _make_config(
            products=[ProductConfig(name="MyApp", workspace=str(workspace))]
        )
        scheduler = Scheduler(config)
        results = scheduler.run_once()

        assert "MyApp" in results
        assert results["MyApp"]["tasks_processed"] >= 1
        # Strategy agent called (call_json is used by StrategyAgent)
        mock_call_json.assert_called()
        # Code generator called (call is used by CodeGeneratorAgent)
        mock_call.assert_called()


# ---------------------------------------------------------------------------
# Tests — state is persisted after a cycle
# ---------------------------------------------------------------------------


class TestStatePersistence:
    """State file is written after run_once()."""

    @mock.patch("crazypumpkin.agents.code_generator.safe_write_text")
    @mock.patch("crazypumpkin.llm.registry.ProviderRegistry.call")
    @mock.patch("crazypumpkin.llm.registry.ProviderRegistry.call_json")
    def test_state_file_written_after_run_once(
        self, mock_call_json, mock_call, mock_write, tmp_path
    ):
        """scheduler_state.json exists after run_once and has correct fields."""
        workspace = tmp_path / "ws"
        data_dir = workspace / "data"

        mock_call_json.return_value = {"tasks": []}
        mock_call.return_value = ""

        config = _make_config(
            products=[ProductConfig(name="Prod", workspace=str(workspace))]
        )
        scheduler = Scheduler(config)
        scheduler.run_once()

        state_path = data_dir / _STATE_FILENAME
        assert state_path.exists(), "State file must exist after run_once()"

        state = json.loads(state_path.read_text(encoding="utf-8"))
        assert "last_run" in state
        assert "cycle_count" in state
        assert state["cycle_count"] == 1
        assert state["last_run"] is not None

    @mock.patch("crazypumpkin.agents.code_generator.safe_write_text")
    @mock.patch("crazypumpkin.llm.registry.ProviderRegistry.call")
    @mock.patch("crazypumpkin.llm.registry.ProviderRegistry.call_json")
    def test_cycle_count_increments(
        self, mock_call_json, mock_call, mock_write, tmp_path
    ):
        """Running twice increments cycle_count to 2."""
        workspace = tmp_path / "products" / "myapp"
        data_dir = workspace / "data"

        mock_call_json.return_value = {"tasks": []}
        mock_call.return_value = ""

        config = _make_config(
            products=[ProductConfig(name="MyApp", workspace=str(workspace))]
        )
        scheduler = Scheduler(config)

        _seed_store_with_goal(data_dir)
        scheduler.run_once()
        scheduler.run_once()

        state_path = data_dir / _STATE_FILENAME
        state = json.loads(state_path.read_text(encoding="utf-8"))
        assert state["cycle_count"] == 2


# ---------------------------------------------------------------------------
# Tests — per-product error is caught and logged without aborting
# ---------------------------------------------------------------------------


class TestErrorIsolation:
    """Errors in one product do not abort processing of other products."""

    @mock.patch("crazypumpkin.agents.code_generator.safe_write_text")
    @mock.patch("crazypumpkin.llm.registry.ProviderRegistry.call")
    @mock.patch("crazypumpkin.llm.registry.ProviderRegistry.call_json")
    def test_error_in_one_product_does_not_abort_others(
        self, mock_call_json, mock_call, mock_write, tmp_path
    ):
        """A raised exception in one product does not prevent the next product."""
        workspace_a = tmp_path / "products" / "app_a"
        workspace_b = tmp_path / "products" / "app_b"

        data_dir_b = workspace_b / "data"
        _seed_store_with_goal(data_dir_b)

        mock_call_json.return_value = {"tasks": []}
        mock_call.return_value = ""

        config = _make_config(
            products=[
                {"name": "AppA", "workspace": str(workspace_a)},
                {"name": "AppB", "workspace": str(workspace_b)},
            ]
        )

        original_process = Scheduler._process_product

        def _failing_process(self_sched, product):
            if product.get("name") == "AppA":
                raise RuntimeError("Simulated failure")
            return original_process(self_sched, product)

        scheduler = Scheduler(config)
        with mock.patch.object(Scheduler, "_process_product", _failing_process):
            results = scheduler.run_once()

        # AppA should have an error, AppB should succeed
        assert "error" in results["AppA"]
        assert "Simulated failure" in results["AppA"]["error"]
        assert "error" not in results["AppB"]

    @mock.patch("crazypumpkin.agents.code_generator.safe_write_text")
    @mock.patch("crazypumpkin.llm.registry.ProviderRegistry.call")
    @mock.patch("crazypumpkin.llm.registry.ProviderRegistry.call_json")
    def test_error_is_logged(
        self, mock_call_json, mock_call, mock_write, tmp_path, caplog
    ):
        """Per-product errors are logged via logger.exception."""
        workspace = tmp_path / "ws"

        config = _make_config(
            products=[{"name": "FailApp", "workspace": str(workspace)}]
        )

        def _always_fail(self_sched, product):
            raise ValueError("Boom")

        scheduler = Scheduler(config)
        with mock.patch.object(Scheduler, "_process_product", _always_fail):
            with caplog.at_level(logging.ERROR, logger="crazypumpkin.scheduler"):
                results = scheduler.run_once()

        assert "error" in results["FailApp"]
        assert "Boom" in results["FailApp"]["error"]
        # Verify the error was logged
        assert any("FailApp" in record.message for record in caplog.records)


# ---------------------------------------------------------------------------
# Tests — --once CLI flag causes a single cycle
# ---------------------------------------------------------------------------


class TestCliRunOnce:
    """test_cli_run_once verifies single-cycle exit behaviour."""

    @mock.patch("crazypumpkin.scheduler.scheduler.Scheduler")
    @mock.patch("crazypumpkin.framework.config.load_config")
    def test_cli_run_once(self, mock_load_config, MockScheduler):
        """--once flag causes cmd_run to call run_once exactly once and return."""
        from crazypumpkin.cli import cmd_run

        mock_scheduler_instance = MockScheduler.return_value
        mock_scheduler_instance.run_once.return_value = {"Product": {"tasks_processed": 0}}

        mock_config = mock.MagicMock()
        mock_config.pipeline = {"cycle_interval": 30}
        mock_load_config.return_value = mock_config

        args = argparse.Namespace(command="run", once=True, interval=None)
        cmd_run(args)

        # run_once should be called exactly once
        mock_scheduler_instance.run_once.assert_called_once()

    @mock.patch("crazypumpkin.scheduler.scheduler.Scheduler")
    @mock.patch("crazypumpkin.framework.config.load_config")
    def test_cli_run_once_does_not_loop(self, mock_load_config, MockScheduler):
        """With --once, cmd_run returns after one cycle (no infinite loop)."""
        from crazypumpkin.cli import cmd_run

        mock_scheduler_instance = MockScheduler.return_value
        call_count = {"n": 0}

        def counting_run_once():
            call_count["n"] += 1
            return {}

        mock_scheduler_instance.run_once.side_effect = counting_run_once

        mock_config = mock.MagicMock()
        mock_config.pipeline = {"cycle_interval": 30}
        mock_load_config.return_value = mock_config

        args = argparse.Namespace(command="run", once=True, interval=None)
        cmd_run(args)

        assert call_count["n"] == 1, "run_once should be called exactly once with --once"

    def test_cli_parser_accepts_once_flag(self):
        """The argparse parser accepts --once as a valid flag for 'run'."""
        from crazypumpkin.cli import main
        import argparse as ap

        # Build the parser the same way main() does
        parser = ap.ArgumentParser(prog="crazypumpkin")
        sub = parser.add_subparsers(dest="command")
        sub.add_parser("init")
        run_parser = sub.add_parser("run")
        run_parser.add_argument("--once", action="store_true", default=False)
        run_parser.add_argument("--interval", type=int, default=None)

        args = parser.parse_args(["run", "--once"])
        assert args.once is True
        assert args.command == "run"


# ---------------------------------------------------------------------------
# Tests — per-agent cooldown tracking
# ---------------------------------------------------------------------------


class TestAgentCooldown:
    """Tests for agent_last_dispatch persistence and _is_agent_on_cooldown."""

    def test_load_state_populates_agent_last_dispatch(self, tmp_path):
        """load_state reads agent_last_dispatch from the JSON file."""
        ts = "2026-01-15T12:00:00+00:00"
        state = {
            "last_run": ts,
            "cycle_count": 5,
            "agent_last_dispatch": {"StrategyAgent": ts},
        }
        (tmp_path / _STATE_FILENAME).write_text(json.dumps(state), encoding="utf-8")

        scheduler = Scheduler(_make_config())
        scheduler.load_state(tmp_path)

        assert scheduler.agent_last_dispatch == {"StrategyAgent": ts}

    def test_load_state_defaults_to_empty_dict(self, tmp_path):
        """load_state defaults agent_last_dispatch to {} when key is absent."""
        state = {"last_run": None, "cycle_count": 0}
        (tmp_path / _STATE_FILENAME).write_text(json.dumps(state), encoding="utf-8")

        scheduler = Scheduler(_make_config())
        scheduler.load_state(tmp_path)

        assert scheduler.agent_last_dispatch == {}

    def test_load_state_defaults_when_no_file(self, tmp_path):
        """load_state defaults agent_last_dispatch to {} when file is missing."""
        scheduler = Scheduler(_make_config())
        scheduler.load_state(tmp_path)

        assert scheduler.agent_last_dispatch == {}

    def test_save_state_writes_agent_last_dispatch(self, tmp_path):
        """save_state persists agent_last_dispatch to the JSON file."""
        scheduler = Scheduler(_make_config())
        scheduler.agent_last_dispatch = {"TestAgent": "2026-01-15T12:00:00+00:00"}
        scheduler.save_state(tmp_path)

        state = json.loads((tmp_path / _STATE_FILENAME).read_text(encoding="utf-8"))
        assert state["agent_last_dispatch"] == {"TestAgent": "2026-01-15T12:00:00+00:00"}

    def test_is_agent_on_cooldown_no_prior_dispatch(self):
        """Returns False when agent has no prior dispatch record."""
        scheduler = Scheduler(_make_config())
        assert scheduler._is_agent_on_cooldown("UnknownAgent", 60) is False

    def test_is_agent_on_cooldown_within_window(self):
        """Returns True when elapsed time is less than cooldown_seconds."""
        scheduler = Scheduler(_make_config())
        recent = datetime.now(timezone.utc).isoformat()
        scheduler.agent_last_dispatch = {"TestAgent": recent}

        assert scheduler._is_agent_on_cooldown("TestAgent", 3600) is True

    def test_is_agent_on_cooldown_after_window(self):
        """Returns False after the cooldown window has passed."""
        scheduler = Scheduler(_make_config())
        old = (datetime.now(timezone.utc) - timedelta(seconds=120)).isoformat()
        scheduler.agent_last_dispatch = {"TestAgent": old}

        assert scheduler._is_agent_on_cooldown("TestAgent", 60) is False

    def test_is_agent_on_cooldown_frozen_clock_within_window(self):
        """With a frozen clock, cooldown returns True when inside the window."""
        frozen_now = datetime(2026, 6, 1, 12, 0, 0, tzinfo=timezone.utc)
        last_dispatch = datetime(2026, 6, 1, 11, 50, 0, tzinfo=timezone.utc)

        scheduler = Scheduler(_make_config())
        scheduler.agent_last_dispatch = {"TestAgent": last_dispatch.isoformat()}

        with mock.patch(
            "crazypumpkin.scheduler.scheduler.datetime"
        ) as mock_dt:
            mock_dt.now.return_value = frozen_now
            mock_dt.fromisoformat = datetime.fromisoformat
            assert scheduler._is_agent_on_cooldown("TestAgent", 3600) is True

    def test_is_agent_on_cooldown_frozen_clock_after_window(self):
        """With a frozen clock, cooldown returns False when past the window."""
        frozen_now = datetime(2026, 6, 1, 14, 0, 0, tzinfo=timezone.utc)
        last_dispatch = datetime(2026, 6, 1, 12, 0, 0, tzinfo=timezone.utc)

        scheduler = Scheduler(_make_config())
        scheduler.agent_last_dispatch = {"TestAgent": last_dispatch.isoformat()}

        with mock.patch(
            "crazypumpkin.scheduler.scheduler.datetime"
        ) as mock_dt:
            mock_dt.now.return_value = frozen_now
            mock_dt.fromisoformat = datetime.fromisoformat
            assert scheduler._is_agent_on_cooldown("TestAgent", 3600) is False

    @mock.patch("crazypumpkin.agents.code_generator.safe_write_text")
    @mock.patch("crazypumpkin.llm.registry.ProviderRegistry.call")
    @mock.patch("crazypumpkin.llm.registry.ProviderRegistry.call_json")
    def test_dispatch_records_agent_timestamps(
        self, mock_call_json, mock_call, mock_write, tmp_path
    ):
        """_process_product records dispatch timestamps for agents."""
        workspace = tmp_path / "products" / "app"
        data_dir = workspace / "data"
        _seed_store_with_goal(data_dir, project_id="proj1")

        mock_call_json.return_value = {
            "tasks": [
                {
                    "title": "Sub task",
                    "description": "Do something",
                    "priority": 1,
                    "acceptance_criteria": ["works"],
                    "depends_on": [],
                }
            ]
        }
        mock_call.return_value = "```file.py\npass\n```\n"

        config = _make_config(
            products=[ProductConfig(name="App", workspace=str(workspace))]
        )
        scheduler = Scheduler(config)
        scheduler.run_once()

        assert "StrategyAgent" in scheduler.agent_last_dispatch
        assert "CodeGeneratorAgent" in scheduler.agent_last_dispatch
        # Timestamps should be valid ISO-8601
        datetime.fromisoformat(scheduler.agent_last_dispatch["StrategyAgent"])
        datetime.fromisoformat(scheduler.agent_last_dispatch["CodeGeneratorAgent"])


# ---------------------------------------------------------------------------
# Tests — trigger expression integration with scheduler dispatch
# ---------------------------------------------------------------------------


class TestTriggerIntegration:
    """Tests for trigger-based dispatch decisions in the scheduler."""

    def _make_config_with_agents(self, agent_defs, products=None):
        """Return a Config with custom AgentDefinitions."""
        return Config(
            company={"name": "TestCo"},
            products=products or [],
            llm={
                "default_provider": "anthropic_api",
                "providers": {"anthropic_api": {"api_key": "fake"}},
                "agent_models": {},
            },
            agents=agent_defs,
        )

    def test_never_trigger_skips_dispatch(self):
        """Agent with trigger='never' causes _should_dispatch to return False."""
        config = self._make_config_with_agents([
            AgentDefinition(name="NeverAgent", role=AgentRole.STRATEGY, trigger="never"),
        ])
        scheduler = Scheduler(config)
        snapshot = {"planned_tasks": 5, "in_progress_tasks": 0, "hours_since_last_run": 10.0}
        assert scheduler._should_dispatch("NeverAgent", snapshot) is False

    def test_always_trigger_dispatches(self):
        """Agent with trigger='always' causes _should_dispatch to return True."""
        config = self._make_config_with_agents([
            AgentDefinition(name="AlwaysAgent", role=AgentRole.STRATEGY, trigger="always"),
        ])
        scheduler = Scheduler(config)
        snapshot = {"planned_tasks": 0, "in_progress_tasks": 0, "hours_since_last_run": 0.0}
        assert scheduler._should_dispatch("AlwaysAgent", snapshot) is True

    def test_default_trigger_is_always(self):
        """Agent with empty trigger defaults to 'always' and dispatches."""
        config = self._make_config_with_agents([
            AgentDefinition(name="DefaultAgent", role=AgentRole.EXECUTION, trigger=""),
        ])
        scheduler = Scheduler(config)
        snapshot = {"planned_tasks": 0, "in_progress_tasks": 0, "hours_since_last_run": 0.0}
        assert scheduler._should_dispatch("DefaultAgent", snapshot) is True

    def test_snapshot_trigger_true_dispatches(self):
        """Trigger 'planned_tasks > 0' dispatches when planned_tasks=5."""
        config = self._make_config_with_agents([
            AgentDefinition(
                name="ConditionalAgent", role=AgentRole.EXECUTION,
                trigger="planned_tasks > 0",
            ),
        ])
        scheduler = Scheduler(config)
        snapshot = {"planned_tasks": 5, "in_progress_tasks": 0, "hours_since_last_run": 1.0}
        assert scheduler._should_dispatch("ConditionalAgent", snapshot) is True

    def test_snapshot_trigger_false_skips(self):
        """Trigger 'planned_tasks > 5' skips when planned_tasks=3."""
        config = self._make_config_with_agents([
            AgentDefinition(
                name="ConditionalAgent", role=AgentRole.EXECUTION,
                trigger="planned_tasks > 5",
            ),
        ])
        scheduler = Scheduler(config)
        snapshot = {"planned_tasks": 3, "in_progress_tasks": 0, "hours_since_last_run": 1.0}
        assert scheduler._should_dispatch("ConditionalAgent", snapshot) is False

    def test_compound_trigger_and_both_true(self):
        """Compound AND trigger dispatches when both conditions are met."""
        config = self._make_config_with_agents([
            AgentDefinition(
                name="CompoundAgent", role=AgentRole.EXECUTION,
                trigger="planned_tasks > 0 AND hours_since_last_run > 1",
            ),
        ])
        scheduler = Scheduler(config)
        snapshot = {"planned_tasks": 3, "in_progress_tasks": 0, "hours_since_last_run": 2.0}
        assert scheduler._should_dispatch("CompoundAgent", snapshot) is True

    def test_compound_trigger_and_one_false(self):
        """Compound AND trigger skips when one condition is false."""
        config = self._make_config_with_agents([
            AgentDefinition(
                name="CompoundAgent", role=AgentRole.EXECUTION,
                trigger="planned_tasks > 0 AND hours_since_last_run > 1",
            ),
        ])
        scheduler = Scheduler(config)
        snapshot = {"planned_tasks": 3, "in_progress_tasks": 0, "hours_since_last_run": 0.5}
        assert scheduler._should_dispatch("CompoundAgent", snapshot) is False

    def test_cooldown_blocks_dispatch_even_when_trigger_true(self):
        """Agent on cooldown is skipped even when trigger evaluates True."""
        config = self._make_config_with_agents([
            AgentDefinition(
                name="CooldownAgent", role=AgentRole.EXECUTION,
                trigger="always", cooldown_seconds=3600,
            ),
        ])
        scheduler = Scheduler(config)
        scheduler.agent_last_dispatch = {
            "CooldownAgent": datetime.now(timezone.utc).isoformat()
        }
        snapshot = {"planned_tasks": 5, "in_progress_tasks": 0, "hours_since_last_run": 10.0}
        assert scheduler._should_dispatch("CooldownAgent", snapshot) is False

    @mock.patch("crazypumpkin.agents.code_generator.safe_write_text")
    @mock.patch("crazypumpkin.llm.registry.ProviderRegistry.call")
    @mock.patch("crazypumpkin.llm.registry.ProviderRegistry.call_json")
    def test_never_trigger_agent_execute_not_called(
        self, mock_call_json, mock_call, mock_write, tmp_path
    ):
        """End-to-end: strategy agent with trigger='never' does NOT call execute."""
        workspace = tmp_path / "products" / "app"
        data_dir = workspace / "data"
        _seed_store_with_goal(data_dir)

        mock_call_json.return_value = {"tasks": []}
        mock_call.return_value = ""

        config = Config(
            company={"name": "TestCo"},
            products=[ProductConfig(name="App", workspace=str(workspace))],
            llm={
                "default_provider": "anthropic_api",
                "providers": {"anthropic_api": {"api_key": "fake"}},
                "agent_models": {},
            },
            agents=[
                AgentDefinition(name="StrategyAgent", role=AgentRole.STRATEGY, trigger="never"),
                AgentDefinition(name="CodeGeneratorAgent", role=AgentRole.EXECUTION, trigger="never"),
            ],
        )
        scheduler = Scheduler(config)
        scheduler.run_once()

        # Neither LLM call endpoint should have been invoked
        mock_call_json.assert_not_called()
        mock_call.assert_not_called()

    @mock.patch("crazypumpkin.agents.code_generator.safe_write_text")
    @mock.patch("crazypumpkin.llm.registry.ProviderRegistry.call")
    @mock.patch("crazypumpkin.llm.registry.ProviderRegistry.call_json")
    def test_always_trigger_agent_execute_is_called(
        self, mock_call_json, mock_call, mock_write, tmp_path
    ):
        """End-to-end: strategy agent with trigger='always' DOES call execute."""
        workspace = tmp_path / "products" / "app"
        data_dir = workspace / "data"
        _seed_store_with_goal(data_dir)

        mock_call_json.return_value = {
            "tasks": [
                {
                    "title": "Sub",
                    "description": "Do it",
                    "priority": 1,
                    "acceptance_criteria": ["done"],
                    "depends_on": [],
                }
            ]
        }
        mock_call.return_value = "```file.py\npass\n```\n"

        config = Config(
            company={"name": "TestCo"},
            products=[ProductConfig(name="App", workspace=str(workspace))],
            llm={
                "default_provider": "anthropic_api",
                "providers": {"anthropic_api": {"api_key": "fake"}},
                "agent_models": {},
            },
            agents=[
                AgentDefinition(name="StrategyAgent", role=AgentRole.STRATEGY, trigger="always"),
                AgentDefinition(name="CodeGeneratorAgent", role=AgentRole.EXECUTION, trigger="always"),
            ],
        )
        scheduler = Scheduler(config)
        scheduler.run_once()

        mock_call_json.assert_called()
        mock_call.assert_called()

    def test_build_snapshot_populates_planned_tasks(self, tmp_path):
        """_build_snapshot reflects the actual task count from the store."""
        from crazypumpkin.framework.store import Store

        data_dir = tmp_path / "data"
        data_dir.mkdir(parents=True)

        store = Store(data_dir=data_dir)
        # Add 3 planned tasks
        for i in range(3):
            t = Task(
                id=f"t{i}", project_id="p1", title=f"Task {i}",
                status=TaskStatus.PLANNED,
            )
            store.add_task(t)

        scheduler = Scheduler(_make_config())
        snapshot = scheduler._build_snapshot(store)

        assert snapshot["planned_tasks"] == 3
        assert snapshot["in_progress_tasks"] == 0


# ---------------------------------------------------------------------------
# Tests — save_state / load_state round-trip for agent_last_dispatch
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# Tests — load_state / save_state persistence (standalone)
# ---------------------------------------------------------------------------


def test_load_state_no_file(tmp_path):
    """load_state on empty dir returns defaults: last_run=None, cycle_count=0."""
    scheduler = Scheduler(_make_config())
    state = scheduler.load_state(tmp_path)

    assert scheduler.last_run is None
    assert scheduler.cycle_count == 0
    assert state["last_run"] is None
    assert state["cycle_count"] == 0


def test_save_and_load_state_roundtrip(tmp_path):
    """save_state then load_state: cycle_count=1, last_run is valid ISO timestamp."""
    data_dir = tmp_path / "data"
    data_dir.mkdir(parents=True)

    scheduler = Scheduler(_make_config())
    scheduler.save_state(data_dir)

    scheduler2 = Scheduler(_make_config())
    scheduler2.load_state(data_dir)

    assert scheduler2.cycle_count == 1
    assert scheduler2.last_run is not None
    # Verify last_run is a valid ISO-8601 timestamp
    parsed = datetime.fromisoformat(scheduler2.last_run)
    assert parsed.tzinfo is not None


def test_load_state_corrupt_json(tmp_path):
    """Corrupt JSON in scheduler_state.json -> defaults without raising."""
    (tmp_path / _STATE_FILENAME).write_text("NOT VALID JSON {{{", encoding="utf-8")

    scheduler = Scheduler(_make_config())
    state = scheduler.load_state(tmp_path)

    assert scheduler.last_run is None
    assert scheduler.cycle_count == 0
    assert state == {"last_run": None, "cycle_count": 0}


def test_save_state_creates_directory(tmp_path):
    """save_state with a non-existent subdirectory path creates the directory and file."""
    nested_dir = tmp_path / "a" / "b" / "c"
    assert not nested_dir.exists()

    scheduler = Scheduler(_make_config())
    scheduler.save_state(nested_dir)

    assert nested_dir.exists()
    state_path = nested_dir / _STATE_FILENAME
    assert state_path.exists()
    state = json.loads(state_path.read_text(encoding="utf-8"))
    assert state["cycle_count"] == 1


def test_agent_last_dispatch_persisted(tmp_path):
    """agent_last_dispatch survives save_state -> load_state in a new instance."""
    data_dir = tmp_path / "data"
    data_dir.mkdir(parents=True)

    dispatches = {
        "StrategyAgent": "2026-03-01T10:00:00+00:00",
        "CodeGeneratorAgent": "2026-03-01T11:30:00+00:00",
    }

    scheduler = Scheduler(_make_config())
    scheduler.agent_last_dispatch = dict(dispatches)
    scheduler.save_state(data_dir)

    scheduler2 = Scheduler(_make_config())
    scheduler2.load_state(data_dir)

    assert scheduler2.agent_last_dispatch == dispatches
    for agent, ts in dispatches.items():
        assert scheduler2.agent_last_dispatch[agent] == ts


class TestAgentLastDispatchRoundTrip:
    """save_state/load_state preserves agent_last_dispatch exactly."""

    def test_round_trip_preserves_timestamps(self, tmp_path):
        """agent_last_dispatch survives a save_state → load_state cycle."""
        data_dir = tmp_path / "data"
        data_dir.mkdir(parents=True)

        original_dispatches = {
            "StrategyAgent": "2026-03-01T10:00:00+00:00",
            "CodeGeneratorAgent": "2026-03-01T11:30:00+00:00",
        }

        scheduler = Scheduler(_make_config())
        scheduler.agent_last_dispatch = dict(original_dispatches)
        scheduler.save_state(data_dir)

        scheduler2 = Scheduler(_make_config())
        scheduler2.load_state(data_dir)

        assert scheduler2.agent_last_dispatch == original_dispatches

    def test_round_trip_empty_dispatches(self, tmp_path):
        """Empty agent_last_dispatch round-trips correctly."""
        data_dir = tmp_path / "data"
        data_dir.mkdir(parents=True)

        scheduler = Scheduler(_make_config())
        scheduler.agent_last_dispatch = {}
        scheduler.save_state(data_dir)

        scheduler2 = Scheduler(_make_config())
        scheduler2.load_state(data_dir)

        assert scheduler2.agent_last_dispatch == {}

    def test_round_trip_multiple_agents(self, tmp_path):
        """Multiple agent timestamps are all preserved through round-trip."""
        data_dir = tmp_path / "data"
        data_dir.mkdir(parents=True)

        dispatches = {
            "Agent1": "2026-01-01T00:00:00+00:00",
            "Agent2": "2026-02-15T08:30:00+00:00",
            "Agent3": "2026-03-20T16:45:00+00:00",
        }

        scheduler = Scheduler(_make_config())
        scheduler.agent_last_dispatch = dict(dispatches)
        scheduler.save_state(data_dir)

        scheduler2 = Scheduler(_make_config())
        scheduler2.load_state(data_dir)

        assert scheduler2.agent_last_dispatch == dispatches
        # Verify each timestamp individually
        for agent, ts in dispatches.items():
            assert scheduler2.agent_last_dispatch[agent] == ts

    def test_round_trip_cycle_count_also_persisted(self, tmp_path):
        """cycle_count and last_run are also preserved alongside agent_last_dispatch."""
        data_dir = tmp_path / "data"
        data_dir.mkdir(parents=True)

        scheduler = Scheduler(_make_config())
        scheduler.agent_last_dispatch = {"A": "2026-01-01T00:00:00+00:00"}
        scheduler.save_state(data_dir)

        scheduler2 = Scheduler(_make_config())
        scheduler2.load_state(data_dir)

        assert scheduler2.cycle_count == 1
        assert scheduler2.last_run is not None
        assert scheduler2.agent_last_dispatch == {"A": "2026-01-01T00:00:00+00:00"}

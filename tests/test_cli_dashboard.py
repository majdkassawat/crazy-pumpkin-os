"""Tests for crazypumpkin dashboard CLI subcommand."""

import argparse
import json
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from crazypumpkin.dashboard.view import (
    agents_table,
    logs_table,
    render_dashboard,
    scheduler_table,
    tasks_table,
)


# ── Fixtures ──────────────────────────────────────────────────────────────


@pytest.fixture()
def dashboard_args():
    return argparse.Namespace(command="dashboard", watch=False, interval=5)


@pytest.fixture()
def fake_config():
    """Minimal Config-like object with agents and company."""
    cfg = MagicMock()
    cfg.company = {"name": "Test Corp"}

    agent1 = MagicMock()
    agent1.name = "Dev"
    agent1.role = "execution"
    agent1.model = "opus"
    agent1.group = "execution"
    agent1.class_path = "crazypumpkin.agents.dev.DevAgent"

    agent2 = MagicMock()
    agent2.name = "Reviewer"
    agent2.role = "reviewer"
    agent2.model = "sonnet"
    agent2.group = "review"
    agent2.class_path = "crazypumpkin.agents.reviewer.ReviewerAgent"

    cfg.agents = [agent1, agent2]
    return cfg


@pytest.fixture()
def data_dir(tmp_path):
    d = tmp_path / "data"
    d.mkdir()
    return d


# ── agents_table ──────────────────────────────────────────────────────────


def test_agents_table_shows_agents(fake_config):
    output = agents_table(fake_config)
    assert "Agents" in output
    assert "Dev" in output
    assert "Reviewer" in output
    assert "execution" in output
    assert "opus" in output


def test_agents_table_empty():
    cfg = MagicMock()
    cfg.agents = []
    output = agents_table(cfg)
    assert "no agents configured" in output


# ── tasks_table ───────────────────────────────────────────────────────────


def test_tasks_table_shows_tasks():
    store = MagicMock()
    task = MagicMock()
    task.id = "task-001"
    task.title = "Implement feature X"
    task.status.value = "in_progress"
    task.assigned_to = "Dev"
    task.project_id = "proj-1"
    store.tasks = {"task-001": task}

    output = tasks_table(store)
    assert "Tasks" in output
    assert "task-001" in output
    assert "Implement feature X" in output
    assert "in_progress" in output


def test_tasks_table_empty():
    store = MagicMock()
    store.tasks = {}
    output = tasks_table(store)
    assert "no tasks in store" in output


# ── scheduler_table ───────────────────────────────────────────────────────


def test_scheduler_table_shows_state(data_dir):
    state = {
        "last_run": "2026-03-29T10:00:00",
        "cycle_count": 42,
        "agent_last_dispatch": {"Dev": "2026-03-29T09:55:00"},
    }
    (data_dir / "scheduler_state.json").write_text(
        json.dumps(state), encoding="utf-8"
    )
    output = scheduler_table(data_dir)
    assert "Scheduler" in output
    assert "42" in output
    assert "2026-03-29T10:00:00" in output


def test_scheduler_table_missing(data_dir):
    output = scheduler_table(data_dir)
    assert "scheduler state not found" in output


# ── logs_table ────────────────────────────────────────────────────────────


def test_logs_table_shows_entries(data_dir):
    log_lines = "\n".join(f"[INFO] line {i}" for i in range(5))
    (data_dir / "pipeline.log").write_text(log_lines, encoding="utf-8")
    output = logs_table(data_dir)
    assert "Logs" in output
    assert "line 0" in output
    assert "line 4" in output


def test_logs_table_missing(data_dir):
    output = logs_table(data_dir)
    assert "no log file found" in output


# ── render_dashboard (full output) ────────────────────────────────────────


def test_render_dashboard_all_sections(fake_config, data_dir):
    (data_dir / "scheduler_state.json").write_text(
        json.dumps({"last_run": "now", "cycle_count": 1}), encoding="utf-8"
    )
    (data_dir / "pipeline.log").write_text(
        "[INFO] started\n[INFO] done\n", encoding="utf-8"
    )

    output = render_dashboard(fake_config, data_dir, store=None)
    assert "Agents" in output
    assert "Dev" in output
    assert "Scheduler" in output
    assert "Logs" in output
    assert "Test Corp" in output


# ── cmd_dashboard integration ─────────────────────────────────────────────


def test_cmd_dashboard_prints_all_sections(dashboard_args, fake_config, data_dir, capsys):
    """cmd_dashboard prints agent, scheduler, and log sections."""
    (data_dir / "scheduler_state.json").write_text(
        json.dumps({"last_run": "now", "cycle_count": 0}), encoding="utf-8"
    )
    (data_dir / "pipeline.log").write_text("[INFO] test\n", encoding="utf-8")

    with patch(
        "crazypumpkin.framework.config.load_config", return_value=fake_config
    ), patch("crazypumpkin.cli.Path") as MockPath:
        MockPath.cwd.return_value = data_dir.parent
        MockPath.side_effect = Path

        from crazypumpkin.cli import cmd_dashboard as _cmd
        _cmd(dashboard_args)

    output = capsys.readouterr().out
    assert "Agents" in output
    assert "Scheduler" in output
    assert "Logs" in output
    assert "Test Corp" in output


def test_cmd_dashboard_no_store_still_works(dashboard_args, fake_config, data_dir, capsys):
    """Dashboard works even when Store cannot be loaded."""
    with patch(
        "crazypumpkin.framework.config.load_config", return_value=fake_config
    ), patch("crazypumpkin.cli.Path") as MockPath, patch(
        "crazypumpkin.framework.store.Store", side_effect=Exception("no store")
    ):
        MockPath.cwd.return_value = data_dir.parent
        MockPath.side_effect = Path

        from crazypumpkin.cli import cmd_dashboard as _cmd
        _cmd(dashboard_args)

    output = capsys.readouterr().out
    assert "Test Corp" in output
    assert "Agents" in output


# ── watch mode ───────────────────────────────────────────────────────────


def test_cmd_dashboard_watch_clears_and_refreshes(fake_config, data_dir, capsys):
    """--watch renders, clears terminal, then exits on KeyboardInterrupt."""
    watch_args = argparse.Namespace(command="dashboard", watch=True, interval=1)

    call_count = 0

    def _sleep_raises(seconds):
        nonlocal call_count
        call_count += 1
        raise KeyboardInterrupt

    with patch(
        "crazypumpkin.framework.config.load_config", return_value=fake_config
    ), patch("crazypumpkin.cli.Path") as MockPath, patch(
        "crazypumpkin.cli.time.sleep", side_effect=_sleep_raises
    ), patch("crazypumpkin.cli.os.system") as mock_system:
        MockPath.cwd.return_value = data_dir.parent
        MockPath.side_effect = Path

        from crazypumpkin.cli import cmd_dashboard as _cmd
        _cmd(watch_args)

    # Terminal should have been cleared at least once
    mock_system.assert_called()
    clear_cmd = mock_system.call_args[0][0]
    assert clear_cmd in ("cls", "clear")

    output = capsys.readouterr().out
    assert "Dashboard watch stopped." in output
    assert call_count == 1


def test_cmd_dashboard_watch_interval_configurable(fake_config, data_dir):
    """--interval value is forwarded to time.sleep."""
    watch_args = argparse.Namespace(command="dashboard", watch=True, interval=10)

    def _sleep_raises(seconds):
        assert seconds == 10
        raise KeyboardInterrupt

    with patch(
        "crazypumpkin.framework.config.load_config", return_value=fake_config
    ), patch("crazypumpkin.cli.Path") as MockPath, patch(
        "crazypumpkin.cli.time.sleep", side_effect=_sleep_raises
    ), patch("crazypumpkin.cli.os.system"):
        MockPath.cwd.return_value = data_dir.parent
        MockPath.side_effect = Path

        from crazypumpkin.cli import cmd_dashboard as _cmd
        _cmd(watch_args)


def test_dashboard_parser_accepts_watch_and_interval():
    """Argument parser recognises --watch and --interval flags."""
    from crazypumpkin.cli import main
    import argparse as _argparse

    parser = _argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="command")
    dp = sub.add_parser("dashboard")
    dp.add_argument("--watch", action="store_true", default=False)
    dp.add_argument("--interval", type=int, default=5)

    args = parser.parse_args(["dashboard", "--watch", "--interval", "3"])
    assert args.watch is True
    assert args.interval == 3

    args2 = parser.parse_args(["dashboard"])
    assert args2.watch is False
    assert args2.interval == 5

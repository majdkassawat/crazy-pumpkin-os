"""Tests for schedule CLI subcommands (list, add, remove)."""

import argparse
import sys
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from crazypumpkin.cli.schedule import cmd_schedule_list, cmd_schedule_add, cmd_schedule_remove
from crazypumpkin.framework.config import Config
from crazypumpkin.framework.models import AgentDefinition, AgentRole


def _make_config(agents=None):
    """Build a Config with the given agent list."""
    if agents is None:
        agents = []
    cfg = Config(
        company={"name": "TestCo"},
        products=[],
        llm={},
        agents=agents,
        pipeline={"cycle_interval": 30},
    )
    return cfg


# ── schedule list ────────────────────────────────────────────────────


def test_schedule_list_empty(capsys):
    """With no scheduled agents, prints 'No scheduled agents found.'"""
    config = _make_config(agents=[
        AgentDefinition(name="Dev", role=AgentRole.EXECUTION),
    ])
    args = argparse.Namespace(command="schedule", schedule_command="list")
    with patch("crazypumpkin.cli.schedule.load_config", return_value=config):
        cmd_schedule_list(args)
    output = capsys.readouterr().out
    assert "No scheduled agents found." in output


def test_schedule_list_with_agents(capsys):
    """Lists both agent names when two agents have cron fields."""
    config = _make_config(agents=[
        AgentDefinition(name="Strategist", role=AgentRole.STRATEGY, cron="0 * * * *"),
        AgentDefinition(name="Developer", role=AgentRole.EXECUTION, cron="*/10 * * * *"),
        AgentDefinition(name="Reviewer", role=AgentRole.REVIEWER),
    ])
    args = argparse.Namespace(command="schedule", schedule_command="list")
    with patch("crazypumpkin.cli.schedule.load_config", return_value=config):
        cmd_schedule_list(args)
    output = capsys.readouterr().out
    assert "Strategist" in output
    assert "Developer" in output
    assert "Reviewer" not in output


# ── schedule add ─────────────────────────────────────────────────────


def test_schedule_add_valid(capsys):
    """Adding a valid cron prints confirmation and calls save_config."""
    config = _make_config(agents=[
        AgentDefinition(name="testagent", role=AgentRole.EXECUTION),
    ])
    args = argparse.Namespace(
        command="schedule", schedule_command="add",
        agent_name="testagent", cron_expr="*/10 * * * *",
    )
    with patch("crazypumpkin.cli.schedule.load_config", return_value=config), \
         patch("crazypumpkin.cli.schedule.save_config") as mock_save:
        cmd_schedule_add(args)
    output = capsys.readouterr().out
    assert "Scheduled testagent" in output
    mock_save.assert_called_once()


def test_schedule_add_invalid_cron():
    """Invalid cron expression causes a non-zero exit."""
    config = _make_config(agents=[
        AgentDefinition(name="testagent", role=AgentRole.EXECUTION),
    ])
    args = argparse.Namespace(
        command="schedule", schedule_command="add",
        agent_name="testagent", cron_expr="bad cron",
    )
    with patch("crazypumpkin.cli.schedule.load_config", return_value=config):
        with pytest.raises(SystemExit) as exc_info:
            cmd_schedule_add(args)
    assert exc_info.value.code != 0


def test_schedule_add_nonexistent_agent():
    """Adding a schedule for a missing agent exits with code 1."""
    config = _make_config(agents=[
        AgentDefinition(name="OtherAgent", role=AgentRole.EXECUTION),
    ])
    args = argparse.Namespace(
        command="schedule", schedule_command="add",
        agent_name="ghost", cron_expr="*/10 * * * *",
    )
    with patch("crazypumpkin.cli.schedule.load_config", return_value=config):
        with pytest.raises(SystemExit) as exc_info:
            cmd_schedule_add(args)
    assert exc_info.value.code == 1


# ── schedule remove ──────────────────────────────────────────────────


def test_schedule_remove_existing(capsys):
    """Removing an existing schedule prints confirmation."""
    config = _make_config(agents=[
        AgentDefinition(name="Strategist", role=AgentRole.STRATEGY, cron="0 * * * *"),
    ])
    args = argparse.Namespace(
        command="schedule", schedule_command="remove",
        agent_name="Strategist",
    )
    with patch("crazypumpkin.cli.schedule.load_config", return_value=config), \
         patch("crazypumpkin.cli.schedule.save_config"):
        cmd_schedule_remove(args)
    output = capsys.readouterr().out
    assert "Removed schedule" in output


def test_schedule_remove_nonexistent():
    """Removing a schedule from an unscheduled agent exits with code 1."""
    config = _make_config(agents=[
        AgentDefinition(name="Dev", role=AgentRole.EXECUTION),
    ])
    args = argparse.Namespace(
        command="schedule", schedule_command="remove",
        agent_name="Dev",
    )
    with patch("crazypumpkin.cli.schedule.load_config", return_value=config):
        with pytest.raises(SystemExit) as exc_info:
            cmd_schedule_remove(args)
    assert exc_info.value.code == 1

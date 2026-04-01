"""Tests for crazypumpkin status collector and CLI command."""

import argparse
import json
import sys
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from crazypumpkin.cli import cmd_status
from crazypumpkin.cli.status import collect_status, format_status_table
from crazypumpkin.framework.metrics import AgentMetrics
from crazypumpkin.framework.models import AgentDefinition


# ── collect_status ────────────────────────────────────────────────────────


def test_collect_status_returns_required_keys(tmp_path):
    """collect_status returns dict with 'agents', 'triggers', 'metrics'."""
    mock_config = MagicMock()
    agent1 = AgentDefinition(name="Dev", trigger="0 * * * *")
    agent2 = AgentDefinition(name="Reviewer", trigger="")
    mock_config.agents = [agent1, agent2]

    fake_metrics = AgentMetrics()
    fake_metrics.record_execution("Dev", duration=1.5)

    with patch("crazypumpkin.cli.status.load_config", return_value=mock_config), \
         patch("crazypumpkin.cli.status.default_metrics", fake_metrics):
        result = collect_status(tmp_path)

    assert "agents" in result
    assert "triggers" in result
    assert "metrics" in result
    assert len(result["agents"]) == 2
    assert result["agents"][0]["name"] == "Dev"
    # Only agent1 has a trigger
    assert len(result["triggers"]) == 1
    assert result["triggers"][0]["agent"] == "Dev"
    # Metrics recorded for Dev
    assert "Dev" in result["metrics"]
    assert result["metrics"]["Dev"]["executions"] == 1


def test_collect_status_empty_project(tmp_path):
    """No config file returns empty lists/dicts without error."""
    with patch("crazypumpkin.cli.status.load_config", side_effect=FileNotFoundError):
        result = collect_status(tmp_path)

    assert result == {"agents": [], "triggers": [], "metrics": {}}


# ── format_status_table ──────────────────────────────────────────────────


def test_format_status_table_sections():
    """Output contains 'Agents', 'Triggers', 'Metrics' section headers."""
    status = {
        "agents": [
            {"name": "Dev", "state": "configured", "last_run": None, "error_count": 0},
        ],
        "triggers": [
            {"agent": "Dev", "expression": "0 * * * *"},
        ],
        "metrics": {
            "Dev": {"executions": 5, "errors": 1, "total_duration": 12.3},
        },
    }
    output = format_status_table(status)
    assert "Agents" in output
    assert "Triggers" in output
    assert "Metrics" in output
    assert "Dev" in output
    assert "0 * * * *" in output
    assert "executions=5" in output


# ── cmd_status CLI ───────────────────────────────────────────────────────


def test_status_cli_json_output(capsys, tmp_path):
    """status --json exits normally and produces parseable JSON."""
    args = argparse.Namespace(command="status", project_dir=str(tmp_path), json=True)

    with patch("crazypumpkin.cli.status.load_config", side_effect=FileNotFoundError):
        cmd_status(args)

    output = capsys.readouterr().out
    parsed = json.loads(output)
    assert "agents" in parsed
    assert "triggers" in parsed
    assert "metrics" in parsed


def test_status_cli_human_output(capsys, tmp_path):
    """status (no --json) exits normally and shows section headers."""
    args = argparse.Namespace(command="status", project_dir=str(tmp_path), json=False)

    mock_config = MagicMock()
    mock_config.agents = [AgentDefinition(name="Bot", trigger="")]
    fake_metrics = AgentMetrics()

    with patch("crazypumpkin.cli.status.load_config", return_value=mock_config), \
         patch("crazypumpkin.cli.status.default_metrics", fake_metrics):
        cmd_status(args)

    output = capsys.readouterr().out
    assert "Agents" in output
    assert "Triggers" in output
    assert "Metrics" in output
    assert "Bot" in output

"""Tests for crazypumpkin.cli.cmd_cost CLI command."""

import argparse
import json
from unittest.mock import patch

import pytest

from crazypumpkin.cli import cmd_cost
from crazypumpkin.llm.base import CallCost, CostTracker


def _make_args(by_model=False, by_agent=False, use_json=False):
    return argparse.Namespace(
        command="cost",
        by_model=by_model,
        by_agent=by_agent,
        json=use_json,
    )


def _make_tracker_with_data():
    """Return a CostTracker pre-loaded with sample data."""
    tracker = CostTracker()
    tracker.record(
        "gpt-4", CallCost(prompt_tokens=100, completion_tokens=50, cost_usd=0.01,
                          cache_creation_tokens=5, cache_read_tokens=10),
        agent="developer",
    )
    tracker.record(
        "claude-3", CallCost(prompt_tokens=200, completion_tokens=80, cost_usd=0.05,
                             cache_creation_tokens=15, cache_read_tokens=30),
        agent="strategist",
    )
    return tracker


class TestCmdCostBasicOutput:
    """cmd_cost prints totals in human-readable text by default."""

    def test_shows_total_cost(self, capsys):
        tracker = _make_tracker_with_data()
        with patch("crazypumpkin.llm.base.get_default_tracker", return_value=tracker):
            cmd_cost(_make_args())
        out = capsys.readouterr().out
        assert "$0.0600" in out

    def test_shows_call_count(self, capsys):
        tracker = _make_tracker_with_data()
        with patch("crazypumpkin.llm.base.get_default_tracker", return_value=tracker):
            cmd_cost(_make_args())
        out = capsys.readouterr().out
        assert "2" in out

    def test_shows_prompt_tokens(self, capsys):
        tracker = _make_tracker_with_data()
        with patch("crazypumpkin.llm.base.get_default_tracker", return_value=tracker):
            cmd_cost(_make_args())
        out = capsys.readouterr().out
        assert "300" in out

    def test_shows_completion_tokens(self, capsys):
        tracker = _make_tracker_with_data()
        with patch("crazypumpkin.llm.base.get_default_tracker", return_value=tracker):
            cmd_cost(_make_args())
        out = capsys.readouterr().out
        assert "130" in out

    def test_shows_cache_read_tokens(self, capsys):
        tracker = _make_tracker_with_data()
        with patch("crazypumpkin.llm.base.get_default_tracker", return_value=tracker):
            cmd_cost(_make_args())
        out = capsys.readouterr().out
        assert "40" in out

    def test_shows_cache_creation_tokens(self, capsys):
        tracker = _make_tracker_with_data()
        with patch("crazypumpkin.llm.base.get_default_tracker", return_value=tracker):
            cmd_cost(_make_args())
        out = capsys.readouterr().out
        assert "20" in out


class TestCmdCostEmptyTracker:
    """cmd_cost works correctly with an empty tracker."""

    def test_empty_tracker_shows_zero_cost(self, capsys):
        tracker = CostTracker()
        with patch("crazypumpkin.llm.base.get_default_tracker", return_value=tracker):
            cmd_cost(_make_args())
        out = capsys.readouterr().out
        assert "$0.0000" in out

    def test_empty_tracker_shows_zero_calls(self, capsys):
        tracker = CostTracker()
        with patch("crazypumpkin.llm.base.get_default_tracker", return_value=tracker):
            cmd_cost(_make_args())
        out = capsys.readouterr().out
        assert "0" in out


class TestCmdCostByModel:
    """--by-model flag shows per-model breakdown."""

    def test_by_model_shows_model_names(self, capsys):
        tracker = _make_tracker_with_data()
        with patch("crazypumpkin.llm.base.get_default_tracker", return_value=tracker):
            cmd_cost(_make_args(by_model=True))
        out = capsys.readouterr().out
        assert "gpt-4" in out
        assert "claude-3" in out

    def test_by_model_shows_breakdown_header(self, capsys):
        tracker = _make_tracker_with_data()
        with patch("crazypumpkin.llm.base.get_default_tracker", return_value=tracker):
            cmd_cost(_make_args(by_model=True))
        out = capsys.readouterr().out
        assert "Per-model breakdown" in out

    def test_by_model_false_hides_breakdown(self, capsys):
        tracker = _make_tracker_with_data()
        with patch("crazypumpkin.llm.base.get_default_tracker", return_value=tracker):
            cmd_cost(_make_args(by_model=False))
        out = capsys.readouterr().out
        assert "Per-model breakdown" not in out

    def test_by_model_shows_per_model_cost(self, capsys):
        tracker = _make_tracker_with_data()
        with patch("crazypumpkin.llm.base.get_default_tracker", return_value=tracker):
            cmd_cost(_make_args(by_model=True))
        out = capsys.readouterr().out
        assert "$0.0100" in out
        assert "$0.0500" in out


class TestCmdCostByAgent:
    """--by-agent flag shows per-agent breakdown."""

    def test_by_agent_shows_agent_names(self, capsys):
        tracker = _make_tracker_with_data()
        with patch("crazypumpkin.llm.base.get_default_tracker", return_value=tracker):
            cmd_cost(_make_args(by_agent=True))
        out = capsys.readouterr().out
        assert "developer" in out
        assert "strategist" in out

    def test_by_agent_shows_breakdown_header(self, capsys):
        tracker = _make_tracker_with_data()
        with patch("crazypumpkin.llm.base.get_default_tracker", return_value=tracker):
            cmd_cost(_make_args(by_agent=True))
        out = capsys.readouterr().out
        assert "Per-agent breakdown" in out

    def test_by_agent_false_hides_breakdown(self, capsys):
        tracker = _make_tracker_with_data()
        with patch("crazypumpkin.llm.base.get_default_tracker", return_value=tracker):
            cmd_cost(_make_args(by_agent=False))
        out = capsys.readouterr().out
        assert "Per-agent breakdown" not in out


class TestCmdCostJsonOutput:
    """--json flag outputs valid JSON."""

    def test_json_output_is_valid(self, capsys):
        tracker = _make_tracker_with_data()
        with patch("crazypumpkin.llm.base.get_default_tracker", return_value=tracker):
            cmd_cost(_make_args(use_json=True))
        out = capsys.readouterr().out
        data = json.loads(out)
        assert isinstance(data, dict)

    def test_json_has_required_keys(self, capsys):
        tracker = _make_tracker_with_data()
        with patch("crazypumpkin.llm.base.get_default_tracker", return_value=tracker):
            cmd_cost(_make_args(use_json=True))
        out = capsys.readouterr().out
        data = json.loads(out)
        assert "total_cost_usd" in data
        assert "call_count" in data
        assert "total_prompt_tokens" in data
        assert "total_completion_tokens" in data
        assert "total_cache_read_tokens" in data
        assert "total_cache_creation_tokens" in data

    def test_json_values_correct(self, capsys):
        tracker = _make_tracker_with_data()
        with patch("crazypumpkin.llm.base.get_default_tracker", return_value=tracker):
            cmd_cost(_make_args(use_json=True))
        out = capsys.readouterr().out
        data = json.loads(out)
        assert data["total_cost_usd"] == pytest.approx(0.06)
        assert data["call_count"] == 2
        assert data["total_prompt_tokens"] == 300
        assert data["total_completion_tokens"] == 130

    def test_json_with_by_model_includes_breakdown(self, capsys):
        tracker = _make_tracker_with_data()
        with patch("crazypumpkin.llm.base.get_default_tracker", return_value=tracker):
            cmd_cost(_make_args(use_json=True, by_model=True))
        out = capsys.readouterr().out
        data = json.loads(out)
        assert "by_model" in data
        assert "gpt-4" in data["by_model"]
        assert "claude-3" in data["by_model"]

    def test_json_without_by_model_excludes_breakdown(self, capsys):
        tracker = _make_tracker_with_data()
        with patch("crazypumpkin.llm.base.get_default_tracker", return_value=tracker):
            cmd_cost(_make_args(use_json=True, by_model=False))
        out = capsys.readouterr().out
        data = json.loads(out)
        assert "by_model" not in data

    def test_json_with_by_agent_includes_breakdown(self, capsys):
        tracker = _make_tracker_with_data()
        with patch("crazypumpkin.llm.base.get_default_tracker", return_value=tracker):
            cmd_cost(_make_args(use_json=True, by_agent=True))
        out = capsys.readouterr().out
        data = json.loads(out)
        assert "by_agent" in data
        assert "developer" in data["by_agent"]

    def test_json_without_by_agent_excludes_breakdown(self, capsys):
        tracker = _make_tracker_with_data()
        with patch("crazypumpkin.llm.base.get_default_tracker", return_value=tracker):
            cmd_cost(_make_args(use_json=True, by_agent=False))
        out = capsys.readouterr().out
        data = json.loads(out)
        assert "by_agent" not in data

    def test_json_does_not_print_human_text(self, capsys):
        tracker = _make_tracker_with_data()
        with patch("crazypumpkin.llm.base.get_default_tracker", return_value=tracker):
            cmd_cost(_make_args(use_json=True))
        out = capsys.readouterr().out
        assert "Total cost:" not in out


class TestCmdCostCombinedFlags:
    """Combined flags work correctly."""

    def test_both_model_and_agent_breakdowns(self, capsys):
        tracker = _make_tracker_with_data()
        with patch("crazypumpkin.llm.base.get_default_tracker", return_value=tracker):
            cmd_cost(_make_args(by_model=True, by_agent=True))
        out = capsys.readouterr().out
        assert "Per-model breakdown" in out
        assert "Per-agent breakdown" in out

    def test_json_with_both_breakdowns(self, capsys):
        tracker = _make_tracker_with_data()
        with patch("crazypumpkin.llm.base.get_default_tracker", return_value=tracker):
            cmd_cost(_make_args(use_json=True, by_model=True, by_agent=True))
        out = capsys.readouterr().out
        data = json.loads(out)
        assert "by_model" in data
        assert "by_agent" in data

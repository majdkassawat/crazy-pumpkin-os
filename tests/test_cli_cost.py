"""Tests for crazypumpkin cost CLI command."""

import argparse
import sys
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from crazypumpkin.cli import cmd_cost, _get_cost_tracker
from crazypumpkin.observability.cost import CostTracker, LLMUsageRecord


def _make_tracker_with_records(days_offset=0):
    """Create a CostTracker pre-loaded with sample records."""
    tracker = CostTracker()
    now = datetime.utcnow()
    ts = now - timedelta(days=days_offset)

    tracker.record(LLMUsageRecord(
        agent_name="Developer",
        provider="openai",
        model="gpt-4",
        input_tokens=500,
        output_tokens=200,
        cached_tokens=50,
        cost_usd=0.10,
        timestamp=ts,
    ))
    tracker.record(LLMUsageRecord(
        agent_name="Reviewer",
        provider="anthropic",
        model="claude-3",
        input_tokens=300,
        output_tokens=100,
        cached_tokens=30,
        cost_usd=0.05,
        timestamp=ts,
    ))
    tracker.record(LLMUsageRecord(
        agent_name="Developer",
        provider="openai",
        model="gpt-4",
        input_tokens=200,
        output_tokens=80,
        cached_tokens=20,
        cost_usd=0.03,
        timestamp=ts,
    ))
    return tracker


# ── Basic output ──────────────────────────────────────────────────────


def test_cost_outputs_spend_summary(capsys):
    """Running `crazypumpkin cost` outputs a formatted spend summary table."""
    tracker = _make_tracker_with_records()
    args = argparse.Namespace(days=7)
    with patch("crazypumpkin.cli._get_cost_tracker", return_value=tracker):
        cmd_cost(args)
    output = capsys.readouterr().out
    assert "LLM Spend Summary" in output
    assert "Total spend" in output
    assert "$" in output


def test_cost_shows_total_spend(capsys):
    """Output includes the total spend amount."""
    tracker = _make_tracker_with_records()
    args = argparse.Namespace(days=7)
    with patch("crazypumpkin.cli._get_cost_tracker", return_value=tracker):
        cmd_cost(args)
    output = capsys.readouterr().out
    # Total should be 0.10 + 0.05 + 0.03 = 0.18
    assert "$0.18" in output


def test_cost_shows_per_agent_breakdown(capsys):
    """Output includes per-agent cost breakdown."""
    tracker = _make_tracker_with_records()
    args = argparse.Namespace(days=7)
    with patch("crazypumpkin.cli._get_cost_tracker", return_value=tracker):
        cmd_cost(args)
    output = capsys.readouterr().out
    assert "Per-agent breakdown" in output
    assert "Developer" in output
    assert "Reviewer" in output


def test_cost_shows_per_model_breakdown(capsys):
    """Output includes per-model cost breakdown."""
    tracker = _make_tracker_with_records()
    args = argparse.Namespace(days=7)
    with patch("crazypumpkin.cli._get_cost_tracker", return_value=tracker):
        cmd_cost(args)
    output = capsys.readouterr().out
    assert "Per-model breakdown" in output
    assert "gpt-4" in output
    assert "claude-3" in output


def test_cost_shows_cached_token_savings(capsys):
    """Output includes cached token savings estimate."""
    tracker = _make_tracker_with_records()
    args = argparse.Namespace(days=7)
    with patch("crazypumpkin.cli._get_cost_tracker", return_value=tracker):
        cmd_cost(args)
    output = capsys.readouterr().out
    assert "Cached token savings" in output
    # 50 + 30 + 20 = 100 cached tokens
    assert "100" in output


# ── --days flag ───────────────────────────────────────────────────────


def test_cost_days_flag_filters_records(capsys):
    """--days flag filters records to the specified time window."""
    tracker = CostTracker()
    now = datetime.utcnow()

    # Record from 2 days ago (within 7-day window)
    tracker.record(LLMUsageRecord(
        agent_name="Developer",
        provider="openai",
        model="gpt-4",
        input_tokens=100,
        output_tokens=50,
        cached_tokens=10,
        cost_usd=0.10,
        timestamp=now - timedelta(days=2),
    ))
    # Record from 10 days ago (outside 7-day window)
    tracker.record(LLMUsageRecord(
        agent_name="Reviewer",
        provider="anthropic",
        model="claude-3",
        input_tokens=100,
        output_tokens=50,
        cached_tokens=10,
        cost_usd=0.50,
        timestamp=now - timedelta(days=10),
    ))

    args = argparse.Namespace(days=7)
    with patch("crazypumpkin.cli._get_cost_tracker", return_value=tracker):
        cmd_cost(args)
    output = capsys.readouterr().out
    # Total spend should only reflect the recent record ($0.10), not the old one
    assert "$0.10" in output
    assert "last 7 days" in output


def test_cost_days_flag_custom_value(capsys):
    """--days 30 expands the window to include older records."""
    tracker = CostTracker()
    now = datetime.utcnow()

    tracker.record(LLMUsageRecord(
        agent_name="Developer",
        provider="openai",
        model="gpt-4",
        input_tokens=100,
        output_tokens=50,
        cached_tokens=10,
        cost_usd=0.10,
        timestamp=now - timedelta(days=2),
    ))
    tracker.record(LLMUsageRecord(
        agent_name="Reviewer",
        provider="anthropic",
        model="claude-3",
        input_tokens=100,
        output_tokens=50,
        cached_tokens=10,
        cost_usd=0.50,
        timestamp=now - timedelta(days=10),
    ))

    args = argparse.Namespace(days=30)
    with patch("crazypumpkin.cli._get_cost_tracker", return_value=tracker):
        cmd_cost(args)
    output = capsys.readouterr().out
    # With 30 days, total should include both: $0.60
    assert "$0.60" in output
    assert "last 30 days" in output


# ── Empty data ────────────────────────────────────────────────────────


def test_cost_no_data_shows_informative_message(capsys):
    """Command exits cleanly with informative message when no usage data exists."""
    tracker = CostTracker()
    args = argparse.Namespace(days=7)
    with patch("crazypumpkin.cli._get_cost_tracker", return_value=tracker):
        cmd_cost(args)
    output = capsys.readouterr().out
    assert "No LLM usage data" in output
    assert "7 days" in output


def test_cost_no_data_does_not_print_table(capsys):
    """When there's no data, no table headers or breakdowns are shown."""
    tracker = CostTracker()
    args = argparse.Namespace(days=7)
    with patch("crazypumpkin.cli._get_cost_tracker", return_value=tracker):
        cmd_cost(args)
    output = capsys.readouterr().out
    assert "Per-agent" not in output
    assert "Per-model" not in output
    assert "Total spend" not in output

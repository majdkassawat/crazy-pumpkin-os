"""Tests for CLI budgets command."""

import argparse
import json
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from crazypumpkin.cli import cmd_budgets


# -- helpers ----------------------------------------------------------------


def _make_args(**kwargs):
    return argparse.Namespace(command="budgets", **kwargs)


SAMPLE_BUDGETS = {
    "product-alpha": {
        "name": "product-alpha",
        "limit_usd": 100.0,
        "current_spend_usd": 42.50,
        "pct_used": 42.5,
    },
    "agent-beta": {
        "name": "agent-beta",
        "limit_usd": 50.0,
        "current_spend_usd": 50.01,
        "pct_used": 100.02,
    },
}


# -- no budgets configured --------------------------------------------------


class TestBudgetsEmpty:
    """When no budgets are configured."""

    def test_prints_no_budgets_message(self, capsys):
        with patch("crazypumpkin.observability.budget.BudgetEnforcer") as MockEnforcer:
            MockEnforcer.return_value.get_all_budgets.return_value = {}
            cmd_budgets(_make_args(json=False))

        out = capsys.readouterr().out
        assert "No budgets configured." in out

    def test_no_budgets_json_flag_still_prints_message(self, capsys):
        with patch("crazypumpkin.observability.budget.BudgetEnforcer") as MockEnforcer:
            MockEnforcer.return_value.get_all_budgets.return_value = {}
            cmd_budgets(_make_args(json=True))

        out = capsys.readouterr().out
        assert "No budgets configured." in out


# -- budgets present (text output) ------------------------------------------


class TestBudgetsText:
    """Text-mode output when budgets are present."""

    def test_prints_each_budget_name(self, capsys):
        with patch("crazypumpkin.observability.budget.BudgetEnforcer") as MockEnforcer:
            MockEnforcer.return_value.get_all_budgets.return_value = SAMPLE_BUDGETS
            cmd_budgets(_make_args(json=False))

        out = capsys.readouterr().out
        assert "product-alpha" in out
        assert "agent-beta" in out

    def test_prints_limit_and_spend(self, capsys):
        with patch("crazypumpkin.observability.budget.BudgetEnforcer") as MockEnforcer:
            MockEnforcer.return_value.get_all_budgets.return_value = SAMPLE_BUDGETS
            cmd_budgets(_make_args(json=False))

        out = capsys.readouterr().out
        assert "$100.00 limit" in out
        assert "$42.50 spent" in out

    def test_prints_percentage(self, capsys):
        with patch("crazypumpkin.observability.budget.BudgetEnforcer") as MockEnforcer:
            MockEnforcer.return_value.get_all_budgets.return_value = SAMPLE_BUDGETS
            cmd_budgets(_make_args(json=False))

        out = capsys.readouterr().out
        assert "42.5%" in out
        assert "100.02%" in out


# -- budgets present (JSON output) ------------------------------------------


class TestBudgetsJson:
    """JSON-mode output when budgets are present."""

    def test_outputs_valid_json(self, capsys):
        with patch("crazypumpkin.observability.budget.BudgetEnforcer") as MockEnforcer:
            MockEnforcer.return_value.get_all_budgets.return_value = SAMPLE_BUDGETS
            cmd_budgets(_make_args(json=True))

        out = capsys.readouterr().out
        data = json.loads(out)
        assert isinstance(data, dict)

    def test_json_contains_budget_data(self, capsys):
        with patch("crazypumpkin.observability.budget.BudgetEnforcer") as MockEnforcer:
            MockEnforcer.return_value.get_all_budgets.return_value = SAMPLE_BUDGETS
            cmd_budgets(_make_args(json=True))

        out = capsys.readouterr().out
        data = json.loads(out)
        assert "product-alpha" in data
        assert data["product-alpha"]["limit_usd"] == 100.0
        assert data["product-alpha"]["current_spend_usd"] == 42.50
        assert data["product-alpha"]["pct_used"] == 42.5

    def test_json_contains_all_budgets(self, capsys):
        with patch("crazypumpkin.observability.budget.BudgetEnforcer") as MockEnforcer:
            MockEnforcer.return_value.get_all_budgets.return_value = SAMPLE_BUDGETS
            cmd_budgets(_make_args(json=True))

        out = capsys.readouterr().out
        data = json.loads(out)
        assert len(data) == 2
        assert "agent-beta" in data


# -- enforcer interaction ---------------------------------------------------


class TestBudgetsEnforcerCalls:
    """Verify cmd_budgets calls BudgetEnforcer correctly."""

    def test_calls_get_all_budgets(self):
        with patch("crazypumpkin.observability.budget.BudgetEnforcer") as MockEnforcer:
            mock_instance = MockEnforcer.return_value
            mock_instance.get_all_budgets.return_value = {}
            cmd_budgets(_make_args(json=False))

        mock_instance.get_all_budgets.assert_called_once()

    def test_creates_enforcer_instance(self):
        with patch("crazypumpkin.observability.budget.BudgetEnforcer") as MockEnforcer:
            MockEnforcer.return_value.get_all_budgets.return_value = {}
            cmd_budgets(_make_args(json=False))

        MockEnforcer.assert_called_once()

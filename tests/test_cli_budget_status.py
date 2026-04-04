"""Tests for CLI budget-status command."""

import argparse
import json
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from crazypumpkin.cli import cmd_budget_status


# -- helpers ----------------------------------------------------------------


def _make_args(**kwargs):
    return argparse.Namespace(command="budget-status", **kwargs)


SAMPLE_STATUS = {
    "name": "mybudget",
    "limit_usd": 100.0,
    "current_spend_usd": 42.50,
    "pct_used": 42.5,
    "exceeded": False,
}

EXCEEDED_STATUS = {
    "name": "over-budget",
    "limit_usd": 50.0,
    "current_spend_usd": 55.00,
    "pct_used": 110.0,
    "exceeded": True,
}


# -- existing budget (text output) -----------------------------------------


class TestBudgetStatusText:
    """Text-mode output for an existing budget."""

    def test_prints_budget_name(self, capsys):
        with patch("crazypumpkin.observability.budget.BudgetEnforcer") as MockEnforcer:
            MockEnforcer.return_value.check_budget.return_value = SAMPLE_STATUS
            cmd_budget_status(_make_args(name="mybudget", json=False))

        out = capsys.readouterr().out
        assert "Budget: mybudget" in out

    def test_prints_limit(self, capsys):
        with patch("crazypumpkin.observability.budget.BudgetEnforcer") as MockEnforcer:
            MockEnforcer.return_value.check_budget.return_value = SAMPLE_STATUS
            cmd_budget_status(_make_args(name="mybudget", json=False))

        out = capsys.readouterr().out
        assert "$100.00" in out
        assert "Limit:" in out

    def test_prints_spent(self, capsys):
        with patch("crazypumpkin.observability.budget.BudgetEnforcer") as MockEnforcer:
            MockEnforcer.return_value.check_budget.return_value = SAMPLE_STATUS
            cmd_budget_status(_make_args(name="mybudget", json=False))

        out = capsys.readouterr().out
        assert "$42.50" in out
        assert "Spent:" in out

    def test_prints_percentage(self, capsys):
        with patch("crazypumpkin.observability.budget.BudgetEnforcer") as MockEnforcer:
            MockEnforcer.return_value.check_budget.return_value = SAMPLE_STATUS
            cmd_budget_status(_make_args(name="mybudget", json=False))

        out = capsys.readouterr().out
        assert "42.5%" in out
        assert "Used:" in out

    def test_prints_exceeded_no(self, capsys):
        with patch("crazypumpkin.observability.budget.BudgetEnforcer") as MockEnforcer:
            MockEnforcer.return_value.check_budget.return_value = SAMPLE_STATUS
            cmd_budget_status(_make_args(name="mybudget", json=False))

        out = capsys.readouterr().out
        assert "Exceeded: no" in out

    def test_prints_exceeded_yes(self, capsys):
        with patch("crazypumpkin.observability.budget.BudgetEnforcer") as MockEnforcer:
            MockEnforcer.return_value.check_budget.return_value = EXCEEDED_STATUS
            cmd_budget_status(_make_args(name="over-budget", json=False))

        out = capsys.readouterr().out
        assert "Exceeded: YES" in out


# -- existing budget (JSON output) -----------------------------------------


class TestBudgetStatusJson:
    """JSON-mode output for an existing budget."""

    def test_outputs_valid_json(self, capsys):
        with patch("crazypumpkin.observability.budget.BudgetEnforcer") as MockEnforcer:
            MockEnforcer.return_value.check_budget.return_value = SAMPLE_STATUS
            cmd_budget_status(_make_args(name="mybudget", json=True))

        out = capsys.readouterr().out
        data = json.loads(out)
        assert isinstance(data, dict)

    def test_json_matches_check_budget_schema(self, capsys):
        with patch("crazypumpkin.observability.budget.BudgetEnforcer") as MockEnforcer:
            MockEnforcer.return_value.check_budget.return_value = SAMPLE_STATUS
            cmd_budget_status(_make_args(name="mybudget", json=True))

        out = capsys.readouterr().out
        data = json.loads(out)
        assert data["name"] == "mybudget"
        assert data["limit_usd"] == 100.0
        assert data["current_spend_usd"] == 42.50
        assert data["pct_used"] == 42.5
        assert data["exceeded"] is False

    def test_json_exceeded_budget(self, capsys):
        with patch("crazypumpkin.observability.budget.BudgetEnforcer") as MockEnforcer:
            MockEnforcer.return_value.check_budget.return_value = EXCEEDED_STATUS
            cmd_budget_status(_make_args(name="over-budget", json=True))

        out = capsys.readouterr().out
        data = json.loads(out)
        assert data["exceeded"] is True
        assert data["pct_used"] == 110.0


# -- nonexistent budget ----------------------------------------------------


class TestBudgetStatusNotFound:
    """Error handling when the budget does not exist."""

    def test_prints_error_message(self, capsys):
        with patch("crazypumpkin.observability.budget.BudgetEnforcer") as MockEnforcer:
            MockEnforcer.return_value.check_budget.side_effect = KeyError("nonexistent")
            with pytest.raises(SystemExit) as exc_info:
                cmd_budget_status(_make_args(name="nonexistent", json=False))

        assert exc_info.value.code == 1
        out = capsys.readouterr().out
        assert "Error: no budget named 'nonexistent'" in out

    def test_exits_with_code_1(self):
        with patch("crazypumpkin.observability.budget.BudgetEnforcer") as MockEnforcer:
            MockEnforcer.return_value.check_budget.side_effect = KeyError("nonexistent")
            with pytest.raises(SystemExit) as exc_info:
                cmd_budget_status(_make_args(name="nonexistent", json=False))

        assert exc_info.value.code == 1


# -- enforcer interaction ---------------------------------------------------


class TestBudgetStatusEnforcerCalls:
    """Verify cmd_budget_status calls BudgetEnforcer correctly."""

    def test_calls_check_budget_with_name(self):
        with patch("crazypumpkin.observability.budget.BudgetEnforcer") as MockEnforcer:
            mock_instance = MockEnforcer.return_value
            mock_instance.check_budget.return_value = SAMPLE_STATUS
            cmd_budget_status(_make_args(name="mybudget", json=False))

        mock_instance.check_budget.assert_called_once_with("mybudget")

    def test_creates_enforcer_instance(self):
        with patch("crazypumpkin.observability.budget.BudgetEnforcer") as MockEnforcer:
            MockEnforcer.return_value.check_budget.return_value = SAMPLE_STATUS
            cmd_budget_status(_make_args(name="mybudget", json=False))

        MockEnforcer.assert_called_once()

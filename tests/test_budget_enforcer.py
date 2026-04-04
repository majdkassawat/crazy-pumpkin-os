"""Tests for BudgetEnforcer."""

from __future__ import annotations

import pytest

from crazypumpkin.observability.budget import (
    BudgetEnforcer,
    BudgetExceededError,
    CostBudget,
)


class TestBudgetEnforcer:
    """Tests matching -k 'test_enforcer'."""

    def test_enforcer_add_budget_and_record_spend_returns_total(self):
        enforcer = BudgetEnforcer()
        budget = CostBudget("proj", 100.0, "monthly")
        enforcer.add_budget(budget)
        total = enforcer.record_spend("proj", 10.0)
        assert total == 10.0
        total = enforcer.record_spend("proj", 25.0)
        assert total == 35.0

    def test_enforcer_record_spend_unregistered_raises_key_error(self):
        enforcer = BudgetEnforcer()
        with pytest.raises(KeyError, match="No budget registered"):
            enforcer.record_spend("nope", 5.0)

    def test_enforcer_record_spend_raises_budget_exceeded_on_hard_stop(self):
        enforcer = BudgetEnforcer()
        budget = CostBudget("proj", 10.0, "daily", hard_stop=True)
        enforcer.add_budget(budget)
        enforcer.record_spend("proj", 5.0)
        with pytest.raises(BudgetExceededError) as exc_info:
            enforcer.record_spend("proj", 6.0)
        assert exc_info.value.budget_name == "proj"
        assert exc_info.value.limit_usd == 10.0
        assert exc_info.value.current_usd == 11.0

    def test_enforcer_warning_callback_fires_once(self):
        enforcer = BudgetEnforcer()
        budget = CostBudget("proj", 100.0, "total", warn_at_pct=50)
        enforcer.add_budget(budget)
        calls: list[tuple] = []
        enforcer.on_warning(lambda name, cur, lim: calls.append((name, cur, lim)))
        # Below threshold — no callback
        enforcer.record_spend("proj", 40.0)
        assert len(calls) == 0
        # Cross threshold — callback fires
        enforcer.record_spend("proj", 20.0)
        assert len(calls) == 1
        assert calls[0] == ("proj", 60.0, 100.0)
        # Above threshold again — callback does NOT fire a second time
        enforcer.record_spend("proj", 10.0)
        assert len(calls) == 1

    def test_enforcer_check_budget_returns_correct_dict(self):
        enforcer = BudgetEnforcer()
        budget = CostBudget("proj", 200.0, "monthly")
        enforcer.add_budget(budget)
        enforcer.record_spend("proj", 50.0)
        info = enforcer.check_budget("proj")
        assert info["name"] == "proj"
        assert info["limit_usd"] == 200.0
        assert info["current_spend_usd"] == 50.0
        assert info["pct_used"] == 25.0
        assert info["exceeded"] is False

    def test_enforcer_check_budget_exceeded_flag(self):
        enforcer = BudgetEnforcer()
        budget = CostBudget("proj", 10.0, "daily")
        enforcer.add_budget(budget)
        enforcer.record_spend("proj", 11.0)
        info = enforcer.check_budget("proj")
        assert info["exceeded"] is True

    def test_enforcer_reset_clears_all_state(self):
        enforcer = BudgetEnforcer()
        budget = CostBudget("proj", 100.0, "total")
        enforcer.add_budget(budget)
        enforcer.on_warning(lambda *a: None)
        enforcer.record_spend("proj", 90.0)
        enforcer.reset()
        assert enforcer.get_all_budgets() == {}
        with pytest.raises(KeyError):
            enforcer.record_spend("proj", 1.0)

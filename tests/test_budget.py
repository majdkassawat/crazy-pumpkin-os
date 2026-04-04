"""Tests for budget class exports from observability package."""

from __future__ import annotations


def test_import_budget_classes_from_observability():
    """Importing CostBudget, BudgetEnforcer, BudgetExceededError from observability succeeds."""
    from crazypumpkin.observability import CostBudget, BudgetEnforcer, BudgetExceededError

    assert CostBudget is not None
    assert BudgetEnforcer is not None
    assert BudgetExceededError is not None


def test_import_budget_classes_in_all():
    """All three budget names appear in crazypumpkin.observability.__all__."""
    import crazypumpkin.observability as obs

    for name in ("CostBudget", "BudgetEnforcer", "BudgetExceededError"):
        assert name in obs.__all__, f"{name} missing from __all__"

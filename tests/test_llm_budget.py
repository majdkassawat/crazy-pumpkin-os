"""Tests for BudgetEnforcer integration in LLMProvider._record_cost."""

from __future__ import annotations

import pytest

from crazypumpkin.llm import base as llm_base
from crazypumpkin.llm.base import (
    CostTracker,
    LLMProvider,
    get_default_enforcer,
    get_default_tracker,
    set_default_enforcer,
)
from crazypumpkin.observability.budget import (
    BudgetEnforcer,
    BudgetExceededError,
    CostBudget,
)


class _StubProvider(LLMProvider):
    """Minimal concrete LLMProvider for testing _record_cost."""

    def call(self, prompt, **kwargs):
        return ""

    def call_json(self, prompt, **kwargs):
        return {}

    def call_multi_turn(self, prompt, **kwargs):
        return ""


@pytest.fixture(autouse=True)
def _reset_enforcer():
    """Ensure module-level enforcer is cleared before and after each test."""
    llm_base._default_enforcer = None
    yield
    llm_base._default_enforcer = None


def test_record_cost_no_enforcer():
    """No enforcer set — _record_cost succeeds and cost is tracked."""
    provider = _StubProvider()
    tracker = CostTracker()
    provider.cost_tracker = tracker

    provider._record_cost(
        model="gpt-4",
        input_tokens=100,
        output_tokens=50,
        cost_usd=0.05,
    )

    summary = tracker.get_summary()
    assert summary["total_cost_usd"] == pytest.approx(0.05)
    assert summary["call_count"] == 1


def test_record_cost_with_enforcer():
    """Set enforcer with a budget, call _record_cost with product, assert spend increased."""
    enforcer = BudgetEnforcer()
    enforcer.add_budget(CostBudget(name="myproduct", limit_usd=10.0, period="total"))
    set_default_enforcer(enforcer)

    provider = _StubProvider()
    tracker = CostTracker()
    provider.cost_tracker = tracker

    provider._record_cost(
        model="gpt-4",
        input_tokens=100,
        output_tokens=50,
        cost_usd=1.50,
        product="myproduct",
    )

    info = enforcer.check_budget("myproduct")
    assert info["current_spend_usd"] == pytest.approx(1.50)
    assert info["pct_used"] == pytest.approx(15.0)


def test_record_cost_enforcer_hard_stop():
    """Hard-stop enforcer raises BudgetExceededError; cost is still recorded in CostTracker."""
    enforcer = BudgetEnforcer()
    enforcer.add_budget(
        CostBudget(name="tiny", limit_usd=0.01, period="daily", hard_stop=True)
    )
    set_default_enforcer(enforcer)

    provider = _StubProvider()
    tracker = CostTracker()
    provider.cost_tracker = tracker

    with pytest.raises(BudgetExceededError) as exc_info:
        provider._record_cost(
            model="gpt-4",
            input_tokens=500,
            output_tokens=200,
            cost_usd=2.00,
            product="tiny",
        )

    assert exc_info.value.budget_name == "tiny"
    assert exc_info.value.limit_usd == pytest.approx(0.01)
    # Cost must still be recorded in the tracker even though enforcer raised
    summary = tracker.get_summary()
    assert summary["total_cost_usd"] == pytest.approx(2.00)
    assert summary["call_count"] == 1


def test_record_cost_no_product_skips_enforcer():
    """Empty product string means enforcer.record_spend is never called."""
    enforcer = BudgetEnforcer()
    enforcer.add_budget(CostBudget(name="myproduct", limit_usd=10.0, period="total"))
    set_default_enforcer(enforcer)

    provider = _StubProvider()
    tracker = CostTracker()
    provider.cost_tracker = tracker

    provider._record_cost(
        model="gpt-4",
        input_tokens=100,
        output_tokens=50,
        cost_usd=0.50,
        product="",
    )

    info = enforcer.check_budget("myproduct")
    assert info["current_spend_usd"] == pytest.approx(0.0)


def test_get_set_default_enforcer():
    """get_default_enforcer returns None initially; set then get returns same instance."""
    assert get_default_enforcer() is None

    enforcer = BudgetEnforcer()
    set_default_enforcer(enforcer)

    assert get_default_enforcer() is enforcer

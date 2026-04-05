"""Tests for budget checking integration in the agent run loop.

Covers: _check_budget_after_call method existence, cost recording,
threshold-based alert dispatch via BudgetNotifier, BudgetExceededError
on hard_stop, and no error when hard_stop is False.
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, patch

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from crazypumpkin.framework.agent import BaseAgent, BudgetExceededError
from crazypumpkin.framework.models import Agent, AgentRole, Task, TaskOutput
from crazypumpkin.observability.budget import (
    AlertLevel,
    BudgetAlert,
    BudgetEnforcer,
    BudgetThreshold,
    CostBudget,
)
from crazypumpkin.observability.budget_notifier import BudgetNotifier


# ---------------------------------------------------------------------------
# Concrete stub agent for testing
# ---------------------------------------------------------------------------

class _StubAgent(BaseAgent):
    """Minimal concrete BaseAgent for testing budget integration."""

    def execute(self, task: Task, context: dict[str, Any]) -> TaskOutput:
        return TaskOutput(content="ok")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_agent(name: str = "test-agent") -> Agent:
    return Agent(name=name, role=AgentRole.EXECUTION)


def _make_enforcer(
    agent_name: str = "test-agent",
    limit: float = 100.0,
    threshold: BudgetThreshold | None = None,
) -> BudgetEnforcer:
    enforcer = BudgetEnforcer(threshold=threshold or BudgetThreshold(cooldown_seconds=0))
    enforcer.add_budget(CostBudget(agent_name, limit, "monthly"))
    return enforcer


# ---------------------------------------------------------------------------
# Tests: _check_budget_after_call method exists
# ---------------------------------------------------------------------------

class TestCheckBudgetMethodExists:

    def test_method_exists_on_base_agent(self):
        agent = _StubAgent(_make_agent())
        assert hasattr(agent, "_check_budget_after_call")
        assert callable(agent._check_budget_after_call)

    def test_method_is_async(self):
        agent = _StubAgent(_make_agent())
        assert asyncio.iscoroutinefunction(agent._check_budget_after_call)


# ---------------------------------------------------------------------------
# Tests: cost recording and threshold checking
# ---------------------------------------------------------------------------

class TestCostRecording:

    def test_records_cost_in_enforcer(self):
        agent = _StubAgent(_make_agent())
        enforcer = _make_enforcer()
        agent.configure_budget(enforcer, BudgetNotifier())

        asyncio.get_event_loop().run_until_complete(
            agent._check_budget_after_call(25.0)
        )

        status = enforcer.check_budget("test-agent")
        assert status["current_spend_usd"] == 25.0

    def test_accumulates_multiple_costs(self):
        agent = _StubAgent(_make_agent())
        enforcer = _make_enforcer()
        agent.configure_budget(enforcer, BudgetNotifier())

        loop = asyncio.get_event_loop()
        loop.run_until_complete(agent._check_budget_after_call(10.0))
        loop.run_until_complete(agent._check_budget_after_call(15.0))
        loop.run_until_complete(agent._check_budget_after_call(5.0))

        status = enforcer.check_budget("test-agent")
        assert status["current_spend_usd"] == 30.0

    def test_no_op_when_no_enforcer_configured(self):
        """No error when budget is not configured."""
        agent = _StubAgent(_make_agent())
        # No configure_budget call
        asyncio.get_event_loop().run_until_complete(
            agent._check_budget_after_call(10.0)
        )


# ---------------------------------------------------------------------------
# Tests: alert dispatch via BudgetNotifier
# ---------------------------------------------------------------------------

class TestAlertDispatch:

    def test_dispatches_warning_alert(self):
        agent = _StubAgent(_make_agent())
        enforcer = _make_enforcer(limit=100.0)
        notifier = BudgetNotifier()
        notifier.dispatch = AsyncMock()
        agent.configure_budget(enforcer, notifier)

        asyncio.get_event_loop().run_until_complete(
            agent._check_budget_after_call(85.0)
        )

        notifier.dispatch.assert_called_once()
        alert = notifier.dispatch.call_args[0][0]
        assert alert.level == AlertLevel.WARNING
        assert alert.agent_name == "test-agent"

    def test_dispatches_critical_alert(self):
        agent = _StubAgent(_make_agent())
        enforcer = _make_enforcer(limit=100.0)
        notifier = BudgetNotifier()
        notifier.dispatch = AsyncMock()
        agent.configure_budget(enforcer, notifier)

        asyncio.get_event_loop().run_until_complete(
            agent._check_budget_after_call(96.0)
        )

        notifier.dispatch.assert_called_once()
        alert = notifier.dispatch.call_args[0][0]
        assert alert.level == AlertLevel.CRITICAL

    def test_dispatches_exceeded_alert(self):
        agent = _StubAgent(_make_agent())
        enforcer = _make_enforcer(limit=100.0)
        notifier = BudgetNotifier()
        notifier.dispatch = AsyncMock()
        agent.configure_budget(enforcer, notifier)

        asyncio.get_event_loop().run_until_complete(
            agent._check_budget_after_call(105.0)
        )

        notifier.dispatch.assert_called_once()
        alert = notifier.dispatch.call_args[0][0]
        assert alert.level == AlertLevel.EXCEEDED

    def test_no_dispatch_below_threshold(self):
        agent = _StubAgent(_make_agent())
        enforcer = _make_enforcer(limit=100.0)
        notifier = BudgetNotifier()
        notifier.dispatch = AsyncMock()
        agent.configure_budget(enforcer, notifier)

        asyncio.get_event_loop().run_until_complete(
            agent._check_budget_after_call(50.0)
        )

        notifier.dispatch.assert_not_called()

    def test_dispatch_at_each_threshold_level(self):
        """Verifies alert dispatch at warning, critical, and exceeded levels."""
        levels_dispatched = []

        for spend, expected_level in [
            (80.0, AlertLevel.WARNING),
            (95.0, AlertLevel.CRITICAL),
            (100.0, AlertLevel.EXCEEDED),
        ]:
            agent = _StubAgent(_make_agent())
            enforcer = _make_enforcer(limit=100.0)
            notifier = BudgetNotifier()
            notifier.dispatch = AsyncMock()
            agent.configure_budget(enforcer, notifier)

            asyncio.get_event_loop().run_until_complete(
                agent._check_budget_after_call(spend)
            )

            notifier.dispatch.assert_called_once()
            alert = notifier.dispatch.call_args[0][0]
            assert alert.level == expected_level
            levels_dispatched.append(alert.level)

        assert levels_dispatched == [
            AlertLevel.WARNING,
            AlertLevel.CRITICAL,
            AlertLevel.EXCEEDED,
        ]


# ---------------------------------------------------------------------------
# Tests: BudgetExceededError raised on hard_stop
# ---------------------------------------------------------------------------

class TestBudgetExceededError:

    def test_raised_when_exceeded_and_hard_stop_true(self):
        agent = _StubAgent(_make_agent())
        enforcer = _make_enforcer(limit=100.0)
        notifier = BudgetNotifier()
        notifier.dispatch = AsyncMock()
        agent.configure_budget(enforcer, notifier, hard_stop=True)

        with pytest.raises(BudgetExceededError):
            asyncio.get_event_loop().run_until_complete(
                agent._check_budget_after_call(105.0)
            )

    def test_not_raised_when_exceeded_and_hard_stop_false(self):
        agent = _StubAgent(_make_agent())
        enforcer = _make_enforcer(limit=100.0)
        notifier = BudgetNotifier()
        notifier.dispatch = AsyncMock()
        agent.configure_budget(enforcer, notifier, hard_stop=False)

        # Should NOT raise
        asyncio.get_event_loop().run_until_complete(
            agent._check_budget_after_call(105.0)
        )

        # Alert should still be dispatched even without hard_stop
        notifier.dispatch.assert_called_once()
        alert = notifier.dispatch.call_args[0][0]
        assert alert.level == AlertLevel.EXCEEDED

    def test_not_raised_when_below_limit_and_hard_stop_true(self):
        agent = _StubAgent(_make_agent())
        enforcer = _make_enforcer(limit=100.0)
        notifier = BudgetNotifier()
        notifier.dispatch = AsyncMock()
        agent.configure_budget(enforcer, notifier, hard_stop=True)

        # Below threshold, should not raise
        asyncio.get_event_loop().run_until_complete(
            agent._check_budget_after_call(50.0)
        )

    def test_alert_dispatched_before_error_raised(self):
        """Ensure the alert is dispatched even when BudgetExceededError is raised."""
        agent = _StubAgent(_make_agent())
        enforcer = _make_enforcer(limit=100.0)
        notifier = BudgetNotifier()
        notifier.dispatch = AsyncMock()
        agent.configure_budget(enforcer, notifier, hard_stop=True)

        with pytest.raises(BudgetExceededError):
            asyncio.get_event_loop().run_until_complete(
                agent._check_budget_after_call(105.0)
            )

        # Alert was dispatched before the error
        notifier.dispatch.assert_called_once()

    def test_budget_exceeded_error_is_exception_subclass(self):
        assert issubclass(BudgetExceededError, Exception)


# ---------------------------------------------------------------------------
# Tests: mock LLM calls with budget verification
# ---------------------------------------------------------------------------

class TestMockLLMCallBudgetFlow:

    def test_simulated_llm_calls_trigger_alerts_at_thresholds(self):
        """Simulate multiple LLM calls and verify alert dispatch at each threshold."""
        agent = _StubAgent(_make_agent())
        enforcer = _make_enforcer(limit=100.0)
        notifier = BudgetNotifier()
        notifier.dispatch = AsyncMock()
        agent.configure_budget(enforcer, notifier)

        loop = asyncio.get_event_loop()

        # Call 1: $30 — below all thresholds
        loop.run_until_complete(agent._check_budget_after_call(30.0))
        notifier.dispatch.assert_not_called()

        # Call 2: $55 — total $85, crosses warning (80%)
        loop.run_until_complete(agent._check_budget_after_call(55.0))
        assert notifier.dispatch.call_count == 1
        alert = notifier.dispatch.call_args[0][0]
        assert alert.level == AlertLevel.WARNING

        # Call 3: $11 — total $96, crosses critical (95%)
        loop.run_until_complete(agent._check_budget_after_call(11.0))
        assert notifier.dispatch.call_count == 2
        alert = notifier.dispatch.call_args[0][0]
        assert alert.level == AlertLevel.CRITICAL

        # Call 4: $10 — total $106, crosses exceeded (100%)
        loop.run_until_complete(agent._check_budget_after_call(10.0))
        assert notifier.dispatch.call_count == 3
        alert = notifier.dispatch.call_args[0][0]
        assert alert.level == AlertLevel.EXCEEDED

    def test_simulated_llm_calls_hard_stop_halts_on_exceed(self):
        """Hard stop halts execution when budget is exceeded."""
        agent = _StubAgent(_make_agent())
        enforcer = _make_enforcer(limit=50.0)
        notifier = BudgetNotifier()
        notifier.dispatch = AsyncMock()
        agent.configure_budget(enforcer, notifier, hard_stop=True)

        loop = asyncio.get_event_loop()

        # Under budget
        loop.run_until_complete(agent._check_budget_after_call(20.0))

        # Over budget — should raise
        with pytest.raises(BudgetExceededError):
            loop.run_until_complete(agent._check_budget_after_call(35.0))

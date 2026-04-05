"""Tests for BudgetAlert model, BudgetThreshold config, and check_thresholds.

Covers: dataclass fields/defaults, AlertLevel enum values, threshold-based
alert generation (WARNING/CRITICAL/EXCEEDED), cooldown suppression, and
custom threshold configuration.
"""

from __future__ import annotations

import time
from unittest.mock import patch

import pytest

from crazypumpkin.observability.budget import (
    AlertLevel,
    BudgetAlert,
    BudgetEnforcer,
    BudgetThreshold,
    CostBudget,
)


class TestBudgetThresholdDataclass:
    """BudgetThreshold has expected fields and defaults."""

    def test_default_warning_pct(self):
        t = BudgetThreshold()
        assert t.warning_pct == 0.8

    def test_default_critical_pct(self):
        t = BudgetThreshold()
        assert t.critical_pct == 0.95

    def test_default_notification_channels(self):
        t = BudgetThreshold()
        assert t.notification_channels == ["slack"]

    def test_default_cooldown_seconds(self):
        t = BudgetThreshold()
        assert t.cooldown_seconds == 3600

    def test_custom_values(self):
        t = BudgetThreshold(
            warning_pct=0.7,
            critical_pct=0.9,
            notification_channels=["email", "pagerduty"],
            cooldown_seconds=600,
        )
        assert t.warning_pct == 0.7
        assert t.critical_pct == 0.9
        assert t.notification_channels == ["email", "pagerduty"]
        assert t.cooldown_seconds == 600


class TestBudgetAlertDataclass:
    """BudgetAlert has expected fields."""

    def test_alert_fields(self):
        alert = BudgetAlert(
            level=AlertLevel.WARNING,
            agent_name="research",
            current_spend=80.0,
            limit=100.0,
            message="research at 80.0% of $100.00 budget (warning)",
        )
        assert alert.level == AlertLevel.WARNING
        assert alert.agent_name == "research"
        assert alert.current_spend == 80.0
        assert alert.limit == 100.0
        assert alert.message == "research at 80.0% of $100.00 budget (warning)"


class TestAlertLevel:
    """AlertLevel enum values."""

    def test_warning_value(self):
        assert AlertLevel.WARNING.value == "warning"

    def test_critical_value(self):
        assert AlertLevel.CRITICAL.value == "critical"

    def test_exceeded_value(self):
        assert AlertLevel.EXCEEDED.value == "exceeded"


class TestCheckThresholds:
    """check_thresholds returns correct alerts based on spend ratio."""

    def _make_enforcer(self, limit: float = 100.0, threshold: BudgetThreshold | None = None) -> BudgetEnforcer:
        enforcer = BudgetEnforcer(threshold=threshold)
        enforcer.add_budget(CostBudget("agent1", limit, "monthly"))
        return enforcer

    def test_below_warning_returns_none(self):
        enforcer = self._make_enforcer()
        enforcer.record_spend("agent1", 50.0)  # 50%
        assert enforcer.check_thresholds("agent1") is None

    def test_at_zero_spend_returns_none(self):
        enforcer = self._make_enforcer()
        assert enforcer.check_thresholds("agent1") is None

    def test_just_below_warning_returns_none(self):
        enforcer = self._make_enforcer()
        enforcer.record_spend("agent1", 79.99)  # 79.99%
        assert enforcer.check_thresholds("agent1") is None

    def test_at_warning_threshold_returns_warning(self):
        enforcer = self._make_enforcer()
        enforcer.record_spend("agent1", 80.0)  # exactly 80%
        alert = enforcer.check_thresholds("agent1")
        assert alert is not None
        assert alert.level == AlertLevel.WARNING
        assert alert.agent_name == "agent1"
        assert alert.current_spend == 80.0
        assert alert.limit == 100.0

    def test_above_warning_below_critical_returns_warning(self):
        enforcer = self._make_enforcer()
        enforcer.record_spend("agent1", 90.0)  # 90%
        alert = enforcer.check_thresholds("agent1")
        assert alert is not None
        assert alert.level == AlertLevel.WARNING

    def test_at_critical_threshold_returns_critical(self):
        enforcer = self._make_enforcer()
        enforcer.record_spend("agent1", 95.0)  # exactly 95%
        alert = enforcer.check_thresholds("agent1")
        assert alert is not None
        assert alert.level == AlertLevel.CRITICAL
        assert alert.current_spend == 95.0

    def test_above_critical_below_exceeded_returns_critical(self):
        enforcer = self._make_enforcer()
        enforcer.record_spend("agent1", 99.0)  # 99%
        alert = enforcer.check_thresholds("agent1")
        assert alert is not None
        assert alert.level == AlertLevel.CRITICAL

    def test_at_100_pct_returns_exceeded(self):
        enforcer = self._make_enforcer()
        enforcer.record_spend("agent1", 100.0)  # exactly 100%
        alert = enforcer.check_thresholds("agent1")
        assert alert is not None
        assert alert.level == AlertLevel.EXCEEDED
        assert alert.current_spend == 100.0

    def test_over_100_pct_returns_exceeded(self):
        enforcer = self._make_enforcer()
        enforcer.record_spend("agent1", 150.0)  # 150%
        alert = enforcer.check_thresholds("agent1")
        assert alert is not None
        assert alert.level == AlertLevel.EXCEEDED

    def test_alert_message_contains_info(self):
        enforcer = self._make_enforcer()
        enforcer.record_spend("agent1", 80.0)
        alert = enforcer.check_thresholds("agent1")
        assert "agent1" in alert.message
        assert "warning" in alert.message

    def test_unregistered_agent_raises_key_error(self):
        enforcer = self._make_enforcer()
        with pytest.raises(KeyError, match="No budget registered"):
            enforcer.check_thresholds("unknown")

    def test_custom_threshold_values(self):
        threshold = BudgetThreshold(warning_pct=0.5, critical_pct=0.7)
        enforcer = self._make_enforcer(threshold=threshold)
        enforcer.record_spend("agent1", 50.0)  # 50% = warning with custom
        alert = enforcer.check_thresholds("agent1")
        assert alert is not None
        assert alert.level == AlertLevel.WARNING

        enforcer2 = self._make_enforcer(threshold=threshold)
        enforcer2.record_spend("agent1", 70.0)  # 70% = critical with custom
        alert2 = enforcer2.check_thresholds("agent1")
        assert alert2 is not None
        assert alert2.level == AlertLevel.CRITICAL


class TestCooldown:
    """Cooldown prevents duplicate alerts within the cooldown window."""

    def test_cooldown_suppresses_second_alert(self):
        threshold = BudgetThreshold(cooldown_seconds=3600)
        enforcer = BudgetEnforcer(threshold=threshold)
        enforcer.add_budget(CostBudget("agent1", 100.0, "monthly"))
        enforcer.record_spend("agent1", 85.0)

        # First call should return an alert
        alert1 = enforcer.check_thresholds("agent1")
        assert alert1 is not None
        assert alert1.level == AlertLevel.WARNING

        # Second call within cooldown should return None
        alert2 = enforcer.check_thresholds("agent1")
        assert alert2 is None

    def test_alert_fires_again_after_cooldown_expires(self):
        threshold = BudgetThreshold(cooldown_seconds=10)
        enforcer = BudgetEnforcer(threshold=threshold)
        enforcer.add_budget(CostBudget("agent1", 100.0, "monthly"))
        enforcer.record_spend("agent1", 85.0)

        # First alert
        alert1 = enforcer.check_thresholds("agent1")
        assert alert1 is not None

        # Simulate time passing beyond cooldown by manipulating _last_alert_time
        with enforcer._lock:
            enforcer._last_alert_time["agent1"] -= 11

        # Should fire again
        alert2 = enforcer.check_thresholds("agent1")
        assert alert2 is not None
        assert alert2.level == AlertLevel.WARNING

    def test_cooldown_zero_always_fires(self):
        threshold = BudgetThreshold(cooldown_seconds=0)
        enforcer = BudgetEnforcer(threshold=threshold)
        enforcer.add_budget(CostBudget("agent1", 100.0, "monthly"))
        enforcer.record_spend("agent1", 85.0)

        alert1 = enforcer.check_thresholds("agent1")
        assert alert1 is not None

        alert2 = enforcer.check_thresholds("agent1")
        assert alert2 is not None

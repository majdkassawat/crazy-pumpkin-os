"""Tests for agent health checking."""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from crazypumpkin.agents.health import (
    HealthReport,
    SystemHealth,
    aggregate_health,
    check_agent_health,
)
from crazypumpkin.framework.models import Agent, AgentConfig, AgentRole, AgentStatus


def _make_agent(**overrides):
    defaults = {"name": "test-agent", "role": AgentRole.EXECUTION}
    defaults.update(overrides)
    return Agent(**defaults)


class TestHealthReport:
    def test_default_fields(self):
        report = HealthReport()
        assert report.status == "healthy"
        assert report.message == ""
        assert report.timestamp  # non-empty
        assert report.details == {}

    def test_custom_fields(self):
        report = HealthReport(
            status="unhealthy",
            message="broken",
            timestamp="2026-01-01T00:00:00+00:00",
            details={"key": "val"},
        )
        assert report.status == "unhealthy"
        assert report.message == "broken"
        assert report.details == {"key": "val"}


class TestCheckAgentHealth:
    def test_healthy_agent(self):
        agent = _make_agent()
        report = check_agent_health(agent)
        assert report.status == "healthy"
        assert "operational" in report.message.lower()
        assert report.details["agent_name"] == "test-agent"

    def test_no_name_unhealthy(self):
        agent = _make_agent(name="")
        report = check_agent_health(agent)
        assert report.status == "unhealthy"
        assert "no name" in report.message

    def test_disabled_agent_degraded(self):
        agent = _make_agent(status=AgentStatus.DISABLED)
        report = check_agent_health(agent)
        assert report.status == "degraded"
        assert "disabled" in report.message.lower()

    def test_disabled_and_no_name_unhealthy(self):
        agent = _make_agent(name="", status=AgentStatus.DISABLED)
        report = check_agent_health(agent)
        assert report.status == "unhealthy"

    def test_bad_timeout_unhealthy(self):
        agent = _make_agent(config=AgentConfig(timeout_sec=0))
        report = check_agent_health(agent)
        assert report.status == "unhealthy"
        assert "timeout" in report.message

    def test_negative_retries_unhealthy(self):
        agent = _make_agent(config=AgentConfig(max_retries=-1))
        report = check_agent_health(agent)
        assert report.status == "unhealthy"
        assert "max_retries" in report.message

    def test_report_has_timestamp(self):
        agent = _make_agent()
        report = check_agent_health(agent)
        assert report.timestamp


class TestSystemHealth:
    def test_default_fields(self):
        sh = SystemHealth()
        assert sh.status == "healthy"
        assert sh.uptime_pct == 100.0
        assert sh.agent_reports == []
        assert sh.timestamp
        assert sh.summary == ""


class TestAggregateHealth:
    def test_empty_reports_healthy(self):
        result = aggregate_health([])
        assert result.status == "healthy"
        assert result.uptime_pct == 100.0
        assert result.agent_reports == []

    def test_all_healthy(self):
        reports = [
            HealthReport(status="healthy", message="ok"),
            HealthReport(status="healthy", message="ok"),
            HealthReport(status="healthy", message="ok"),
        ]
        result = aggregate_health(reports)
        assert result.status == "healthy"
        assert result.uptime_pct == 100.0
        assert len(result.agent_reports) == 3

    def test_one_unhealthy_degraded(self):
        reports = [
            HealthReport(status="healthy"),
            HealthReport(status="healthy"),
            HealthReport(status="unhealthy"),
        ]
        result = aggregate_health(reports)
        assert result.status == "degraded"
        assert 60.0 < result.uptime_pct < 70.0  # 66.67%

    def test_half_healthy_degraded(self):
        reports = [
            HealthReport(status="healthy"),
            HealthReport(status="unhealthy"),
        ]
        result = aggregate_health(reports)
        assert result.status == "degraded"
        assert result.uptime_pct == 50.0

    def test_majority_unhealthy_critical(self):
        reports = [
            HealthReport(status="unhealthy"),
            HealthReport(status="unhealthy"),
            HealthReport(status="healthy"),
        ]
        result = aggregate_health(reports)
        assert result.status == "critical"
        assert 33.0 < result.uptime_pct < 34.0  # 33.33%

    def test_all_unhealthy_critical(self):
        reports = [
            HealthReport(status="unhealthy"),
            HealthReport(status="unhealthy"),
        ]
        result = aggregate_health(reports)
        assert result.status == "critical"
        assert result.uptime_pct == 0.0

    def test_degraded_agents_not_counted_healthy(self):
        reports = [
            HealthReport(status="healthy"),
            HealthReport(status="degraded"),
        ]
        result = aggregate_health(reports)
        assert result.status == "degraded"
        assert result.uptime_pct == 50.0

    def test_summary_populated(self):
        reports = [HealthReport(status="healthy")]
        result = aggregate_health(reports)
        assert result.summary
        assert result.timestamp

    def test_reports_preserved(self):
        reports = [
            HealthReport(status="healthy", message="agent-a"),
            HealthReport(status="unhealthy", message="agent-b"),
        ]
        result = aggregate_health(reports)
        assert len(result.agent_reports) == 2
        assert result.agent_reports[0].message == "agent-a"
        assert result.agent_reports[1].message == "agent-b"

    def test_single_unhealthy_critical(self):
        reports = [HealthReport(status="unhealthy")]
        result = aggregate_health(reports)
        assert result.status == "critical"
        assert result.uptime_pct == 0.0

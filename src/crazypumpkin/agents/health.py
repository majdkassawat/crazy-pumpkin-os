"""Agent health checking utilities."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from crazypumpkin.framework.models import Agent, AgentStatus


@dataclass
class HealthReport:
    """Result of an agent health check."""

    status: str = "healthy"
    message: str = ""
    timestamp: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )
    details: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "message": self.message,
            "timestamp": self.timestamp,
            "details": self.details,
        }


@dataclass
class SystemHealth:
    """Aggregate health status for the entire system."""

    status: str = "healthy"
    uptime_pct: float = 100.0
    agent_reports: list[HealthReport] = field(default_factory=list)
    timestamp: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )
    summary: str = ""


def check_agent_health(agent: Agent) -> HealthReport:
    """Inspect an agent instance and return a HealthReport.

    Returns a report with status 'healthy', 'degraded', or 'unhealthy'
    depending on the agent's configuration and state.

    Args:
        agent: The Agent model instance to inspect.

    Returns:
        HealthReport indicating the agent's health.
    """
    issues: list[str] = []

    if not agent.name:
        issues.append("agent has no name")

    if agent.status == AgentStatus.DISABLED:
        issues.append("agent is disabled")

    if not agent.role:
        issues.append("agent has no role assigned")

    if agent.config.timeout_sec <= 0:
        issues.append("timeout is non-positive")

    if agent.config.max_retries < 0:
        issues.append("max_retries is negative")

    if not issues:
        return HealthReport(
            status="healthy",
            message="Agent is properly configured and operational.",
            details={"agent_id": agent.id, "agent_name": agent.name},
        )

    if len(issues) == 1 and issues[0] == "agent is disabled":
        return HealthReport(
            status="degraded",
            message="Agent is disabled.",
            details={"agent_id": agent.id, "issues": issues},
        )

    return HealthReport(
        status="unhealthy",
        message=f"Agent is misconfigured: {'; '.join(issues)}",
        details={"agent_id": agent.id, "issues": issues},
    )


class HealthChecker:
    """Async health checker that runs check_agent_health across registered agents."""

    def __init__(self) -> None:
        self._agents: list[Agent] = []

    def register(self, agent: Agent) -> None:
        self._agents.append(agent)

    async def check_all(self) -> list[HealthReport]:
        return [check_agent_health(a) for a in self._agents]


def aggregate_health(reports: list[HealthReport]) -> SystemHealth:
    """Aggregate individual agent health reports into overall system health.

    Computes uptime percentage as the fraction of reports with status
    ``"healthy"`` and maps that to a system-level status:

    * ``uptime_pct == 100`` → ``"healthy"``
    * ``uptime_pct >= 50``  → ``"degraded"``
    * ``uptime_pct < 50``   → ``"critical"``

    An empty list of reports is treated as fully healthy (no agents to
    report problems).

    Args:
        reports: Individual :class:`HealthReport` instances, typically one
            per agent.

    Returns:
        A :class:`SystemHealth` summarising the overall state.
    """
    if not reports:
        return SystemHealth(
            status="healthy",
            uptime_pct=100.0,
            agent_reports=[],
            summary="No agents reporting.",
        )

    healthy_count = sum(1 for r in reports if r.status == "healthy")
    uptime_pct = (healthy_count / len(reports)) * 100.0

    if uptime_pct == 100.0:
        status = "healthy"
        summary = "All agents healthy."
    elif uptime_pct >= 50.0:
        status = "degraded"
        unhealthy = len(reports) - healthy_count
        summary = f"{unhealthy}/{len(reports)} agents reporting issues."
    else:
        status = "critical"
        unhealthy = len(reports) - healthy_count
        summary = f"{unhealthy}/{len(reports)} agents reporting issues."

    return SystemHealth(
        status=status,
        uptime_pct=uptime_pct,
        agent_reports=list(reports),
        summary=summary,
    )

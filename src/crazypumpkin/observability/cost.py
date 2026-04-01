"""LLM call cost tracking — per-agent and per-model usage accounting."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional


@dataclass
class LLMUsageRecord:
    agent_name: str
    provider: str
    model: str
    input_tokens: int
    output_tokens: int
    cached_tokens: int
    cost_usd: float
    timestamp: datetime = field(default_factory=datetime.utcnow)
    metadata: Optional[dict] = None


class CostTracker:
    def __init__(self) -> None:
        self._records: list[LLMUsageRecord] = []

    def record(self, usage: LLMUsageRecord) -> None:
        self._records.append(usage)

    def get_spend_by_agent(self, agent_name: str, since: Optional[datetime] = None) -> float:
        total = 0.0
        for r in self._records:
            if r.agent_name != agent_name:
                continue
            if since is not None and r.timestamp < since:
                continue
            total += r.cost_usd
        return total

    def get_total_spend(self, since: Optional[datetime] = None) -> float:
        total = 0.0
        for r in self._records:
            if since is not None and r.timestamp < since:
                continue
            total += r.cost_usd
        return total

    def get_usage_summary(self) -> dict:
        by_agent: dict[str, float] = {}
        by_model: dict[str, float] = {}
        for r in self._records:
            by_agent[r.agent_name] = by_agent.get(r.agent_name, 0.0) + r.cost_usd
            by_model[r.model] = by_model.get(r.model, 0.0) + r.cost_usd
        return {
            "total_cost_usd": self.get_total_spend(),
            "record_count": len(self._records),
            "by_agent": by_agent,
            "by_model": by_model,
        }

"""Per-product cost tracking with Langfuse export."""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional

from crazypumpkin.observability.tracing import get_tracer


@dataclass
class CostRecord:
    """A single LLM call cost record."""

    agent_name: str
    model: str
    prompt_tokens: int
    completion_tokens: int
    cost_usd: float
    product: str = "crazy-pumpkin-os"
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


class CostTracker:
    """Tracks LLM costs with per-product and per-agent aggregation."""

    def __init__(self) -> None:
        self._records: list[CostRecord] = []
        self._product_spend: dict[str, float] = defaultdict(float)
        self._agent_spend: dict[str, float] = defaultdict(float)
        self._product_agent_spend: dict[str, dict[str, float]] = defaultdict(
            lambda: defaultdict(float)
        )
        self._synced_count: int = 0

    def record(
        self,
        agent_name: str,
        model: str,
        prompt_tokens: int,
        completion_tokens: int,
        cost_usd: float,
        product: str = "crazy-pumpkin-os",
    ) -> CostRecord:
        """Create and store a CostRecord, optionally tracing to Langfuse."""
        rec = CostRecord(
            agent_name=agent_name,
            model=model,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            cost_usd=cost_usd,
            product=product,
        )
        self._records.append(rec)
        self._product_spend[product] += cost_usd
        self._agent_spend[agent_name] += cost_usd
        self._product_agent_spend[product][agent_name] += cost_usd

        tracer = get_tracer()
        if tracer is not None:
            tracer.trace_llm_call(
                agent_name=agent_name,
                model=model,
                prompt_tokens=prompt_tokens,
                completion_tokens=completion_tokens,
                cost_usd=cost_usd,
                product=product,
            )
            self._synced_count = len(self._records)

        return rec

    def spend_by_product(self) -> dict[str, float]:
        """Return total USD spend keyed by product name."""
        return dict(self._product_spend)

    def spend_by_agent(self, product: Optional[str] = None) -> dict[str, float]:
        """Return total USD spend keyed by agent name, optionally filtered by product."""
        if product is not None:
            return dict(self._product_agent_spend.get(product, {}))
        return dict(self._agent_spend)

    def total_spend(self) -> float:
        """Return the sum of all recorded cost_usd values."""
        return sum(self._product_spend.values())

    def export_to_langfuse(self) -> int:
        """Send unsynced records to Langfuse. Returns the count of records sent."""
        tracer = get_tracer()
        if tracer is None:
            return 0

        unsynced = self._records[self._synced_count :]
        for rec in unsynced:
            tracer.trace_llm_call(
                agent_name=rec.agent_name,
                model=rec.model,
                prompt_tokens=rec.prompt_tokens,
                completion_tokens=rec.completion_tokens,
                cost_usd=rec.cost_usd,
                product=rec.product,
            )
        count = len(unsynced)
        self._synced_count = len(self._records)
        return count

"""Per-product cost tracking with Langfuse export."""

from __future__ import annotations

import threading
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
        self._lock = threading.Lock()
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
        with self._lock:
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
            with self._lock:
                self._synced_count = len(self._records)

        return rec

    def spend_by_product(self) -> dict[str, float]:
        """Return total USD spend keyed by product name."""
        with self._lock:
            return dict(self._product_spend)

    def spend_by_agent(self, product: Optional[str] = None) -> dict[str, float]:
        """Return total USD spend keyed by agent name, optionally filtered by product."""
        with self._lock:
            if product is not None:
                return dict(self._product_agent_spend.get(product, {}))
            return dict(self._agent_spend)

    def total_spend(self) -> float:
        """Return the sum of all recorded cost_usd values."""
        with self._lock:
            return sum(self._product_spend.values())

    def export_to_langfuse(self) -> int:
        """Send unsynced records to Langfuse. Returns the count of records sent."""
        tracer = get_tracer()
        if tracer is None:
            return 0

        with self._lock:
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
        with self._lock:
            self._synced_count = len(self._records)
        return count


_global_tracker: Optional[CostTracker] = None
_tracker_lock = threading.Lock()


def get_cost_tracker() -> CostTracker:
    """Return the module-level singleton CostTracker, lazily initialised."""
    global _global_tracker
    with _tracker_lock:
        if _global_tracker is None:
            _global_tracker = CostTracker()
        return _global_tracker

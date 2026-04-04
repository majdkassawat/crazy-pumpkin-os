"""Cost tracking module — per-agent spend recording with JSONL storage."""

from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Optional


@dataclass
class CostRecord:
    """A single cost record for an LLM call."""

    agent_name: str
    product: str
    model: str
    input_tokens: int
    output_tokens: int
    cost_usd: float
    cached_tokens: int = 0
    timestamp: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )
    metadata: Optional[dict] = None


class CostTracker:
    """Tracks LLM costs in a JSONL file."""

    def __init__(
        self,
        store_path: str = ".cpos/costs.jsonl",
        base_dir: str | None = None,
    ) -> None:
        if base_dir is None:
            base_dir = os.getcwd()
        resolved = os.path.abspath(os.path.join(base_dir, store_path))
        abs_base = os.path.abspath(base_dir)
        if os.path.commonpath([resolved, abs_base]) != abs_base:
            raise ValueError(
                f"store_path escapes base directory: {store_path!r}"
            )
        self.store_path = resolved

    def record(self, record: CostRecord) -> None:
        """Append a cost record to the JSONL store."""
        parent = os.path.dirname(self.store_path)
        if parent:
            os.makedirs(parent, exist_ok=True)
        with open(self.store_path, "a", encoding="utf-8") as f:
            f.write(json.dumps(asdict(record)) + "\n")

    def _load_all(self) -> list[CostRecord]:
        """Load all records from the JSONL store."""
        if not os.path.exists(self.store_path):
            return []
        records: list[CostRecord] = []
        with open(self.store_path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                data = json.loads(line)
                records.append(CostRecord(**data))
        return records

    def query(
        self,
        agent_name: str | None = None,
        product: str | None = None,
        since: str | None = None,
    ) -> list[CostRecord]:
        """Query cost records with optional filters."""
        records = self._load_all()
        if agent_name is not None:
            records = [r for r in records if r.agent_name == agent_name]
        if product is not None:
            records = [r for r in records if r.product == product]
        if since is not None:
            records = [r for r in records if r.timestamp >= since]
        return records

    def summary(self, group_by: str = "agent_name") -> dict[str, float]:
        """Aggregate total cost grouped by a field."""
        records = self._load_all()
        totals: dict[str, float] = {}
        for r in records:
            key = getattr(r, group_by)
            totals[key] = totals.get(key, 0.0) + r.cost_usd
        return totals

"""Cost-budget enforcement for products and agents."""

from __future__ import annotations

import time
import threading
from dataclasses import dataclass, field
from enum import Enum
from typing import Callable, Optional


class AlertLevel(Enum):
    WARNING = "warning"    # e.g. 80% of cap
    CRITICAL = "critical"  # e.g. 95% of cap
    EXCEEDED = "exceeded"  # 100%+


@dataclass
class BudgetThreshold:
    warning_pct: float = 0.8
    critical_pct: float = 0.95
    notification_channels: list[str] = field(default_factory=lambda: ["slack"])
    cooldown_seconds: int = 3600  # avoid alert storms


@dataclass
class BudgetAlert:
    level: AlertLevel
    agent_name: str
    current_spend: float
    limit: float
    message: str


@dataclass
class CostBudget:
    """A spending cap for a product or agent."""

    name: str
    limit_usd: float
    period: str  # 'daily', 'monthly', 'total'
    warn_at_pct: int = 80  # percent of limit to trigger warning
    hard_stop: bool = False  # if True, raise BudgetExceededError on exceed

    def __post_init__(self) -> None:
        if self.limit_usd <= 0:
            raise ValueError(f"limit_usd must be > 0, got {self.limit_usd}")
        if self.period not in ("daily", "monthly", "total"):
            raise ValueError(
                f"period must be 'daily', 'monthly', or 'total', got {self.period!r}"
            )


class BudgetExceededError(Exception):
    """Raised when a hard spending cap is exceeded."""

    def __init__(
        self, budget_name: str, limit_usd: float, current_usd: float
    ) -> None:
        super().__init__(budget_name, limit_usd, current_usd)
        self.budget_name = budget_name
        self.limit_usd = limit_usd
        self.current_usd = current_usd


class BudgetEnforcer:
    """Tracks spend against configured budgets and fires callbacks on threshold crossings."""

    def __init__(self, threshold: Optional[BudgetThreshold] = None) -> None:
        self._lock = threading.Lock()
        self._budgets: dict[str, CostBudget] = {}
        self._spend: dict[str, float] = {}
        self._warned: set[str] = set()
        self._warning_callbacks: list[Callable[[str, float, float], None]] = []
        self._threshold = threshold or BudgetThreshold()
        self._last_alert_time: dict[str, float] = {}

    def add_budget(self, budget: CostBudget) -> None:
        with self._lock:
            self._budgets[budget.name] = budget
            self._spend.setdefault(budget.name, 0.0)

    def record_spend(self, name: str, cost_usd: float) -> float:
        with self._lock:
            if name not in self._budgets:
                raise KeyError(f"No budget registered for {name!r}")
            self._spend[name] = self._spend.get(name, 0.0) + cost_usd
            current = self._spend[name]
            budget = self._budgets[name]

            # Check warning threshold
            pct = (current / budget.limit_usd) * 100
            if pct >= budget.warn_at_pct and name not in self._warned:
                self._warned.add(name)
                for cb in self._warning_callbacks:
                    cb(name, current, budget.limit_usd)

            # Check hard stop
            if current > budget.limit_usd and budget.hard_stop:
                raise BudgetExceededError(name, budget.limit_usd, current)

            return current

    def check_budget(self, name: str) -> dict:
        with self._lock:
            if name not in self._budgets:
                raise KeyError(f"No budget registered for {name!r}")
            budget = self._budgets[name]
            current = self._spend.get(name, 0.0)
            pct = (current / budget.limit_usd) * 100
            return {
                "name": name,
                "limit_usd": budget.limit_usd,
                "current_spend_usd": current,
                "pct_used": round(pct, 2),
                "exceeded": current > budget.limit_usd,
            }

    def on_warning(self, callback: Callable[[str, float, float], None]) -> None:
        with self._lock:
            self._warning_callbacks.append(callback)

    def get_all_budgets(self) -> dict[str, dict]:
        with self._lock:
            result: dict[str, dict] = {}
            for name, budget in self._budgets.items():
                current = self._spend.get(name, 0.0)
                pct = (current / budget.limit_usd) * 100
                result[name] = {
                    "name": name,
                    "limit_usd": budget.limit_usd,
                    "current_spend_usd": current,
                    "pct_used": round(pct, 2),
                }
            return result

    def check_thresholds(self, agent_name: str) -> Optional[BudgetAlert]:
        """Compare current spend against configured thresholds, return alert if crossed."""
        with self._lock:
            if agent_name not in self._budgets:
                raise KeyError(f"No budget registered for {agent_name!r}")
            budget = self._budgets[agent_name]
            current = self._spend.get(agent_name, 0.0)
            ratio = current / budget.limit_usd

            if ratio >= 1.0:
                level = AlertLevel.EXCEEDED
            elif ratio >= self._threshold.critical_pct:
                level = AlertLevel.CRITICAL
            elif ratio >= self._threshold.warning_pct:
                level = AlertLevel.WARNING
            else:
                return None

            # Cooldown check
            now = time.monotonic()
            last = self._last_alert_time.get(agent_name, 0.0)
            if now - last < self._threshold.cooldown_seconds:
                return None

            self._last_alert_time[agent_name] = now
            pct_str = f"{ratio * 100:.1f}%"
            return BudgetAlert(
                level=level,
                agent_name=agent_name,
                current_spend=current,
                limit=budget.limit_usd,
                message=f"{agent_name} at {pct_str} of ${budget.limit_usd:.2f} budget ({level.value})",
            )

    def reset(self) -> None:
        with self._lock:
            self._budgets.clear()
            self._spend.clear()
            self._warned.clear()
            self._warning_callbacks.clear()
            self._last_alert_time.clear()

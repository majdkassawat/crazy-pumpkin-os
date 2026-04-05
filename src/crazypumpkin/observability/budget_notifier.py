"""Budget alert notification dispatcher."""

from __future__ import annotations

import logging

from crazypumpkin.observability.budget import BudgetAlert

logger = logging.getLogger(__name__)


class BudgetNotifier:
    """Dispatches budget alerts to configured notification channels."""

    def __init__(self) -> None:
        self._dispatched: list[BudgetAlert] = []

    async def dispatch(self, alert: BudgetAlert) -> None:
        """Dispatch a budget alert to notification channels."""
        logger.warning("Budget alert: %s", alert.message)
        self._dispatched.append(alert)

"""Observability package — structured logging and metrics."""

from crazypumpkin.observability.logging import get_logger, correlation_id_var
from crazypumpkin.observability.metrics import (
    record_task_completed,
    record_error,
    record_agent_uptime,
    get_metrics_snapshot,
)

__all__ = [
    "get_logger",
    "correlation_id_var",
    "record_task_completed",
    "record_error",
    "record_agent_uptime",
    "get_metrics_snapshot",
]

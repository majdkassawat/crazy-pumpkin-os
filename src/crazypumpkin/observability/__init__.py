"""Observability package — structured logging and metrics."""

from crazypumpkin.observability.logging import (
    agent_call_context,
    correlation_id_var,
    get_logger,
    start_pipeline_run,
)
from crazypumpkin.observability.metrics import (
    record_task_completed,
    record_error,
    record_agent_uptime,
    get_metrics_snapshot,
)

__all__ = [
    "agent_call_context",
    "correlation_id_var",
    "get_logger",
    "start_pipeline_run",
    "record_task_completed",
    "record_error",
    "record_agent_uptime",
    "get_metrics_snapshot",
]

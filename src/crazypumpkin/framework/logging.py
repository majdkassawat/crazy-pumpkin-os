"""Structured logging utilities for the crazy-pumpkin framework."""

import json
import logging
import time
from dataclasses import dataclass


class StructuredFormatter(logging.Formatter):
    """Formatter that emits JSON lines with structured fields."""

    def format(self, record: logging.LogRecord) -> str:
        data = {
            "timestamp": time.strftime(
                "%Y-%m-%dT%H:%M:%SZ", time.gmtime(record.created)
            ),
            "level": record.levelname,
            "message": record.getMessage(),
            "agent_id": getattr(record, "agent_id", None),
            "task_id": getattr(record, "task_id", None),
            "cycle_id": getattr(record, "cycle_id", None),
            "logger": record.name,
        }
        _standard = {
            "name", "msg", "args", "levelname", "levelno", "pathname",
            "filename", "module", "exc_info", "exc_text", "stack_info",
            "lineno", "funcName", "created", "msecs", "relativeCreated",
            "thread", "threadName", "processName", "process", "message",
            "taskName", "agent_id", "task_id", "cycle_id",
        }
        for key, value in record.__dict__.items():
            if key not in _standard:
                data[key] = value
        return json.dumps(data)


@dataclass
class AgentLogContext:
    """Holds agent/task/cycle identifiers for structured log injection."""

    agent_id: str
    task_id: str
    cycle_id: str

    def bind(self, logger: logging.Logger) -> logging.LoggerAdapter:
        """Return a LoggerAdapter that injects context fields into every record."""
        extra = {
            "agent_id": self.agent_id,
            "task_id": self.task_id,
            "cycle_id": self.cycle_id,
        }
        return logging.LoggerAdapter(logger, extra)


def configure_agent_logging(level: int = logging.INFO) -> logging.Logger:
    """Get or create the crazypumpkin.agent logger with structured formatting."""
    logger = logging.getLogger("crazypumpkin.agent")
    handler = logging.StreamHandler()
    handler.setFormatter(StructuredFormatter())
    logger.addHandler(handler)
    logger.setLevel(level)
    return logger

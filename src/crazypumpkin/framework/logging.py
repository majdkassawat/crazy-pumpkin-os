"""Structured JSON logging for agent pipelines."""

import json
import logging
import time
from dataclasses import dataclass


class StructuredFormatter(logging.Formatter):
    """Formats log records as single-line JSON objects."""

    def format(self, record: logging.LogRecord) -> str:
        payload: dict = {
            "timestamp": self.formatTime(record, self.datefmt),
            "level": record.levelname,
            "message": record.getMessage(),
            "agent_id": getattr(record, "agent_id", ""),
            "task_id": getattr(record, "task_id", ""),
            "cycle_id": getattr(record, "cycle_id", ""),
            "logger": record.name,
        }
        # Merge any extra fields that were injected via LoggerAdapter
        for key, value in vars(record).items():
            if key not in payload and key not in logging.LogRecord(
                "", 0, "", 0, "", (), None
            ).__dict__:
                payload[key] = value
        return json.dumps(payload)


@dataclass
class AgentLogContext:
    """Holds per-agent identifiers and binds them to a logger."""

    agent_id: str
    task_id: str
    cycle_id: str

    def bind(self, logger: logging.Logger) -> logging.LoggerAdapter:
        return logging.LoggerAdapter(
            logger,
            {
                "agent_id": self.agent_id,
                "task_id": self.task_id,
                "cycle_id": self.cycle_id,
            },
        )


def configure_agent_logging(level: int = logging.INFO) -> logging.Logger:
    """Create / configure the ``crazypumpkin.agent`` logger."""
    logger = logging.getLogger("crazypumpkin.agent")
    logger.setLevel(level)

    # Avoid duplicate handlers on repeated calls
    if not any(
        isinstance(h, logging.StreamHandler) and isinstance(h.formatter, StructuredFormatter)
        for h in logger.handlers
    ):
        handler = logging.StreamHandler()
        handler.setFormatter(StructuredFormatter())
        logger.addHandler(handler)

    return logger

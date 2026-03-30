"""Unit tests for crazypumpkin.framework.logging."""

import json
import logging
import sys
from pathlib import Path

import pytest

_src = str(Path(__file__).resolve().parent.parent / "src")
if _src not in sys.path:
    sys.path.insert(0, _src)

from crazypumpkin.framework.logging import (
    AgentLogContext,
    StructuredFormatter,
    configure_agent_logging,
)


class _CaptureHandler(logging.Handler):
    """Handler that stores formatted records for inspection."""

    def __init__(self):
        super().__init__()
        self.records: list[str] = []

    def emit(self, record: logging.LogRecord) -> None:
        self.records.append(self.format(record))


def test_structured_formatter_outputs_valid_json():
    formatter = StructuredFormatter()
    record = logging.LogRecord(
        name="test",
        level=logging.INFO,
        pathname="test.py",
        lineno=1,
        msg="hello world",
        args=None,
        exc_info=None,
    )
    output = formatter.format(record)
    parsed = json.loads(output)
    assert parsed["level"] == "INFO"
    assert parsed["message"] == "hello world"
    for key in ("timestamp", "level", "message", "agent_id", "task_id", "cycle_id", "logger"):
        assert key in parsed


def test_structured_formatter_includes_extra_fields():
    formatter = StructuredFormatter()
    record = logging.LogRecord(
        name="test",
        level=logging.DEBUG,
        pathname="test.py",
        lineno=1,
        msg="extra",
        args=None,
        exc_info=None,
    )
    record.custom_field = "custom_value"
    output = formatter.format(record)
    parsed = json.loads(output)
    assert parsed["custom_field"] == "custom_value"


def test_agent_log_context_bind_returns_adapter():
    ctx = AgentLogContext(agent_id="a1", task_id="t1", cycle_id="c1")
    logger = logging.getLogger("test_bind_adapter")
    adapter = ctx.bind(logger)
    assert isinstance(adapter, logging.LoggerAdapter)


def test_agent_log_context_bind_injects_fields():
    ctx = AgentLogContext(agent_id="a1", task_id="t1", cycle_id="c1")
    logger = logging.getLogger("test_bind_inject")
    logger.setLevel(logging.DEBUG)
    logger.handlers.clear()

    capture = _CaptureHandler()
    capture.setFormatter(StructuredFormatter())
    logger.addHandler(capture)

    adapter = ctx.bind(logger)
    adapter.info("test message")

    assert len(capture.records) >= 1
    parsed = json.loads(capture.records[0])
    assert parsed["agent_id"] == "a1"
    assert parsed["task_id"] == "t1"
    assert parsed["cycle_id"] == "c1"
    assert parsed["message"] == "test message"


def test_configure_agent_logging_returns_logger():
    logger = configure_agent_logging()
    assert isinstance(logger, logging.Logger)
    assert logger.name == "crazypumpkin.agent"


def test_configure_agent_logging_has_stream_handler_with_structured_formatter():
    logger = configure_agent_logging()
    stream_handlers = [
        h for h in logger.handlers if isinstance(h, logging.StreamHandler)
    ]
    assert len(stream_handlers) >= 1
    has_structured = any(
        isinstance(h.formatter, StructuredFormatter) for h in stream_handlers
    )
    assert has_structured


def test_configure_agent_logging_sets_level():
    logger = configure_agent_logging(level=logging.DEBUG)
    assert logger.level == logging.DEBUG


def test_module_importable():
    import crazypumpkin.framework.logging as mod

    assert hasattr(mod, "StructuredFormatter")
    assert hasattr(mod, "AgentLogContext")
    assert hasattr(mod, "configure_agent_logging")

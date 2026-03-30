"""Tests for crazypumpkin.framework.logging — structured JSON logging."""

import importlib
import json
import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

_log_mod = importlib.import_module("crazypumpkin.framework.logging")

StructuredFormatter = _log_mod.StructuredFormatter
AgentLogContext = _log_mod.AgentLogContext
configure_agent_logging = _log_mod.configure_agent_logging

REQUIRED_KEYS = {"timestamp", "level", "message", "agent_id", "task_id", "cycle_id"}


class _CaptureHandler(logging.Handler):
    """Handler that stores formatted records for inspection."""

    def __init__(self):
        super().__init__()
        self.records: list[str] = []

    def emit(self, record: logging.LogRecord) -> None:
        self.records.append(self.format(record))


# ── StructuredFormatter ──────────────────────────────────────────────


class TestStructuredFormatter:
    def _make_record(self, msg="hello", **extras):
        logger = logging.getLogger("test.formatter")
        record = logger.makeRecord(
            name="test.formatter",
            level=logging.INFO,
            fn="test.py",
            lno=1,
            msg=msg,
            args=(),
            exc_info=None,
        )
        for k, v in extras.items():
            setattr(record, k, v)
        return record

    def test_format_returns_valid_json(self):
        fmt = StructuredFormatter()
        record = self._make_record("test message")
        output = fmt.format(record)
        data = json.loads(output)
        assert isinstance(data, dict)

    def test_format_contains_required_keys(self):
        fmt = StructuredFormatter()
        record = self._make_record("msg", agent_id="a1", task_id="t1", cycle_id="c1")
        data = json.loads(fmt.format(record))
        for key in REQUIRED_KEYS:
            assert key in data, f"missing key: {key}"

    def test_format_values_match_record(self):
        fmt = StructuredFormatter()
        record = self._make_record("my msg", agent_id="ag", task_id="tk", cycle_id="cy")
        data = json.loads(fmt.format(record))
        assert data["level"] == "INFO"
        assert data["message"] == "my msg"
        assert data["agent_id"] == "ag"
        assert data["task_id"] == "tk"
        assert data["cycle_id"] == "cy"

    def test_format_defaults_empty_when_extras_missing(self):
        fmt = StructuredFormatter()
        record = self._make_record("bare")
        data = json.loads(fmt.format(record))
        assert data["agent_id"] == ""
        assert data["task_id"] == ""
        assert data["cycle_id"] == ""

    def test_format_includes_logger_name(self):
        fmt = StructuredFormatter()
        record = self._make_record("x")
        data = json.loads(fmt.format(record))
        assert data["logger"] == "test.formatter"

    def test_format_includes_extra_fields(self):
        fmt = StructuredFormatter()
        record = self._make_record("x", custom_field="custom_value")
        data = json.loads(fmt.format(record))
        assert data.get("custom_field") == "custom_value"


# ── AgentLogContext ──────────────────────────────────────────────────


class TestAgentLogContext:
    def test_bind_returns_logger_adapter(self):
        ctx = AgentLogContext(agent_id="a1", task_id="t1", cycle_id="c1")
        logger = logging.getLogger("test.bind")
        adapter = ctx.bind(logger)
        assert isinstance(adapter, logging.LoggerAdapter)

    def test_adapter_injects_fields(self):
        ctx = AgentLogContext(agent_id="a1", task_id="t1", cycle_id="c1")
        logger = logging.getLogger("test.inject")
        logger.handlers.clear()
        logger.setLevel(logging.DEBUG)
        fmt = StructuredFormatter()
        handler = logging.StreamHandler()
        handler.setFormatter(fmt)
        logger.addHandler(handler)

        adapter = ctx.bind(logger)

        # Capture formatted output via a custom handler
        captured = []

        class _InlineCapture(logging.Handler):
            def emit(self, record):
                captured.append(fmt.format(record))

        cap = _InlineCapture()
        logger.addHandler(cap)

        adapter.info("test log")

        assert len(captured) == 1
        data = json.loads(captured[0])
        assert data["agent_id"] == "a1"
        assert data["task_id"] == "t1"
        assert data["cycle_id"] == "c1"

    def test_is_dataclass(self):
        import dataclasses
        assert dataclasses.is_dataclass(AgentLogContext)


# ── configure_agent_logging ──────────────────────────────────────────


class TestConfigureAgentLogging:
    def _cleanup_logger(self):
        logger = logging.getLogger("crazypumpkin.agent")
        logger.handlers.clear()
        return logger

    def test_returns_logger(self):
        self._cleanup_logger()
        logger = configure_agent_logging()
        assert isinstance(logger, logging.Logger)

    def test_logger_name(self):
        self._cleanup_logger()
        logger = configure_agent_logging()
        assert logger.name == "crazypumpkin.agent"

    def test_has_stream_handler(self):
        self._cleanup_logger()
        logger = configure_agent_logging()
        stream_handlers = [h for h in logger.handlers if isinstance(h, logging.StreamHandler)]
        assert len(stream_handlers) >= 1

    def test_handler_uses_structured_formatter(self):
        self._cleanup_logger()
        logger = configure_agent_logging()
        stream_handlers = [h for h in logger.handlers if isinstance(h, logging.StreamHandler)]
        assert any(isinstance(h.formatter, StructuredFormatter) for h in stream_handlers)

    def test_sets_level(self):
        self._cleanup_logger()
        logger = configure_agent_logging(level=logging.DEBUG)
        assert logger.level == logging.DEBUG

    def test_no_duplicate_handlers_on_repeated_calls(self):
        self._cleanup_logger()
        configure_agent_logging()
        configure_agent_logging()
        logger = logging.getLogger("crazypumpkin.agent")
        structured = [
            h for h in logger.handlers
            if isinstance(h, logging.StreamHandler) and isinstance(h.formatter, StructuredFormatter)
        ]
        assert len(structured) == 1


# ── Module importability ─────────────────────────────────────────────


class TestModuleImport:
    def test_importable_as_framework_logging(self):
        mod = importlib.import_module("crazypumpkin.framework.logging")
        assert hasattr(mod, "StructuredFormatter")
        assert hasattr(mod, "AgentLogContext")
        assert hasattr(mod, "configure_agent_logging")


# ── End-to-end: configure + bind + log ───────────────────────────────


class TestEndToEnd:
    def test_full_pipeline_produces_valid_json(self):
        # Clean slate
        logger = logging.getLogger("crazypumpkin.agent")
        logger.handlers.clear()

        logger = configure_agent_logging(level=logging.DEBUG)
        ctx = AgentLogContext(agent_id="dev-1", task_id="task-42", cycle_id="cycle-7")
        adapter = ctx.bind(logger)

        captured = []
        fmt = StructuredFormatter()

        class _Cap(logging.Handler):
            def emit(self, record):
                captured.append(fmt.format(record))

        logger.addHandler(_Cap())

        adapter.info("Pipeline started")

        assert len(captured) == 1
        data = json.loads(captured[0])
        for key in REQUIRED_KEYS:
            assert key in data
        assert data["agent_id"] == "dev-1"
        assert data["task_id"] == "task-42"
        assert data["cycle_id"] == "cycle-7"
        assert data["message"] == "Pipeline started"
        assert data["level"] == "INFO"

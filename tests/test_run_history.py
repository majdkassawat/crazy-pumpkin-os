"""Tests for run history storage methods on Store."""

import asyncio
import importlib
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

_models = importlib.import_module("crazypumpkin.framework.models")
_store_mod = importlib.import_module("crazypumpkin.framework.store")

RunRecord = _models.RunRecord
Store = _store_mod.Store


def _make_record(run_id: str, agent_name: str = "agent", status: str = "success",
                 minutes_ago: int = 0) -> RunRecord:
    started = datetime.now(timezone.utc) - timedelta(minutes=minutes_ago)
    return RunRecord(
        run_id=run_id,
        agent_name=agent_name,
        started_at=started,
        status=status,
    )


def _run(coro):
    return asyncio.get_event_loop().run_until_complete(coro)


@pytest.fixture
def store():
    return Store()


# ── save / get round-trip ────────────────────────────────────────────


class TestSaveAndGet:
    def test_save_then_get(self, store):
        rec = _make_record("r1", agent_name="Bolt")
        _run(store.save_run_record(rec))
        got = _run(store.get_run_record("r1"))
        assert got is rec
        assert got.run_id == "r1"
        assert got.agent_name == "Bolt"

    def test_get_missing_returns_none(self, store):
        assert _run(store.get_run_record("no-such-id")) is None

    def test_overwrite_existing(self, store):
        rec1 = _make_record("r1", agent_name="A")
        rec2 = _make_record("r1", agent_name="B")
        _run(store.save_run_record(rec1))
        _run(store.save_run_record(rec2))
        got = _run(store.get_run_record("r1"))
        assert got.agent_name == "B"


# ── list ordering ────────────────────────────────────────────────────


class TestListOrdering:
    def test_newest_first(self, store):
        for i in range(5):
            _run(store.save_run_record(_make_record(f"r{i}", minutes_ago=i)))
        records = _run(store.list_run_records())
        # minutes_ago=0 is newest, should be first
        assert records[0].run_id == "r0"
        assert records[-1].run_id == "r4"
        timestamps = [r.started_at for r in records]
        assert timestamps == sorted(timestamps, reverse=True)


# ── filtering ────────────────────────────────────────────────────────


class TestFiltering:
    def test_filter_by_agent_name(self, store):
        _run(store.save_run_record(_make_record("r1", agent_name="Alpha")))
        _run(store.save_run_record(_make_record("r2", agent_name="Beta")))
        _run(store.save_run_record(_make_record("r3", agent_name="Alpha")))
        result = _run(store.list_run_records(agent_name="Alpha"))
        assert len(result) == 2
        assert all(r.agent_name == "Alpha" for r in result)

    def test_filter_by_status(self, store):
        _run(store.save_run_record(_make_record("r1", status="success")))
        _run(store.save_run_record(_make_record("r2", status="failure")))
        _run(store.save_run_record(_make_record("r3", status="success")))
        result = _run(store.list_run_records(status="failure"))
        assert len(result) == 1
        assert result[0].run_id == "r2"

    def test_filter_by_agent_name_and_status(self, store):
        _run(store.save_run_record(_make_record("r1", agent_name="A", status="success")))
        _run(store.save_run_record(_make_record("r2", agent_name="A", status="failure")))
        _run(store.save_run_record(_make_record("r3", agent_name="B", status="success")))
        result = _run(store.list_run_records(agent_name="A", status="success"))
        assert len(result) == 1
        assert result[0].run_id == "r1"

    def test_filter_no_match(self, store):
        _run(store.save_run_record(_make_record("r1", agent_name="X")))
        result = _run(store.list_run_records(agent_name="Z"))
        assert result == []


# ── pagination ───────────────────────────────────────────────────────


class TestPagination:
    def test_limit_and_offset(self, store):
        # Save 10 records; r0 has minutes_ago=9 (oldest), r9 has minutes_ago=0 (newest)
        for i in range(10):
            _run(store.save_run_record(_make_record(f"r{i}", minutes_ago=9 - i)))
        # Newest first: r9, r8, r7, r6, r5, r4, r3, r2, r1, r0
        result = _run(store.list_run_records(limit=3, offset=3))
        assert len(result) == 3
        assert [r.run_id for r in result] == ["r6", "r5", "r4"]

    def test_limit_clamps_to_available(self, store):
        for i in range(3):
            _run(store.save_run_record(_make_record(f"r{i}", minutes_ago=i)))
        result = _run(store.list_run_records(limit=100))
        assert len(result) == 3

    def test_offset_beyond_total(self, store):
        _run(store.save_run_record(_make_record("r1")))
        result = _run(store.list_run_records(offset=10))
        assert result == []

    def test_default_limit_is_50(self, store):
        for i in range(60):
            _run(store.save_run_record(_make_record(f"r{i}", minutes_ago=i)))
        result = _run(store.list_run_records())
        assert len(result) == 50


# ── lifecycle execute_run tests ──────────────────────────────────────

_lifecycle = importlib.import_module("crazypumpkin.agents.lifecycle")
execute_run = _lifecycle.execute_run

_registry_mod = importlib.import_module("crazypumpkin.framework.registry")
AgentRegistry = _registry_mod.AgentRegistry

Agent = _models.Agent
AgentRole = _models.AgentRole
AgentStatus = _models.AgentStatus


class _StubAgent:
    """Minimal concrete agent for lifecycle testing."""

    def __init__(self, agent):
        self.agent = agent

    @property
    def id(self):
        return self.agent.id

    @property
    def name(self):
        return self.agent.name

    @property
    def role(self):
        return self.agent.role

    def execute(self, task, context):
        raise NotImplementedError

    def can_handle(self, task):
        return True


class _FailingAgent(_StubAgent):
    def execute(self, task, context):
        raise RuntimeError("agent crashed")


def _make_registry(agent_id="a1", name="test-agent", status=AgentStatus.IDLE, agent_cls=_StubAgent):
    model = Agent(id=agent_id, name=name, role=AgentRole.EXECUTION, status=status)
    stub = agent_cls(model)
    registry = AgentRegistry()
    registry._agents[agent_id] = stub
    return registry, stub


class TestExecuteRunSuccess:
    def test_success_record_persisted(self, store):
        registry, _ = _make_registry(status=AgentStatus.IDLE)
        record = _run(execute_run(registry, "a1", store))
        assert record.status == "success"
        assert record.duration_ms is not None
        saved = _run(store.get_run_record(record.run_id))
        assert saved is not None
        assert saved.status == "success"
        assert saved.duration_ms is not None

    def test_finished_at_set_on_success(self, store):
        registry, _ = _make_registry(status=AgentStatus.IDLE)
        record = _run(execute_run(registry, "a1", store))
        assert record.finished_at is not None
        assert record.finished_at >= record.started_at


class TestExecuteRunFailure:
    def test_failure_with_task_error(self, store):
        registry, _ = _make_registry(status=AgentStatus.IDLE, agent_cls=_FailingAgent)
        record = _run(execute_run(registry, "a1", store, task="do-something"))
        assert record.status == "failure"
        assert record.error is not None
        assert "agent crashed" in record.error
        saved = _run(store.get_run_record(record.run_id))
        assert saved is not None
        assert saved.status == "failure"
        assert saved.error is not None

    def test_failure_when_agent_already_active(self, store):
        registry, _ = _make_registry(status=AgentStatus.ACTIVE)
        record = _run(execute_run(registry, "a1", store))
        assert record.status == "failure"
        assert record.error is not None
        assert "already running" in record.error


class TestRunIdUniqueness:
    def test_unique_run_ids_across_runs(self, store):
        ids = set()
        for _ in range(5):
            registry, _ = _make_registry(status=AgentStatus.IDLE)
            record = _run(execute_run(registry, "a1", store))
            ids.add(record.run_id)
        assert len(ids) == 5


class TestStartedAtBeforeExecution:
    def test_started_at_set_before_execution(self, store):
        before = datetime.now(timezone.utc)
        registry, _ = _make_registry(status=AgentStatus.IDLE)
        record = _run(execute_run(registry, "a1", store))
        assert isinstance(record.started_at, datetime)
        assert record.started_at >= before or (before - record.started_at).total_seconds() < 1

    def test_started_at_before_finished_at(self, store):
        registry, _ = _make_registry(status=AgentStatus.IDLE)
        record = _run(execute_run(registry, "a1", store))
        assert record.started_at <= record.finished_at

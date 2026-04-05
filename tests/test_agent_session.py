"""Tests for BaseAgent session integration."""

import asyncio
import sys
from pathlib import Path
from typing import Any

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from crazypumpkin.framework.agent import BaseAgent
from crazypumpkin.framework.models import Agent, AgentRole, Session, Task, TaskOutput
from crazypumpkin.framework.session import SessionStore
from crazypumpkin.framework.store import Store


# ---------------------------------------------------------------------------
# Concrete subclass for testing
# ---------------------------------------------------------------------------

class _StubAgent(BaseAgent):
    """Minimal concrete BaseAgent that returns a fixed TaskOutput."""

    def __init__(self, agent: Agent, *, output: str = "ok"):
        super().__init__(agent)
        self._output = output

    def execute(self, task: Task, context: dict[str, Any]) -> TaskOutput:
        return TaskOutput(content=self._output)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_agent(name: str = "test-agent") -> Agent:
    return Agent(name=name, role=AgentRole.EXECUTION)


def _make_task(title: str = "Do something", desc: str = "desc") -> Task:
    return Task(title=title, description=desc, acceptance_criteria=["a"])


def _run(coro):
    return asyncio.new_event_loop().run_until_complete(coro)


# ---------------------------------------------------------------------------
# Tests: start_session
# ---------------------------------------------------------------------------

class TestStartSession:

    def test_creates_session(self):
        agent = _StubAgent(_make_agent("sess-agent"))
        session = _run(agent.start_session())
        assert isinstance(session, Session)
        assert session.agent_name == "sess-agent"
        assert session.status == "active"

    def test_sets_current_session(self):
        agent = _StubAgent(_make_agent())
        session = _run(agent.start_session())
        assert agent._current_session is not None
        assert agent._current_session.session_id == session.session_id

    def test_sets_session_store(self):
        agent = _StubAgent(_make_agent())
        _run(agent.start_session())
        assert agent._session_store is not None

    def test_custom_max_turns(self):
        agent = _StubAgent(_make_agent())
        session = _run(agent.start_session(max_turns=10))
        assert session.max_turns == 10

    def test_default_max_turns(self):
        agent = _StubAgent(_make_agent())
        session = _run(agent.start_session())
        assert session.max_turns == 50


# ---------------------------------------------------------------------------
# Tests: resume_session
# ---------------------------------------------------------------------------

class TestResumeSession:

    def test_resumes_existing_session(self):
        agent = _StubAgent(_make_agent("res-agent"))
        session = _run(agent.start_session())
        sid = session.session_id

        # Clear current session to simulate fresh state
        agent._current_session = None

        resumed = _run(agent.resume_session(sid))
        assert resumed.session_id == sid
        assert resumed.agent_name == "res-agent"

    def test_sets_current_session(self):
        agent = _StubAgent(_make_agent())
        session = _run(agent.start_session())
        sid = session.session_id
        agent._current_session = None

        _run(agent.resume_session(sid))
        assert agent._current_session is not None
        assert agent._current_session.session_id == sid

    def test_raises_for_nonexistent(self):
        agent = _StubAgent(_make_agent())
        # Need a session store first
        agent._session_store = SessionStore(Store())
        with pytest.raises(KeyError):
            _run(agent.resume_session("nonexistent-id"))


# ---------------------------------------------------------------------------
# Tests: end_session
# ---------------------------------------------------------------------------

class TestEndSession:

    def test_closes_session(self):
        agent = _StubAgent(_make_agent())
        session = _run(agent.start_session())
        closed = _run(agent.end_session())
        assert closed.status == "completed"

    def test_clears_current_session(self):
        agent = _StubAgent(_make_agent())
        _run(agent.start_session())
        _run(agent.end_session())
        assert agent._current_session is None

    def test_raises_when_no_session(self):
        agent = _StubAgent(_make_agent())
        with pytest.raises(RuntimeError):
            _run(agent.end_session())


# ---------------------------------------------------------------------------
# Tests: run with active session records messages
# ---------------------------------------------------------------------------

class TestRunWithSession:

    def test_records_user_and_assistant_messages(self):
        agent = _StubAgent(_make_agent(), output="agent response")
        _run(agent.start_session())

        task = _make_task(title="Test task", desc="Test description")
        agent.run(task, {})

        messages = agent.get_session_messages()
        assert len(messages) == 2
        assert messages[0]["role"] == "user"
        assert "Test task" in messages[0]["content"]
        assert messages[1]["role"] == "assistant"
        assert messages[1]["content"] == "agent response"

    def test_multiple_runs_accumulate_messages(self):
        agent = _StubAgent(_make_agent(), output="response")
        _run(agent.start_session())

        agent.run(_make_task(title="Task 1"), {})
        agent.run(_make_task(title="Task 2"), {})

        messages = agent.get_session_messages()
        assert len(messages) == 4  # 2 user + 2 assistant
        assert messages[0]["role"] == "user"
        assert messages[1]["role"] == "assistant"
        assert messages[2]["role"] == "user"
        assert messages[3]["role"] == "assistant"

    def test_session_messages_in_context(self):
        """When a session is active, context should contain session_messages."""
        received_contexts = []

        class _CapturingAgent(BaseAgent):
            def execute(self, task, context):
                received_contexts.append(dict(context))
                return TaskOutput(content="ok")

        agent = _CapturingAgent(_make_agent())
        _run(agent.start_session())

        # First run - session has no prior messages yet at context build time
        agent.run(_make_task(), {})
        # Second run - should have prior messages in context
        agent.run(_make_task(), {})

        assert "session_messages" in received_contexts[1]
        # 2 from first run (user + assistant) + 1 user message from second run (appended before execute)
        assert len(received_contexts[1]["session_messages"]) == 3


# ---------------------------------------------------------------------------
# Tests: get_session_messages
# ---------------------------------------------------------------------------

class TestGetSessionMessages:

    def test_returns_empty_when_no_session(self):
        agent = _StubAgent(_make_agent())
        assert agent.get_session_messages() == []

    def test_returns_messages_as_dicts(self):
        agent = _StubAgent(_make_agent(), output="hello")
        _run(agent.start_session())
        agent.run(_make_task(), {})

        messages = agent.get_session_messages()
        assert isinstance(messages, list)
        for m in messages:
            assert isinstance(m, dict)
            assert "role" in m
            assert "content" in m


# ---------------------------------------------------------------------------
# Tests: backward compatibility (no session active)
# ---------------------------------------------------------------------------

class TestBackwardCompatibility:

    def test_run_works_without_session(self):
        agent = _StubAgent(_make_agent())
        task = _make_task()
        result = agent.run(task, {})
        assert isinstance(result, TaskOutput)
        assert result.content == "ok"

    def test_no_session_fields_set_by_default(self):
        agent = _StubAgent(_make_agent())
        assert agent._session_store is None
        assert agent._current_session is None

    def test_context_unchanged_without_session(self):
        received_contexts = []

        class _CapturingAgent(BaseAgent):
            def execute(self, task, context):
                received_contexts.append(context)
                return TaskOutput(content="ok")

        agent = _CapturingAgent(_make_agent())
        original_ctx = {"key": "value"}
        agent.run(_make_task(), original_ctx)

        assert "session_messages" not in received_contexts[0]
        assert received_contexts[0] is original_ctx

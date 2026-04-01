"""Integration tests for multi-turn sessions with mocked LLM.

Tests full session lifecycle: create, multi-turn exchanges, context window
management, and cleanup.
"""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from crazypumpkin.framework.models import Session, SessionMessage, SessionStatus
from crazypumpkin.framework.store import Store
from crazypumpkin.llm.base import LLMProvider
from crazypumpkin.llm.registry import ProviderRegistry


# ---------------------------------------------------------------------------
# Mock provider that echoes back with turn counting
# ---------------------------------------------------------------------------


class MockSessionProvider(LLMProvider):
    """Mock LLM that tracks conversation turns and echoes context length."""

    def __init__(self, config: dict | None = None) -> None:
        self.config = config or {}
        self.call_count = 0
        self.last_messages: list[dict] = []

    def call(self, prompt, *, model=None, timeout=None, cwd=None,
             tools=None, system=None, cache=True):
        self.call_count += 1
        return f"response-{self.call_count}"

    def call_json(self, prompt, **kwargs):
        return {"turn": self.call_count}

    def call_multi_turn(self, prompt, *, max_turns=10, tools=None,
                        timeout=None, cwd=None, system=None, cache=True):
        self.call_count += 1
        return f"multi-turn-response-{self.call_count}"

    def call_session(self, messages, *, model=None, timeout=None,
                     system=None, cache=True):
        self.call_count += 1
        self.last_messages = list(messages)
        user_msg = messages[-1]["content"] if messages else ""
        reply = f"reply-{self.call_count}: received {len(messages)} messages, last='{user_msg}'"
        updated = list(messages) + [{"role": "assistant", "content": reply}]
        return reply, updated


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def store(tmp_path):
    return Store(tmp_path)


@pytest.fixture()
def mock_provider():
    return MockSessionProvider()


@pytest.fixture()
def registry(mock_provider):
    """ProviderRegistry wired to the mock provider."""
    config = {
        "default_provider": "mock",
        "providers": {},
    }
    reg = ProviderRegistry.__new__(ProviderRegistry)
    reg._config = config
    reg._store = None
    reg._default_provider_name = "mock"
    reg._agent_models = {}
    reg._providers = {"mock": mock_provider}
    return reg


# ---------------------------------------------------------------------------
# Session creation
# ---------------------------------------------------------------------------


class TestSessionCreate:
    def test_create_session(self, store):
        session = Session(id="s1", agent_id="agent-a", model="test-model")
        store.create_session(session)
        assert store.get_session("s1") is session
        assert session.status == SessionStatus.OPEN
        assert session.messages == []

    def test_create_multiple_sessions(self, store):
        for i in range(3):
            store.create_session(Session(id=f"s{i}", agent_id="agent-a", model="m"))
        assert len(store.sessions) == 3

    def test_sessions_by_agent(self, store):
        store.create_session(Session(id="s1", agent_id="a1", model="m"))
        store.create_session(Session(id="s2", agent_id="a2", model="m"))
        store.create_session(Session(id="s3", agent_id="a1", model="m"))
        results = store.sessions_by_agent("a1")
        assert {s.id for s in results} == {"s1", "s3"}


# ---------------------------------------------------------------------------
# Multi-turn exchanges with mocked LLM
# ---------------------------------------------------------------------------


class TestMultiTurnExchanges:
    def test_single_turn(self, store, mock_provider):
        """One user message, one assistant reply."""
        session = Session(id="s1", agent_id="dev", model="test")
        store.create_session(session)

        # User sends first message
        user_msg = SessionMessage(role="user", content="Hello")
        store.append_session_message("s1", user_msg)

        # Call mocked LLM
        messages = [{"role": m.role, "content": m.content} for m in session.messages]
        reply_text, _ = mock_provider.call_session(messages)

        # Record assistant reply
        store.append_session_message("s1", SessionMessage(role="assistant", content=reply_text))

        assert len(session.messages) == 2
        assert session.messages[0].role == "user"
        assert session.messages[1].role == "assistant"
        assert "reply-1" in session.messages[1].content

    def test_three_turn_conversation(self, store, mock_provider):
        """Three full user/assistant turn pairs."""
        session = Session(id="s1", agent_id="dev", model="test")
        store.create_session(session)

        conversation_messages: list[dict] = []
        for turn in range(3):
            user_text = f"Question {turn + 1}"
            store.append_session_message("s1", SessionMessage(role="user", content=user_text))
            conversation_messages.append({"role": "user", "content": user_text})

            reply_text, conversation_messages = mock_provider.call_session(conversation_messages)
            store.append_session_message("s1", SessionMessage(role="assistant", content=reply_text))

        assert len(session.messages) == 6
        # Verify alternating roles
        for i, msg in enumerate(session.messages):
            expected_role = "user" if i % 2 == 0 else "assistant"
            assert msg.role == expected_role

    def test_provider_receives_full_history(self, store, mock_provider):
        """The mock provider sees all prior messages on each call."""
        session = Session(id="s1", agent_id="dev", model="test")
        store.create_session(session)

        conversation_messages: list[dict] = []
        for turn in range(4):
            user_text = f"msg-{turn}"
            conversation_messages.append({"role": "user", "content": user_text})
            store.append_session_message("s1", SessionMessage(role="user", content=user_text))

            reply_text, conversation_messages = mock_provider.call_session(conversation_messages)
            store.append_session_message("s1", SessionMessage(role="assistant", content=reply_text))

        # After 4 turns the provider should have seen 7 messages on the last call
        # (4 user + 3 assistant before the 4th reply was added)
        assert len(mock_provider.last_messages) == 7
        assert mock_provider.last_messages[-1]["content"] == "msg-3"

    def test_via_registry(self, store, registry, mock_provider):
        """Multi-turn exchange routed through ProviderRegistry.call_session."""
        session = Session(id="s1", agent_id="dev", model="test")
        store.create_session(session)

        conversation_messages: list[dict] = []
        for turn in range(2):
            user_text = f"turn-{turn}"
            conversation_messages.append({"role": "user", "content": user_text})
            store.append_session_message("s1", SessionMessage(role="user", content=user_text))

            reply_text, conversation_messages = registry.call_session(conversation_messages)
            store.append_session_message("s1", SessionMessage(role="assistant", content=reply_text))

        assert len(session.messages) == 4
        assert mock_provider.call_count == 2


# ---------------------------------------------------------------------------
# Context window management
# ---------------------------------------------------------------------------


def _trim_to_window(messages: list[dict], max_messages: int) -> list[dict]:
    """Trim conversation history to fit a context window, keeping the
    system message (if any) and the most recent messages."""
    if len(messages) <= max_messages:
        return messages

    # Preserve system message if present
    if messages and messages[0].get("role") == "system":
        return [messages[0]] + messages[-(max_messages - 1):]
    return messages[-max_messages:]


class TestContextWindowManagement:
    def test_trim_keeps_recent(self):
        """Trimming keeps the N most recent messages."""
        msgs = [{"role": "user", "content": f"m{i}"} for i in range(20)]
        trimmed = _trim_to_window(msgs, max_messages=6)
        assert len(trimmed) == 6
        assert trimmed[0]["content"] == "m14"
        assert trimmed[-1]["content"] == "m19"

    def test_trim_preserves_system_message(self):
        """System message is always kept when trimming."""
        msgs = [{"role": "system", "content": "You are helpful."}]
        msgs += [{"role": "user", "content": f"m{i}"} for i in range(10)]
        trimmed = _trim_to_window(msgs, max_messages=4)
        assert len(trimmed) == 4
        assert trimmed[0]["role"] == "system"
        assert trimmed[0]["content"] == "You are helpful."
        assert trimmed[-1]["content"] == "m9"

    def test_no_trim_below_max(self):
        """Messages within the window are untouched."""
        msgs = [{"role": "user", "content": f"m{i}"} for i in range(3)]
        trimmed = _trim_to_window(msgs, max_messages=10)
        assert trimmed == msgs

    def test_trimmed_session_with_mock_llm(self, store, mock_provider):
        """Simulate a long conversation where we trim before each LLM call."""
        session = Session(id="s1", agent_id="dev", model="test")
        store.create_session(session)

        max_window = 6  # keep at most 6 messages in the context
        conversation_messages: list[dict] = []

        for turn in range(10):
            user_text = f"question-{turn}"
            conversation_messages.append({"role": "user", "content": user_text})
            store.append_session_message("s1", SessionMessage(role="user", content=user_text))

            # Trim before sending to LLM
            windowed = _trim_to_window(conversation_messages, max_window)
            reply_text, _ = mock_provider.call_session(windowed)

            conversation_messages.append({"role": "assistant", "content": reply_text})
            store.append_session_message("s1", SessionMessage(role="assistant", content=reply_text))

        # Store keeps the full history
        assert len(session.messages) == 20
        # But the LLM only ever saw at most max_window messages
        assert len(mock_provider.last_messages) <= max_window

    def test_trimmed_context_preserves_latest_user(self, store, mock_provider):
        """After trimming, the latest user message is always present."""
        conversation_messages: list[dict] = []
        for i in range(15):
            conversation_messages.append({"role": "user", "content": f"u{i}"})
            conversation_messages.append({"role": "assistant", "content": f"a{i}"})
        conversation_messages.append({"role": "user", "content": "final-question"})

        windowed = _trim_to_window(conversation_messages, max_messages=4)
        reply, _ = mock_provider.call_session(windowed)
        assert mock_provider.last_messages[-1]["content"] == "final-question"


# ---------------------------------------------------------------------------
# Session cleanup
# ---------------------------------------------------------------------------


class TestSessionCleanup:
    def test_close_session(self, store):
        session = Session(id="s1", agent_id="dev", model="test")
        store.create_session(session)
        store.append_session_message("s1", SessionMessage(role="user", content="hi"))
        store.close_session("s1")
        assert session.status == SessionStatus.CLOSED
        assert session.closed_at != ""

    def test_cannot_append_to_closed_session(self, store):
        session = Session(id="s1", agent_id="dev", model="test")
        store.create_session(session)
        store.close_session("s1")
        with pytest.raises(ValueError, match="Cannot append"):
            store.append_session_message("s1", SessionMessage(role="user", content="late"))

    def test_cannot_close_already_closed(self, store):
        session = Session(id="s1", agent_id="dev", model="test")
        store.create_session(session)
        store.close_session("s1")
        with pytest.raises(ValueError, match="already"):
            store.close_session("s1")

    def test_close_nonexistent_raises(self, store):
        with pytest.raises(KeyError):
            store.close_session("no-such-session")

    def test_append_nonexistent_raises(self, store):
        with pytest.raises(KeyError):
            store.append_session_message("no-such", SessionMessage(role="user", content="x"))


# ---------------------------------------------------------------------------
# Persistence round-trip
# ---------------------------------------------------------------------------


class TestSessionPersistence:
    def test_save_and_load(self, store):
        """Sessions survive a save/load cycle."""
        s = Session(id="s1", agent_id="dev", model="gpt-4")
        s.messages = [
            SessionMessage(role="user", content="Hello"),
            SessionMessage(role="assistant", content="Hi!"),
            SessionMessage(role="user", content="How are you?"),
            SessionMessage(role="assistant", content="Good, thanks."),
        ]
        store.create_session(s)
        store.save()

        store2 = Store(store._data_dir)
        store2.load()
        loaded = store2.get_session("s1")
        assert loaded is not None
        assert loaded.agent_id == "dev"
        assert loaded.model == "gpt-4"
        assert loaded.status == SessionStatus.OPEN
        assert len(loaded.messages) == 4
        assert loaded.messages[0].content == "Hello"
        assert loaded.messages[3].content == "Good, thanks."

    def test_closed_session_persists(self, store):
        """Closed status and closed_at survive save/load."""
        s = Session(id="s1", agent_id="dev", model="test")
        store.create_session(s)
        store.append_session_message("s1", SessionMessage(role="user", content="bye"))
        store.close_session("s1")
        store.save()

        store2 = Store(store._data_dir)
        store2.load()
        loaded = store2.get_session("s1")
        assert loaded.status == SessionStatus.CLOSED
        assert loaded.closed_at != ""

    def test_multiple_sessions_persist(self, store):
        """Multiple sessions with different states survive round-trip."""
        s1 = Session(id="s1", agent_id="a1", model="m1")
        s1.messages = [SessionMessage(role="user", content="q1")]
        store.create_session(s1)

        s2 = Session(id="s2", agent_id="a2", model="m2")
        s2.messages = [
            SessionMessage(role="user", content="q2"),
            SessionMessage(role="assistant", content="a2"),
        ]
        store.create_session(s2)
        store.close_session("s2")

        store.save()

        store2 = Store(store._data_dir)
        store2.load()
        assert len(store2.sessions) == 2
        assert store2.get_session("s1").status == SessionStatus.OPEN
        assert store2.get_session("s2").status == SessionStatus.CLOSED

    def test_message_metadata_persists(self, store):
        """Message metadata survives save/load."""
        s = Session(id="s1", agent_id="dev", model="test")
        s.messages = [
            SessionMessage(role="user", content="hi", metadata={"token_count": 5}),
        ]
        store.create_session(s)
        store.save()

        store2 = Store(store._data_dir)
        store2.load()
        loaded = store2.get_session("s1")
        assert loaded.messages[0].metadata == {"token_count": 5}


# ---------------------------------------------------------------------------
# Full lifecycle integration
# ---------------------------------------------------------------------------


class TestFullLifecycle:
    def test_create_converse_persist_resume_close(self, tmp_path, mock_provider):
        """End-to-end: create session, multi-turn with mocked LLM, persist,
        reload, continue conversation, then close."""
        store = Store(tmp_path)

        # 1. Create session
        session = Session(id="lifecycle", agent_id="dev", model="test")
        store.create_session(session)

        # 2. Two-turn conversation
        conv: list[dict] = []
        for turn in range(2):
            user_text = f"q{turn}"
            conv.append({"role": "user", "content": user_text})
            store.append_session_message("lifecycle", SessionMessage(role="user", content=user_text))

            reply, conv = mock_provider.call_session(conv)
            store.append_session_message("lifecycle", SessionMessage(role="assistant", content=reply))

        assert len(session.messages) == 4
        store.save()

        # 3. Reload in a fresh store
        store2 = Store(tmp_path)
        store2.load()
        loaded = store2.get_session("lifecycle")
        assert loaded.status == SessionStatus.OPEN
        assert len(loaded.messages) == 4

        # 4. Resume conversation from loaded state
        conv2 = [{"role": m.role, "content": m.content} for m in loaded.messages]
        conv2.append({"role": "user", "content": "follow-up"})
        store2.append_session_message("lifecycle", SessionMessage(role="user", content="follow-up"))

        reply2, conv2 = mock_provider.call_session(conv2)
        store2.append_session_message("lifecycle", SessionMessage(role="assistant", content=reply2))

        assert len(loaded.messages) == 6
        assert "follow-up" in loaded.messages[4].content

        # 5. Close
        store2.close_session("lifecycle")
        assert loaded.status == SessionStatus.CLOSED

        # 6. Persist final state
        store2.save()
        store3 = Store(tmp_path)
        store3.load()
        final = store3.get_session("lifecycle")
        assert final.status == SessionStatus.CLOSED
        assert len(final.messages) == 6

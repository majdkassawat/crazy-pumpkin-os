"""Tests for ClaudeSDKAgent."""

import sys
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from crazypumpkin.framework.agent import ClaudeSDKAgent
from crazypumpkin.framework.models import Agent, AgentConfig, AgentRole, Task, TaskOutput


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_agent(**kwargs) -> Agent:
    defaults = {"name": "test-claude-sdk", "role": AgentRole.EXECUTION}
    defaults.update(kwargs)
    return Agent(**defaults)


def _make_task(title: str = "Summarise module", description: str = "Summarise the utils module.") -> Task:
    return Task(
        title=title,
        description=description,
        acceptance_criteria=["Must be concise"],
    )


def _fake_response(text: str = "Done."):
    """Build a minimal object mimicking anthropic Messages response."""
    block = SimpleNamespace(text=text)
    return SimpleNamespace(content=[block])


# ---------------------------------------------------------------------------
# Construction
# ---------------------------------------------------------------------------

class TestClaudeSDKAgentInit:
    def test_subclasses_base_agent(self):
        from crazypumpkin.framework.agent import BaseAgent
        agent = ClaudeSDKAgent(_make_agent())
        assert isinstance(agent, BaseAgent)

    def test_default_tool_permissions(self):
        agent = ClaudeSDKAgent(_make_agent())
        assert agent.tool_permissions == {"read": True, "write": False, "bash": False}

    def test_custom_tool_permissions(self):
        perms = {"read": True, "write": True, "bash": True}
        agent = ClaudeSDKAgent(_make_agent(), tool_permissions=perms)
        assert agent.tool_permissions == perms

    def test_history_starts_empty(self):
        agent = ClaudeSDKAgent(_make_agent())
        assert agent._history == []


# ---------------------------------------------------------------------------
# Tool building
# ---------------------------------------------------------------------------

class TestBuildTools:
    def test_read_only_includes_text_editor(self):
        agent = ClaudeSDKAgent(_make_agent(), tool_permissions={"read": True, "write": False, "bash": False})
        tools = agent._build_tools()
        assert len(tools) == 1
        assert tools[0]["type"] == "text_editor_20250429"

    def test_write_includes_text_editor(self):
        agent = ClaudeSDKAgent(_make_agent(), tool_permissions={"read": False, "write": True, "bash": False})
        tools = agent._build_tools()
        assert any(t["type"] == "text_editor_20250429" for t in tools)

    def test_bash_includes_bash_tool(self):
        agent = ClaudeSDKAgent(_make_agent(), tool_permissions={"read": False, "write": False, "bash": True})
        tools = agent._build_tools()
        assert len(tools) == 1
        assert tools[0]["type"] == "bash_20250429"

    def test_all_permissions_yield_two_tools(self):
        agent = ClaudeSDKAgent(_make_agent(), tool_permissions={"read": True, "write": True, "bash": True})
        tools = agent._build_tools()
        types = {t["type"] for t in tools}
        assert types == {"text_editor_20250429", "bash_20250429"}

    def test_no_permissions_yield_empty(self):
        agent = ClaudeSDKAgent(_make_agent(), tool_permissions={"read": False, "write": False, "bash": False})
        tools = agent._build_tools()
        assert tools == []


# ---------------------------------------------------------------------------
# Execute
# ---------------------------------------------------------------------------

class TestClaudeSDKAgentExecute:
    @mock.patch("anthropic.Anthropic")
    def test_returns_task_output(self, MockAnthropic):
        client = MockAnthropic.return_value
        client.messages.create.return_value = _fake_response("result text")

        agent = ClaudeSDKAgent(_make_agent())
        result = agent.execute(_make_task(), {})

        assert isinstance(result, TaskOutput)
        assert result.content == "result text"

    @mock.patch("anthropic.Anthropic")
    def test_history_grows_after_execute(self, MockAnthropic):
        client = MockAnthropic.return_value
        client.messages.create.return_value = _fake_response("first")

        agent = ClaudeSDKAgent(_make_agent())
        agent.execute(_make_task(), {})

        assert len(agent._history) == 2  # user + assistant
        assert agent._history[0]["role"] == "user"
        assert agent._history[1]["role"] == "assistant"

    @mock.patch("anthropic.Anthropic")
    def test_multi_turn_preserves_history(self, MockAnthropic):
        client = MockAnthropic.return_value
        client.messages.create.side_effect = [
            _fake_response("first"),
            _fake_response("second"),
        ]

        agent = ClaudeSDKAgent(_make_agent())
        agent.execute(_make_task(title="Task A"), {})
        agent.execute(_make_task(title="Task B"), {})

        # After two calls: user1, assistant1, user2, assistant2
        assert len(agent._history) == 4
        # The second SDK call should include prior turns (user1 + assistant1 + user2)
        second_call_messages = client.messages.create.call_args_list[1].kwargs["messages"]
        assert len(second_call_messages) == 3
        assert second_call_messages[0]["role"] == "user"
        assert second_call_messages[1]["role"] == "assistant"
        assert second_call_messages[2]["role"] == "user"

    @mock.patch("anthropic.Anthropic")
    def test_uses_agent_config_model(self, MockAnthropic):
        client = MockAnthropic.return_value
        client.messages.create.return_value = _fake_response()

        agent_model = _make_agent(config=AgentConfig(model="claude-opus-4-20250514"))
        agent = ClaudeSDKAgent(agent_model)
        agent.execute(_make_task(), {})

        call_kwargs = client.messages.create.call_args.kwargs
        assert call_kwargs["model"] == "claude-opus-4-20250514"

    @mock.patch("anthropic.Anthropic")
    def test_defaults_to_sonnet_when_model_empty(self, MockAnthropic):
        client = MockAnthropic.return_value
        client.messages.create.return_value = _fake_response()

        agent = ClaudeSDKAgent(_make_agent())
        agent.execute(_make_task(), {})

        call_kwargs = client.messages.create.call_args.kwargs
        assert call_kwargs["model"] == ClaudeSDKAgent.DEFAULT_MODEL

    @mock.patch("anthropic.Anthropic")
    def test_tools_omitted_when_no_permissions(self, MockAnthropic):
        client = MockAnthropic.return_value
        client.messages.create.return_value = _fake_response()

        agent = ClaudeSDKAgent(
            _make_agent(),
            tool_permissions={"read": False, "write": False, "bash": False},
        )
        agent.execute(_make_task(), {})

        call_kwargs = client.messages.create.call_args.kwargs
        assert "tools" not in call_kwargs

    @mock.patch("anthropic.Anthropic")
    def test_tools_included_when_permissions_set(self, MockAnthropic):
        client = MockAnthropic.return_value
        client.messages.create.return_value = _fake_response()

        agent = ClaudeSDKAgent(
            _make_agent(),
            tool_permissions={"read": True, "write": False, "bash": True},
        )
        agent.execute(_make_task(), {})

        call_kwargs = client.messages.create.call_args.kwargs
        assert "tools" in call_kwargs
        types = {t["type"] for t in call_kwargs["tools"]}
        assert "text_editor_20250429" in types
        assert "bash_20250429" in types

    @mock.patch("anthropic.Anthropic")
    def test_prompt_contains_task_title(self, MockAnthropic):
        client = MockAnthropic.return_value
        client.messages.create.return_value = _fake_response()

        agent = ClaudeSDKAgent(_make_agent())
        agent.execute(_make_task(title="Refactor FooBar"), {})

        messages = client.messages.create.call_args.kwargs["messages"]
        assert "Refactor FooBar" in messages[0]["content"]

    @mock.patch("anthropic.Anthropic")
    def test_multiple_text_blocks_joined(self, MockAnthropic):
        client = MockAnthropic.return_value
        block1 = SimpleNamespace(text="Hello")
        block2 = SimpleNamespace(text="World")
        client.messages.create.return_value = SimpleNamespace(content=[block1, block2])

        agent = ClaudeSDKAgent(_make_agent())
        result = agent.execute(_make_task(), {})

        assert result.content == "Hello\nWorld"

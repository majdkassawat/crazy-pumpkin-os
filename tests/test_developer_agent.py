"""Tests for DeveloperAgent."""

import sys
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from crazypumpkin.agents.developer_agent import DeveloperAgent
from crazypumpkin.framework.agent import ClaudeSDKAgent
from crazypumpkin.framework.models import Agent, AgentConfig, AgentRole, Task, TaskOutput


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_agent(**kwargs) -> Agent:
    defaults = {"name": "test-developer", "role": AgentRole.EXECUTION}
    defaults.update(kwargs)
    return Agent(**defaults)


def _make_task(
    title: str = "Implement feature",
    description: str = "Add a helper function.",
) -> Task:
    return Task(
        title=title,
        description=description,
        acceptance_criteria=["Must have type hints"],
    )


def _fake_response(text: str = "Done."):
    block = SimpleNamespace(text=text)
    return SimpleNamespace(content=[block])


# ---------------------------------------------------------------------------
# Construction
# ---------------------------------------------------------------------------

class TestDeveloperAgentInit:
    def test_subclasses_claude_sdk_agent(self):
        agent = DeveloperAgent(_make_agent())
        assert isinstance(agent, ClaudeSDKAgent)

    def test_read_permission_enabled(self):
        agent = DeveloperAgent(_make_agent())
        assert agent.tool_permissions["read"] is True

    def test_write_permission_enabled(self):
        agent = DeveloperAgent(_make_agent())
        assert agent.tool_permissions["write"] is True

    def test_bash_permission_disabled(self):
        agent = DeveloperAgent(_make_agent())
        assert agent.tool_permissions["bash"] is False

    def test_tools_include_text_editor(self):
        agent = DeveloperAgent(_make_agent())
        tools = agent._build_tools()
        types = {t["type"] for t in tools}
        assert "text_editor_20250429" in types

    def test_tools_exclude_bash(self):
        agent = DeveloperAgent(_make_agent())
        tools = agent._build_tools()
        types = {t["type"] for t in tools}
        assert "bash_20250429" not in types


# ---------------------------------------------------------------------------
# Execute
# ---------------------------------------------------------------------------

class TestDeveloperAgentExecute:
    @mock.patch("anthropic.Anthropic")
    def test_returns_task_output(self, MockAnthropic):
        client = MockAnthropic.return_value
        client.messages.create.return_value = _fake_response("code written")

        agent = DeveloperAgent(_make_agent())
        result = agent.execute(_make_task(), {"repo_root": "/tmp/repo"})

        assert isinstance(result, TaskOutput)
        assert "code written" in result.content

    @mock.patch("anthropic.Anthropic")
    def test_repo_root_in_prompt(self, MockAnthropic):
        client = MockAnthropic.return_value
        client.messages.create.return_value = _fake_response("ok")

        agent = DeveloperAgent(_make_agent())
        agent.execute(_make_task(), {"repo_root": "/my/project"})

        messages = client.messages.create.call_args.kwargs["messages"]
        assert "/my/project" in messages[0]["content"]

    @mock.patch("anthropic.Anthropic")
    def test_repo_root_defaults_to_dot(self, MockAnthropic):
        client = MockAnthropic.return_value
        client.messages.create.return_value = _fake_response("ok")

        agent = DeveloperAgent(_make_agent())
        agent.execute(_make_task(), {})

        messages = client.messages.create.call_args.kwargs["messages"]
        assert "Repository root: ." in messages[0]["content"]

    @mock.patch("anthropic.Anthropic")
    def test_artifacts_extracted_from_response(self, MockAnthropic):
        client = MockAnthropic.return_value
        response_text = (
            "I created the file.\n"
            '```json\n{"files_changed": ["src/utils.py", "src/helpers.py"]}\n```'
        )
        client.messages.create.return_value = _fake_response(response_text)

        agent = DeveloperAgent(_make_agent())
        result = agent.execute(_make_task(), {"repo_root": "/tmp/repo"})

        assert "src/utils.py" in result.artifacts
        assert "src/helpers.py" in result.artifacts

    @mock.patch("anthropic.Anthropic")
    def test_artifacts_empty_when_no_json_block(self, MockAnthropic):
        client = MockAnthropic.return_value
        client.messages.create.return_value = _fake_response("No files changed.")

        agent = DeveloperAgent(_make_agent())
        result = agent.execute(_make_task(), {"repo_root": "/tmp/repo"})

        assert result.artifacts == {}

    @mock.patch("anthropic.Anthropic")
    def test_history_grows_after_execute(self, MockAnthropic):
        client = MockAnthropic.return_value
        client.messages.create.return_value = _fake_response("done")

        agent = DeveloperAgent(_make_agent())
        agent.execute(_make_task(), {"repo_root": "/tmp/repo"})

        assert len(agent._history) == 2
        assert agent._history[0]["role"] == "user"
        assert agent._history[1]["role"] == "assistant"

    @mock.patch("anthropic.Anthropic")
    def test_tools_passed_to_sdk(self, MockAnthropic):
        client = MockAnthropic.return_value
        client.messages.create.return_value = _fake_response("ok")

        agent = DeveloperAgent(_make_agent())
        agent.execute(_make_task(), {"repo_root": "/tmp/repo"})

        call_kwargs = client.messages.create.call_args.kwargs
        assert "tools" in call_kwargs
        types = {t["type"] for t in call_kwargs["tools"]}
        assert "text_editor_20250429" in types


# ---------------------------------------------------------------------------
# Artifact extraction
# ---------------------------------------------------------------------------

class TestExtractArtifacts:
    def test_parses_valid_json_block(self):
        content = 'Some text\n```json\n{"files_changed": ["a.py"]}\n```\nmore text'
        result = DeveloperAgent._extract_artifacts(content)
        assert result == {"a.py": "created/modified"}

    def test_returns_empty_on_no_block(self):
        result = DeveloperAgent._extract_artifacts("No json here.")
        assert result == {}

    def test_returns_empty_on_malformed_json(self):
        content = '```json\n{bad json}\n```'
        result = DeveloperAgent._extract_artifacts(content)
        assert result == {}

    def test_multiple_files(self):
        content = '```json\n{"files_changed": ["a.py", "b.py", "c/d.py"]}\n```'
        result = DeveloperAgent._extract_artifacts(content)
        assert len(result) == 3
        assert "c/d.py" in result

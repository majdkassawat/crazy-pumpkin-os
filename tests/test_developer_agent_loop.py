"""Tests for the DeveloperAgent agentic tool-use loop and artifact extraction."""

import sys
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from crazypumpkin.agents.developer_agent import DeveloperAgent
from crazypumpkin.framework.models import Agent, AgentRole, Task, TaskOutput


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


def _text_block(text: str):
    return SimpleNamespace(type="text", text=text)


def _tool_use_block(tool_id: str, command: str, file_path: str, content: str = ""):
    return SimpleNamespace(
        type="tool_use",
        id=tool_id,
        name="str_replace_editor",
        input={"command": command, "file_path": file_path, "content": content},
    )


def _response(content_blocks, stop_reason="end_turn"):
    return SimpleNamespace(content=content_blocks, stop_reason=stop_reason)


# ---------------------------------------------------------------------------
# Test cases
# ---------------------------------------------------------------------------

class TestDeveloperAgentLoop:
    @mock.patch("anthropic.Anthropic")
    def test_execute_with_tool_use_produces_artifacts(self, MockAnthropic, tmp_path):
        """Tool-use loop: Write block on first call -> artifacts populated."""
        client = MockAnthropic.return_value
        repo_root = str(tmp_path)
        file_path = str(tmp_path / "src" / "main.py")

        first_response = _response(
            [_tool_use_block("toolu_1", "write", file_path, "print('hello')")],
            stop_reason="tool_use",
        )
        second_response = _response(
            [_text_block("Done writing the file.")],
            stop_reason="end_turn",
        )
        client.messages.create.side_effect = [first_response, second_response]

        agent = DeveloperAgent(_make_agent())
        result = agent.execute(_make_task(), {"repo_root": repo_root})

        assert isinstance(result, TaskOutput)
        assert file_path in result.artifacts
        assert result.artifacts[file_path] == "created/modified"
        # Verify the API was called twice (loop iterated)
        assert client.messages.create.call_count == 2

    @mock.patch("anthropic.Anthropic")
    def test_execute_no_tool_use_falls_back_to_regex(self, MockAnthropic):
        """end_turn with files_changed JSON block -> artifacts via regex."""
        client = MockAnthropic.return_value
        response_text = (
            "I created the file.\n"
            '```json\n{"files_changed": ["src/utils.py", "src/helpers.py"]}\n```'
        )
        client.messages.create.return_value = _response(
            [_text_block(response_text)],
            stop_reason="end_turn",
        )

        agent = DeveloperAgent(_make_agent())
        result = agent.execute(_make_task(), {"repo_root": "/tmp/repo"})

        assert "src/utils.py" in result.artifacts
        assert "src/helpers.py" in result.artifacts
        # Only one API call (no loop)
        assert client.messages.create.call_count == 1

    @mock.patch("anthropic.Anthropic")
    def test_execute_no_artifacts_returns_empty(self, MockAnthropic):
        """end_turn with plain text, no JSON block -> empty artifacts."""
        client = MockAnthropic.return_value
        client.messages.create.return_value = _response(
            [_text_block("All done, nothing to report.")],
            stop_reason="end_turn",
        )

        agent = DeveloperAgent(_make_agent())
        result = agent.execute(_make_task(), {"repo_root": "/tmp/repo"})

        assert result.artifacts == {}
        assert "All done" in result.content

    @mock.patch("anthropic.Anthropic")
    def test_execute_path_traversal_blocked(self, MockAnthropic, tmp_path):
        """Tool-use with file_path outside repo_root -> error, not in artifacts."""
        client = MockAnthropic.return_value
        repo_root = str(tmp_path)
        malicious_path = str(tmp_path.parent / "evil.py")

        first_response = _response(
            [_tool_use_block("toolu_1", "write", malicious_path, "evil code")],
            stop_reason="tool_use",
        )
        second_response = _response(
            [_text_block("Done.")],
            stop_reason="end_turn",
        )
        client.messages.create.side_effect = [first_response, second_response]

        agent = DeveloperAgent(_make_agent())
        result = agent.execute(_make_task(), {"repo_root": repo_root})

        # Malicious path must NOT appear in artifacts
        assert malicious_path not in result.artifacts

        # Verify the tool result sent back contained an error
        tool_result_messages = [
            m for m in agent._history
            if m["role"] == "user" and isinstance(m["content"], list)
        ]
        assert len(tool_result_messages) >= 1
        tool_result = tool_result_messages[0]["content"][0]
        assert tool_result["is_error"] is True
        assert "outside the repository root" in tool_result["content"]

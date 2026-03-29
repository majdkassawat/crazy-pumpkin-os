"""Tests for ReviewerAgent."""

import json
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from crazypumpkin.agents.reviewer_agent import ReviewerAgent
from crazypumpkin.framework.agent import ClaudeSDKAgent
from crazypumpkin.framework.models import Agent, AgentConfig, AgentRole, Task, TaskOutput


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_agent(**kwargs) -> Agent:
    defaults = {"name": "test-reviewer", "role": AgentRole.REVIEWER}
    defaults.update(kwargs)
    return Agent(**defaults)


def _make_task(files=None, title="Review utils", description="Check quality.") -> Task:
    return Task(
        title=title,
        description=description,
        acceptance_criteria=["No critical bugs"],
        metadata={"files": files or []},
    )


REVIEW_JSON = json.dumps({
    "issues": [
        {"file": "foo.py", "line": 10, "severity": "warning", "message": "Unused import"}
    ],
    "verdict": "approve",
})


def _fake_response(text: str = REVIEW_JSON):
    block = SimpleNamespace(text=text)
    return SimpleNamespace(content=[block])


# ---------------------------------------------------------------------------
# Construction
# ---------------------------------------------------------------------------

class TestReviewerAgentInit:
    def test_subclasses_claude_sdk_agent(self):
        agent = ReviewerAgent(_make_agent())
        assert isinstance(agent, ClaudeSDKAgent)

    def test_read_only_permissions(self):
        agent = ReviewerAgent(_make_agent())
        assert agent.tool_permissions == {"read": True, "write": False, "bash": False}

    def test_cannot_override_permissions(self):
        """Constructor does not accept tool_permissions — always read-only."""
        agent = ReviewerAgent(_make_agent())
        assert agent.tool_permissions["write"] is False
        assert agent.tool_permissions["bash"] is False


# ---------------------------------------------------------------------------
# Execute
# ---------------------------------------------------------------------------

class TestReviewerAgentExecute:
    @mock.patch("anthropic.Anthropic")
    def test_returns_task_output(self, MockAnthropic):
        client = MockAnthropic.return_value
        client.messages.create.return_value = _fake_response()

        agent = ReviewerAgent(_make_agent())
        result = agent.execute(_make_task(), {})

        assert isinstance(result, TaskOutput)

    @mock.patch("anthropic.Anthropic")
    def test_content_is_structured_json(self, MockAnthropic):
        client = MockAnthropic.return_value
        client.messages.create.return_value = _fake_response()

        agent = ReviewerAgent(_make_agent())
        result = agent.execute(_make_task(), {})

        parsed = json.loads(result.content)
        assert "issues" in parsed
        assert "verdict" in parsed

    @mock.patch("anthropic.Anthropic")
    def test_issues_list_present(self, MockAnthropic):
        client = MockAnthropic.return_value
        client.messages.create.return_value = _fake_response()

        agent = ReviewerAgent(_make_agent())
        result = agent.execute(_make_task(), {})

        parsed = json.loads(result.content)
        assert isinstance(parsed["issues"], list)
        assert len(parsed["issues"]) == 1
        assert parsed["issues"][0]["file"] == "foo.py"

    @mock.patch("anthropic.Anthropic")
    def test_verdict_present(self, MockAnthropic):
        client = MockAnthropic.return_value
        client.messages.create.return_value = _fake_response()

        agent = ReviewerAgent(_make_agent())
        result = agent.execute(_make_task(), {})

        parsed = json.loads(result.content)
        assert parsed["verdict"] == "approve"

    @mock.patch("anthropic.Anthropic")
    def test_review_metadata_populated(self, MockAnthropic):
        client = MockAnthropic.return_value
        client.messages.create.return_value = _fake_response()

        agent = ReviewerAgent(_make_agent())
        result = agent.execute(_make_task(), {})

        assert "review" in result.metadata
        assert result.metadata["review"]["verdict"] == "approve"

    @mock.patch("anthropic.Anthropic")
    def test_reads_files_from_task_metadata(self, MockAnthropic, tmp_path):
        test_file = tmp_path / "example.py"
        test_file.write_text("x = 1\n", encoding="utf-8")

        client = MockAnthropic.return_value
        client.messages.create.return_value = _fake_response()

        agent = ReviewerAgent(_make_agent())
        task = _make_task(files=[str(test_file)])
        agent.execute(task, {})

        prompt = client.messages.create.call_args.kwargs["messages"][0]["content"]
        assert "x = 1" in prompt

    @mock.patch("anthropic.Anthropic")
    def test_missing_file_noted_in_prompt(self, MockAnthropic):
        client = MockAnthropic.return_value
        client.messages.create.return_value = _fake_response()

        agent = ReviewerAgent(_make_agent())
        task = _make_task(files=["/nonexistent/path.py"])
        agent.execute(task, {})

        prompt = client.messages.create.call_args.kwargs["messages"][0]["content"]
        assert "<file not found:" in prompt

    @mock.patch("anthropic.Anthropic")
    def test_no_files_writes_performed(self, MockAnthropic, tmp_path):
        """ReviewerAgent must never write files."""
        client = MockAnthropic.return_value
        client.messages.create.return_value = _fake_response()

        agent = ReviewerAgent(_make_agent())
        task = _make_task(files=[])
        agent.execute(task, {})

        # Verify write permission is disabled
        assert agent.tool_permissions["write"] is False
        # Verify no artifacts in output
        result = agent.execute(task, {})
        assert result.artifacts == {}

    @mock.patch("anthropic.Anthropic")
    def test_non_json_response_falls_back(self, MockAnthropic):
        client = MockAnthropic.return_value
        client.messages.create.return_value = _fake_response("Not valid JSON at all")

        agent = ReviewerAgent(_make_agent())
        result = agent.execute(_make_task(), {})

        parsed = json.loads(result.content)
        assert parsed["verdict"] == "revise"
        assert parsed["issues"] == []
        assert "raw_response" in parsed

    @mock.patch("anthropic.Anthropic")
    def test_history_grows_after_execute(self, MockAnthropic):
        client = MockAnthropic.return_value
        client.messages.create.return_value = _fake_response()

        agent = ReviewerAgent(_make_agent())
        agent.execute(_make_task(), {})

        assert len(agent._history) == 2
        assert agent._history[0]["role"] == "user"
        assert agent._history[1]["role"] == "assistant"

    @mock.patch("anthropic.Anthropic")
    def test_tools_only_include_text_editor(self, MockAnthropic):
        client = MockAnthropic.return_value
        client.messages.create.return_value = _fake_response()

        agent = ReviewerAgent(_make_agent())
        agent.execute(_make_task(), {})

        call_kwargs = client.messages.create.call_args.kwargs
        assert "tools" in call_kwargs
        types = {t["type"] for t in call_kwargs["tools"]}
        assert types == {"text_editor_20250429"}
        assert "bash_20250429" not in types

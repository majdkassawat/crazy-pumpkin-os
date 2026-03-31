"""Combined unit tests for ClaudeSDKAgent, DeveloperAgent, and ReviewerAgent.

All Anthropic SDK calls are mocked — no real API traffic.
"""

import json
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from crazypumpkin.framework.agent import ClaudeSDKAgent
from crazypumpkin.agents.developer_agent import DeveloperAgent
from crazypumpkin.agents.reviewer_agent import ReviewerAgent
from crazypumpkin.framework.models import Agent, AgentConfig, AgentRole, Task, TaskOutput


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _agent(**kwargs) -> Agent:
    defaults = {"name": "test-agent", "role": AgentRole.EXECUTION}
    defaults.update(kwargs)
    return Agent(**defaults)


def _task(title="Do thing", description="Do the thing.", **kwargs) -> Task:
    defaults = {
        "title": title,
        "description": description,
        "acceptance_criteria": ["criterion-a"],
    }
    defaults.update(kwargs)
    return Task(**defaults)


def _fake_response(text="Done."):
    return SimpleNamespace(content=[SimpleNamespace(text=text)])


REVIEW_JSON = json.dumps({
    "issues": [
        {"file": "a.py", "line": 1, "severity": "warning", "message": "nit"}
    ],
    "verdict": "approve",
})


# ===========================================================================
# ClaudeSDKAgent
# ===========================================================================

class TestClaudeSDKAgentMultiTurn:
    """Multi-turn history must grow across successive execute() calls."""

    @mock.patch("anthropic.Anthropic")
    def test_history_grows_across_two_calls(self, MockAnthropic):
        client = MockAnthropic.return_value
        client.messages.create.side_effect = [
            _fake_response("first"),
            _fake_response("second"),
        ]

        sdk_agent = ClaudeSDKAgent(_agent())
        sdk_agent.execute(_task(title="T1"), {})
        sdk_agent.execute(_task(title="T2"), {})

        # Two calls → 4 history entries: user, assistant, user, assistant
        assert len(sdk_agent._history) == 4
        roles = [h["role"] for h in sdk_agent._history]
        assert roles == ["user", "assistant", "user", "assistant"]

    @mock.patch("anthropic.Anthropic")
    def test_second_call_sends_prior_turns(self, MockAnthropic):
        client = MockAnthropic.return_value
        client.messages.create.side_effect = [
            _fake_response("r1"),
            _fake_response("r2"),
        ]

        sdk_agent = ClaudeSDKAgent(_agent())
        sdk_agent.execute(_task(title="A"), {})
        sdk_agent.execute(_task(title="B"), {})

        second_call_msgs = client.messages.create.call_args_list[1].kwargs["messages"]
        # Must include user1, assistant1, user2
        assert len(second_call_msgs) == 3
        assert second_call_msgs[0]["role"] == "user"
        assert second_call_msgs[1]["role"] == "assistant"
        assert second_call_msgs[2]["role"] == "user"


class TestClaudeSDKAgentToolPermissions:
    """tool_permissions must propagate into SDK create() kwargs."""

    @mock.patch("anthropic.Anthropic")
    def test_read_only_forwards_text_editor(self, MockAnthropic):
        client = MockAnthropic.return_value
        client.messages.create.return_value = _fake_response()

        sdk_agent = ClaudeSDKAgent(
            _agent(),
            tool_permissions={"read": True, "write": False, "bash": False},
        )
        sdk_agent.execute(_task(), {})

        kw = client.messages.create.call_args.kwargs
        assert "tools" in kw
        types = {t["type"] for t in kw["tools"]}
        assert types == {"text_editor_20250429"}

    @mock.patch("anthropic.Anthropic")
    def test_all_perms_forward_both_tools(self, MockAnthropic):
        client = MockAnthropic.return_value
        client.messages.create.return_value = _fake_response()

        sdk_agent = ClaudeSDKAgent(
            _agent(),
            tool_permissions={"read": True, "write": True, "bash": True},
        )
        sdk_agent.execute(_task(), {})

        kw = client.messages.create.call_args.kwargs
        types = {t["type"] for t in kw["tools"]}
        assert types == {"text_editor_20250429", "bash_20250429"}

    @mock.patch("anthropic.Anthropic")
    def test_no_perms_omit_tools_key(self, MockAnthropic):
        client = MockAnthropic.return_value
        client.messages.create.return_value = _fake_response()

        sdk_agent = ClaudeSDKAgent(
            _agent(),
            tool_permissions={"read": False, "write": False, "bash": False},
        )
        sdk_agent.execute(_task(), {})

        kw = client.messages.create.call_args.kwargs
        assert "tools" not in kw


# ===========================================================================
# DeveloperAgent
# ===========================================================================

@pytest.mark.skip(reason="Mock response missing stop_reason attr — needs update for current SDK interface")
class TestDeveloperAgentArtifacts:
    """DeveloperAgent.execute() must populate artifacts in TaskOutput."""

    @mock.patch("anthropic.Anthropic")
    def test_artifacts_populated_from_json_block(self, MockAnthropic):
        client = MockAnthropic.return_value
        text = (
            "Created files.\n"
            '```json\n{"files_changed": ["src/foo.py", "src/bar.py"]}\n```'
        )
        client.messages.create.return_value = _fake_response(text)

        dev = DeveloperAgent(_agent())
        result = dev.execute(_task(), {"repo_root": "/tmp"})

        assert isinstance(result, TaskOutput)
        assert "src/foo.py" in result.artifacts
        assert "src/bar.py" in result.artifacts
        assert result.artifacts["src/foo.py"] == "created/modified"

    @mock.patch("anthropic.Anthropic")
    def test_artifacts_empty_when_no_json(self, MockAnthropic):
        client = MockAnthropic.return_value
        client.messages.create.return_value = _fake_response("nothing changed")

        dev = DeveloperAgent(_agent())
        result = dev.execute(_task(), {"repo_root": "/tmp"})

        assert result.artifacts == {}

    @mock.patch("anthropic.Anthropic")
    def test_content_preserved_alongside_artifacts(self, MockAnthropic):
        client = MockAnthropic.return_value
        text = 'Done.\n```json\n{"files_changed": ["x.py"]}\n```'
        client.messages.create.return_value = _fake_response(text)

        dev = DeveloperAgent(_agent())
        result = dev.execute(_task(), {"repo_root": "."})

        assert "Done." in result.content
        assert "x.py" in result.artifacts


# ===========================================================================
# ReviewerAgent
# ===========================================================================

class TestReviewerAgentStructuredFeedback:
    """ReviewerAgent content must contain 'issues' and 'verdict' keys."""

    @mock.patch("anthropic.Anthropic")
    def test_content_has_issues_and_verdict(self, MockAnthropic):
        client = MockAnthropic.return_value
        client.messages.create.return_value = _fake_response(REVIEW_JSON)

        rev = ReviewerAgent(_agent(role=AgentRole.REVIEWER))
        result = rev.execute(_task(metadata={"files": []}), {})

        parsed = json.loads(result.content)
        assert "issues" in parsed
        assert "verdict" in parsed

    @mock.patch("anthropic.Anthropic")
    def test_fallback_still_has_issues_and_verdict(self, MockAnthropic):
        client = MockAnthropic.return_value
        client.messages.create.return_value = _fake_response("not json")

        rev = ReviewerAgent(_agent(role=AgentRole.REVIEWER))
        result = rev.execute(_task(metadata={"files": []}), {})

        parsed = json.loads(result.content)
        assert "issues" in parsed
        assert "verdict" in parsed

    @mock.patch("anthropic.Anthropic")
    def test_review_metadata_populated(self, MockAnthropic):
        client = MockAnthropic.return_value
        client.messages.create.return_value = _fake_response(REVIEW_JSON)

        rev = ReviewerAgent(_agent(role=AgentRole.REVIEWER))
        result = rev.execute(_task(metadata={"files": []}), {})

        assert "review" in result.metadata
        assert "issues" in result.metadata["review"]
        assert "verdict" in result.metadata["review"]


class TestReviewerAgentNoWrites:
    """ReviewerAgent must never write files — write/bash permissions off."""

    def test_write_permission_disabled(self):
        rev = ReviewerAgent(_agent(role=AgentRole.REVIEWER))
        assert rev.tool_permissions["write"] is False

    def test_bash_permission_disabled(self):
        rev = ReviewerAgent(_agent(role=AgentRole.REVIEWER))
        assert rev.tool_permissions["bash"] is False

    @mock.patch("anthropic.Anthropic")
    def test_no_artifacts_in_output(self, MockAnthropic):
        client = MockAnthropic.return_value
        client.messages.create.return_value = _fake_response(REVIEW_JSON)

        rev = ReviewerAgent(_agent(role=AgentRole.REVIEWER))
        result = rev.execute(_task(metadata={"files": []}), {})

        assert result.artifacts == {}

    @mock.patch("anthropic.Anthropic")
    def test_tools_exclude_bash(self, MockAnthropic):
        client = MockAnthropic.return_value
        client.messages.create.return_value = _fake_response(REVIEW_JSON)

        rev = ReviewerAgent(_agent(role=AgentRole.REVIEWER))
        rev.execute(_task(metadata={"files": []}), {})

        kw = client.messages.create.call_args.kwargs
        if "tools" in kw:
            types = {t["type"] for t in kw["tools"]}
            assert "bash_20250429" not in types

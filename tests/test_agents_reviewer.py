"""Tests for ReviewerAgent."""

import sys
from pathlib import Path
from unittest import mock

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from crazypumpkin.agents.reviewer import ReviewerAgent
from crazypumpkin.framework.models import Agent, AgentRole, Task, TaskOutput


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_agent() -> Agent:
    return Agent(name="test-reviewer", role=AgentRole.REVIEWER)


def _make_task_with_artifacts(
    acceptance_criteria: list[str] | None = None,
) -> Task:
    """Return a Task whose output has artifacts matching common criteria keywords."""
    task = Task(
        title="Review widget",
        description="Review the widget implementation.",
        acceptance_criteria=acceptance_criteria or ["widget module exists"],
    )
    task.output = TaskOutput(
        content="done",
        artifacts={"widget.py": "class Widget:\n    pass\n"},
    )
    return task


def _make_task_empty_artifacts() -> Task:
    """Return a Task with no output artifacts."""
    return Task(
        title="Review empty",
        description="Nothing to review.",
        acceptance_criteria=["something"],
    )


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestReviewerAgent:
    """Tests for ReviewerAgent.execute()."""

    @mock.patch("crazypumpkin.agents.reviewer.subprocess_util")
    def test_approve_flow(self, mock_subprocess_util, tmp_path):
        """Artifacts present, criteria met, tests pass → APPROVED."""
        mock_subprocess_util.run.return_value = mock.MagicMock(
            returncode=0, stdout="all passed", stderr=""
        )

        agent = ReviewerAgent(_make_agent())
        task = _make_task_with_artifacts(["widget module exists"])
        result = agent.execute(task, {"workspace": str(tmp_path)})

        assert result.content.startswith("APPROVED")
        assert result.metadata["decision"] == "approved"
        mock_subprocess_util.run.assert_called_once()

    @mock.patch("crazypumpkin.agents.reviewer.subprocess_util")
    def test_reject_flow_tests_fail(self, mock_subprocess_util, tmp_path):
        """Artifacts present but test command fails → REJECTED."""
        mock_subprocess_util.run.return_value = mock.MagicMock(
            returncode=1, stdout="1 failed", stderr=""
        )

        agent = ReviewerAgent(_make_agent())
        task = _make_task_with_artifacts(["widget module exists"])
        result = agent.execute(task, {"workspace": str(tmp_path)})

        assert result.content.startswith("REJECTED")
        assert result.metadata["decision"] == "rejected"
        mock_subprocess_util.run.assert_called_once()

    @mock.patch("crazypumpkin.agents.reviewer.subprocess_util")
    def test_governance_reject_empty_artifacts(self, mock_subprocess_util):
        """Empty artifacts → REJECTED without running test command."""
        agent = ReviewerAgent(_make_agent())
        task = _make_task_empty_artifacts()
        result = agent.execute(task, {"workspace": "/some/path"})

        assert result.content.startswith("REJECTED")
        assert result.metadata["decision"] == "rejected"
        mock_subprocess_util.run.assert_not_called()

    @mock.patch("crazypumpkin.agents.reviewer.subprocess_util")
    def test_no_workspace_skips_subprocess(self, mock_subprocess_util):
        """No workspace in context → subprocess not called."""
        agent = ReviewerAgent(_make_agent())
        task = _make_task_with_artifacts(["widget module exists"])
        result = agent.execute(task, {})

        assert result.content.startswith("APPROVED")
        mock_subprocess_util.run.assert_not_called()

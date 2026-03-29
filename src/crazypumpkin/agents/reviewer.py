"""Reviewer agent — governance-based reviewer that runs tests and checks artifacts."""

from __future__ import annotations

from typing import Any

from crazypumpkin.framework import subprocess_util
from crazypumpkin.framework.models import Agent, Task, TaskOutput


class ReviewerAgent:
    """Agent that reviews task output by checking artifacts and running tests."""

    def __init__(self, agent: Agent) -> None:
        self.agent = agent

    def execute(self, task: Task, context: dict[str, Any]) -> TaskOutput:
        """Review task output artifacts and optionally run tests.

        Returns APPROVED if artifacts are present, criteria appear met, and
        tests pass (when workspace is provided). Returns REJECTED otherwise.
        """
        output = getattr(task, "output", None)
        artifacts: dict[str, str] = {}
        if output is not None:
            artifacts = getattr(output, "artifacts", {}) or {}

        # Governance: reject immediately if no artifacts
        if not artifacts:
            return TaskOutput(
                content="REJECTED: no artifacts produced.",
                metadata={"decision": "rejected", "reason": "no_artifacts"},
            )

        # Check acceptance criteria against artifact keys/content
        criteria = task.acceptance_criteria or []
        unmet: list[str] = []
        artifact_text = " ".join(artifacts.keys()) + " " + " ".join(artifacts.values())
        for criterion in criteria:
            # Simple keyword check: criterion words present in artifacts
            keywords = criterion.lower().split()
            if not any(kw in artifact_text.lower() for kw in keywords):
                unmet.append(criterion)

        workspace = context.get("workspace")
        if workspace:
            test_cmd = ["python", "-m", "pytest", "tests/", "--tb=short"]
            result = subprocess_util.run(test_cmd, cwd=workspace)
            if result.returncode != 0:
                return TaskOutput(
                    content=f"REJECTED: tests failed.\n{result.stdout}",
                    metadata={
                        "decision": "rejected",
                        "reason": "tests_failed",
                        "returncode": result.returncode,
                    },
                )

        if unmet:
            return TaskOutput(
                content=f"REJECTED: unmet criteria: {unmet}",
                metadata={"decision": "rejected", "reason": "criteria_unmet", "unmet": unmet},
            )

        return TaskOutput(
            content="APPROVED: all checks passed.",
            metadata={"decision": "approved"},
        )

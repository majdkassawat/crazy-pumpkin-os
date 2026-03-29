"""Developer agent — reads and writes code using the Claude SDK."""

from __future__ import annotations

import json
import re
from typing import Any

from crazypumpkin.framework.agent import ClaudeSDKAgent
from crazypumpkin.framework.models import Agent, Task, TaskOutput


class DeveloperAgent(ClaudeSDKAgent):
    """Agent that reads and writes code via the Claude SDK.

    Subclasses ClaudeSDKAgent with read and write tool permissions enabled
    by default so the model can inspect and modify source files within the
    repository.
    """

    SYSTEM_PROMPT = (
        "You are a senior software developer. Your role is to read, write, "
        "and modify code within the repository. Follow best practices for "
        "code quality, maintainability, and correctness. Provide clear "
        "explanations of any changes you make."
    )

    def __init__(self, agent: Agent) -> None:
        super().__init__(
            agent,
            tool_permissions={"read": True, "write": True, "bash": False},
            system_prompt=self.SYSTEM_PROMPT,
        )

    def execute(self, task: Task, context: dict[str, Any]) -> TaskOutput:
        """Execute a coding task within the given repository.

        The *context* dict must contain a ``repo_root`` key pointing to the
        root directory of the target repository.  This path is injected into
        the system prompt so the SDK session knows where files live.

        Returns a TaskOutput whose ``artifacts`` dict maps file paths to a
        short description for every file created or modified.
        """
        import anthropic

        repo_root: str = context.get("repo_root", ".")

        client = anthropic.Anthropic()
        model = self.agent.config.model or self.DEFAULT_MODEL

        criteria = "\n".join(f"- {c}" for c in task.acceptance_criteria)
        user_message = (
            f"Repository root: {repo_root}\n\n"
            f"Task: {task.title}\n\n"
            f"Description:\n{task.description}\n\n"
            f"Acceptance criteria:\n{criteria}\n\n"
            "After making changes, list every file you created or modified "
            "in a JSON block like:\n"
            '```json\n{"files_changed": ["path/to/file1.py", "path/to/file2.py"]}\n```'
        )
        self._history.append({"role": "user", "content": user_message})

        tools = self._build_tools()
        create_kwargs: dict[str, Any] = {
            "model": model,
            "max_tokens": 16384,
            "messages": list(self._history),
        }
        if self.system_prompt is not None:
            create_kwargs["system"] = [
                {"type": "text", "text": self.system_prompt, "cache_control": {"type": "ephemeral"}},
            ]
        if tools:
            create_kwargs["tools"] = tools

        response = client.messages.create(**create_kwargs)

        # Extract text content from the response
        content_parts: list[str] = []
        for block in response.content:
            if hasattr(block, "text"):
                content_parts.append(block.text)
        content = "\n".join(content_parts)

        # Preserve assistant turn for multi-turn continuity
        self._history.append({
            "role": "assistant",
            "content": response.content,
        })

        # Extract file paths from the response
        artifacts = self._extract_artifacts(content)

        return TaskOutput(content=content, artifacts=artifacts)

    @staticmethod
    def _extract_artifacts(content: str) -> dict[str, str]:
        """Parse file paths from a ``files_changed`` JSON block in *content*.

        Returns a dict mapping each file path to ``"created/modified"``.
        """
        match = re.search(
            r"```json\s*(\{.*?\"files_changed\".*?\})\s*```",
            content,
            re.DOTALL,
        )
        if match:
            try:
                data = json.loads(match.group(1))
                paths = data.get("files_changed", [])
                return {p: "created/modified" for p in paths}
            except (json.JSONDecodeError, TypeError):
                pass
        return {}

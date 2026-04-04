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

        Runs an agentic tool-use loop: the model may request file writes via
        tool_use blocks, which are executed (with path-traversal checks) and
        fed back until the model signals ``end_turn``.

        The *context* dict must contain a ``repo_root`` key pointing to the
        root directory of the target repository.

        Returns a TaskOutput whose ``artifacts`` dict maps file paths to a
        short description for every file created or modified.
        """
        import os

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

        artifacts: dict[str, str] = {}
        all_content_parts: list[str] = []
        max_iterations = 10

        for _ in range(max_iterations):
            response = client.messages.create(**create_kwargs)

            # Collect text content from this turn
            for block in response.content:
                if hasattr(block, "text"):
                    all_content_parts.append(block.text)

            # Preserve assistant turn for multi-turn continuity
            self._history.append({
                "role": "assistant",
                "content": response.content,
            })

            if response.stop_reason != "tool_use":
                break

            # Process tool-use blocks and build tool results
            tool_results: list[dict[str, Any]] = []
            for block in response.content:
                if getattr(block, "type", None) != "tool_use":
                    continue

                tool_input = block.input
                command = tool_input.get("command", "")
                file_path = tool_input.get("file_path", "")

                # Path-traversal guard
                if file_path:
                    if os.path.isabs(file_path):
                        resolved = os.path.normpath(os.path.abspath(file_path))
                    else:
                        resolved = os.path.normpath(
                            os.path.join(os.path.abspath(repo_root), file_path)
                        )
                    root = os.path.normpath(os.path.abspath(repo_root))
                    if not resolved.startswith(root + os.sep) and resolved != root:
                        tool_results.append({
                            "type": "tool_result",
                            "tool_use_id": block.id,
                            "content": f"Error: path '{file_path}' is outside the repository root.",
                            "is_error": True,
                        })
                        continue

                # Record write artifacts
                if command in ("write", "create", "str_replace", "insert") and file_path:
                    artifacts[file_path] = "created/modified"

                tool_results.append({
                    "type": "tool_result",
                    "tool_use_id": block.id,
                    "content": "OK",
                })

            self._history.append({"role": "user", "content": tool_results})
            create_kwargs["messages"] = list(self._history)

        content = "\n".join(all_content_parts)

        # Fall back to regex extraction when no tool calls produced artifacts
        if not artifacts:
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

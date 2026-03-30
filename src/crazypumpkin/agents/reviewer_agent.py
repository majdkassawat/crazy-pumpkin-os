"""Reviewer agent — checks code quality using the Claude SDK (read-only)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from crazypumpkin.framework.agent import ClaudeSDKAgent
from crazypumpkin.framework.models import Agent, Task, TaskOutput


class ReviewerAgent(ClaudeSDKAgent):
    """Agent that reviews code for quality issues.

    Subclasses ClaudeSDKAgent with only read permissions — write and bash
    are always disabled so the reviewer never modifies the codebase.
    """

    SYSTEM_PROMPT = (
        "You are a code reviewer. Review files for quality issues including "
        "bugs, security vulnerabilities, performance problems, and style "
        "violations. Provide actionable feedback."
    )

    def __init__(self, agent: Agent) -> None:
        super().__init__(
            agent,
            tool_permissions={"read": True, "write": False, "bash": False},
            system_prompt=self.SYSTEM_PROMPT,
        )

    def execute(self, task: Task, context: dict[str, Any]) -> TaskOutput:
        """Review files listed in *task.metadata['files']* for quality issues.

        Returns a TaskOutput whose content is a JSON-formatted review
        containing an ``issues`` list and an overall ``verdict``.
        """
        import anthropic

        file_paths: list[str] = task.metadata.get("files", [])

        # Read file contents from disk
        file_contents: dict[str, str] = {}
        for fp in file_paths:
            path = Path(fp)
            if path.is_file():
                file_contents[fp] = path.read_text(encoding="utf-8", errors="replace")
            else:
                file_contents[fp] = f"<file not found: {fp}>"

        # Build the review prompt
        files_section = ""
        for fp, content in file_contents.items():
            files_section += f"\n### {fp}\n```\n{content}\n```\n"

        criteria = "\n".join(f"- {c}" for c in task.acceptance_criteria)
        user_message = (
            "Review the following files for quality issues.\n\n"
            f"Task: {task.title}\n\n"
            f"Description:\n{task.description}\n\n"
        )
        if criteria:
            user_message += f"Acceptance criteria:\n{criteria}\n\n"
        user_message += (
            f"Files to review:\n{files_section}\n\n"
            "Respond with JSON only, in this exact format:\n"
            '{"issues": [{"file": "<path>", "line": <number or null>, '
            '"severity": "error|warning|info", "message": "<description>"}], '
            '"verdict": "approve|reject|revise"}'
        )

        self._history.append({"role": "user", "content": user_message})

        client = anthropic.Anthropic()
        model = self.agent.config.model or self.DEFAULT_MODEL

        tools = self._build_tools()
        create_kwargs: dict[str, Any] = {
            "model": model,
            "max_tokens": 4096,
            "messages": list(self._history),
        }
        if self.system_prompt is not None:
            create_kwargs["system"] = [
                {"type": "text", "text": self.system_prompt, "cache_control": {"type": "ephemeral"}},
            ]
        if tools:
            create_kwargs["tools"] = tools

        response = client.messages.create(**create_kwargs)

        # Extract text content
        content_parts: list[str] = []
        for block in response.content:
            if hasattr(block, "text"):
                content_parts.append(block.text)
        raw_content = "\n".join(content_parts)

        self._history.append({
            "role": "assistant",
            "content": response.content,
        })

        # Attempt to parse structured JSON; fall back to raw content
        try:
            review = json.loads(raw_content)
        except (json.JSONDecodeError, TypeError):
            review = {
                "issues": [],
                "verdict": "revise",
                "raw_response": raw_content,
            }

        return TaskOutput(
            content=json.dumps(review, indent=2),
            metadata={"review": review},
        )

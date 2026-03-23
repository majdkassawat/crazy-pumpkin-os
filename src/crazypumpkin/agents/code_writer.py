"""Code-writer agent – generates code via LLM and writes artifacts to disk."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from crazypumpkin.framework.agent import BaseAgent
from crazypumpkin.framework.io import safe_write_text
from crazypumpkin.framework.models import Agent, Task, TaskOutput
from crazypumpkin.llm.registry import ProviderRegistry


class CodeWriterAgent(BaseAgent):
    """Agent that generates code files from a task description using an LLM."""

    def __init__(self, agent: Agent, llm: ProviderRegistry) -> None:
        super().__init__(agent)
        self.llm = llm

    def execute(self, task: Task, context: dict[str, Any]) -> TaskOutput:
        prompt = (
            f"You are a code-writing agent.\n\n"
            f"Task: {task.title}\n\n"
            f"Description: {task.description}\n\n"
            f"Respond with JSON: {{\"content\": \"<summary>\", \"artifacts\": {{\"<filename>\": \"<file content>\"}}}}"
        )

        result = self.llm.call_json(prompt, agent="developer")

        content: str = result.get("content", "")
        artifacts: dict[str, str] = result.get("artifacts", {})

        workspace = Path(context["workspace"])
        for filename, file_content in artifacts.items():
            safe_write_text(workspace / filename, file_content)

        return TaskOutput(content=content, artifacts=artifacts)

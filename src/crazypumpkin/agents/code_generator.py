"""Code-generator agent — turns task specs into source-code artifacts."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from crazypumpkin.framework.agent import BaseAgent
from crazypumpkin.framework.io import safe_write_text
from crazypumpkin.framework.models import Agent, Task, TaskOutput
from crazypumpkin.llm.registry import ProviderRegistry


def _parse_fenced_blocks(text: str) -> dict[str, str]:
    """Extract ``filename -> content`` from fenced code blocks.

    Expected format::

        ```filename
        content
        ```
    """
    pattern = re.compile(r"```(\S+)\n(.*?)```", re.DOTALL)
    return {m.group(1): m.group(2) for m in pattern.finditer(text)}


class CodeGeneratorAgent(BaseAgent):
    """Agent that generates code artifacts from a task specification."""

    def __init__(self, agent: Agent, registry: ProviderRegistry) -> None:
        super().__init__(agent)
        self.registry = registry

    def execute(self, task: Task, context: dict[str, Any]) -> TaskOutput:
        criteria = "\n".join(f"- {c}" for c in task.acceptance_criteria)
        prompt = (
            f"Task: {task.title}\n\n"
            f"Description:\n{task.description}\n\n"
            f"Acceptance criteria:\n{criteria}\n\n"
            "Generate the required source files. "
            "Wrap each file in a fenced code block whose info-string is the filename."
        )

        raw_response: str = self.registry.call(prompt, agent="code_generator")

        artifacts = _parse_fenced_blocks(raw_response)

        workspace = Path(context["workspace"])
        for filename, content in artifacts.items():
            safe_write_text(workspace / filename, content)

        return TaskOutput(content=raw_response, artifacts=artifacts)

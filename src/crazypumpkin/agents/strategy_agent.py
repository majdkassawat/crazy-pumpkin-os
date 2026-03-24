"""Strategy agent — decomposes high-level product goals into developer tasks."""

from __future__ import annotations

from typing import Any

from crazypumpkin.framework.agent import BaseAgent
from crazypumpkin.framework.models import Agent, AgentRole, Task, TaskOutput
from crazypumpkin.framework.store import Store
from crazypumpkin.llm.registry import ProviderRegistry


class StrategyAgent(BaseAgent):
    """Agent that breaks a high-level product goal into ordered developer tasks."""

    def __init__(self, agent: Agent, registry: ProviderRegistry, store: Store) -> None:
        super().__init__(agent)
        if agent.role != AgentRole.STRATEGY:
            raise ValueError(f"StrategyAgent requires AgentRole.STRATEGY, got {agent.role}")
        self.registry = registry
        self.store = store

    def execute(self, task: Task, context: dict[str, Any]) -> TaskOutput:
        """Decompose the goal in *task.description* into developer tasks.

        Calls the LLM for an ordered list of tasks, persists each one via
        the store, and returns a summary of created task IDs.
        """
        prompt = (
            "You are a technical strategy agent. Given the following high-level "
            "product goal, produce an ordered JSON list of developer tasks.\n\n"
            f"Goal: {task.description}\n\n"
            "Return a JSON object with a single key \"tasks\" whose value is a list. "
            "Each element must have:\n"
            "- \"title\": short task title\n"
            "- \"description\": detailed description\n"
            "- \"priority\": integer 1-5 (1=highest)\n"
            "- \"acceptance_criteria\": list of strings\n"
            "- \"depends_on\": list of title strings this task depends on "
            "(must match titles of earlier tasks in the list, or empty list)\n\n"
            "Return ONLY valid JSON, no markdown fences."
        )

        result = self.registry.call_json(prompt, agent="strategy_agent")

        raw_tasks: list[dict[str, Any]] = result.get("tasks", []) if isinstance(result, dict) else result

        project_id = task.project_id

        # First pass: create Task objects and build title->id mapping
        title_to_id: dict[str, str] = {}
        created_tasks: list[Task] = []

        for item in raw_tasks:
            new_task = Task(
                project_id=project_id,
                title=item.get("title", ""),
                description=item.get("description", ""),
                priority=int(item.get("priority", 3)),
                acceptance_criteria=item.get("acceptance_criteria", []),
            )
            title_to_id[new_task.title] = new_task.id
            created_tasks.append(new_task)

        # Second pass: resolve depends_on titles to task IDs
        for idx, item in enumerate(raw_tasks):
            depends_on_titles = item.get("depends_on", [])
            resolved_deps: list[str] = []
            for dep_title in depends_on_titles:
                dep_id = title_to_id.get(dep_title)
                if dep_id is not None:
                    resolved_deps.append(dep_id)
            created_tasks[idx].dependencies = resolved_deps

        # Persist all tasks
        created_ids: list[str] = []
        for t in created_tasks:
            self.store.add_task(t)
            created_ids.append(t.id)

        summary = "Created tasks:\n" + "\n".join(f"- {tid}" for tid in created_ids)
        return TaskOutput(content=summary)

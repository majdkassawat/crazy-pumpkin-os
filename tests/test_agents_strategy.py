"""Tests for StrategyAgent."""

import sys
from pathlib import Path
from unittest import mock

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from crazypumpkin.agents.strategy_agent import StrategyAgent
from crazypumpkin.framework.models import Agent, AgentRole, Task, TaskOutput
from crazypumpkin.framework.store import Store


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_agent() -> Agent:
    return Agent(name="test-strategist", role=AgentRole.STRATEGY)


def _make_task(project_id: str = "proj-abc", description: str = "Build a calculator app") -> Task:
    return Task(project_id=project_id, title="Goal", description=description)


MOCK_LLM_RESPONSE = {
    "tasks": [
        {
            "title": "Set up project scaffold",
            "description": "Create the initial project structure with package layout.",
            "priority": 1,
            "acceptance_criteria": ["package.json exists", "src/ directory created"],
            "depends_on": [],
        },
        {
            "title": "Implement calculator logic",
            "description": "Write the core arithmetic operations module.",
            "priority": 2,
            "acceptance_criteria": ["add/subtract/multiply/divide work", "unit tests pass"],
            "depends_on": ["Set up project scaffold"],
        },
    ]
}


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestStrategyAgent:
    """Tests for StrategyAgent.execute()."""

    def test_requires_strategy_role(self):
        """StrategyAgent rejects non-STRATEGY roles."""
        wrong_agent = Agent(name="exec", role=AgentRole.EXECUTION)
        registry = mock.MagicMock()
        store = Store()
        with pytest.raises(ValueError, match="AgentRole.STRATEGY"):
            StrategyAgent(wrong_agent, registry, store)

    def test_both_tasks_in_store(self):
        """After execute(), both tasks appear in the store."""
        registry = mock.MagicMock()
        registry.call_json.return_value = MOCK_LLM_RESPONSE
        store = Store()

        sa = StrategyAgent(_make_agent(), registry, store)
        sa.execute(_make_task(), {})

        assert len(store.tasks) == 2

    def test_task_project_ids(self):
        """All created tasks carry the parent task's project_id."""
        registry = mock.MagicMock()
        registry.call_json.return_value = MOCK_LLM_RESPONSE
        store = Store()

        sa = StrategyAgent(_make_agent(), registry, store)
        sa.execute(_make_task(project_id="proj-xyz"), {})

        for task in store.tasks.values():
            assert task.project_id == "proj-xyz"

    def test_task_priorities(self):
        """Created tasks have the priorities specified in the LLM response."""
        registry = mock.MagicMock()
        registry.call_json.return_value = MOCK_LLM_RESPONSE
        store = Store()

        sa = StrategyAgent(_make_agent(), registry, store)
        sa.execute(_make_task(), {})

        tasks = sorted(store.tasks.values(), key=lambda t: t.priority)
        assert tasks[0].priority == 1
        assert tasks[1].priority == 2

    def test_acceptance_criteria(self):
        """Created tasks have acceptance_criteria from the LLM response."""
        registry = mock.MagicMock()
        registry.call_json.return_value = MOCK_LLM_RESPONSE
        store = Store()

        sa = StrategyAgent(_make_agent(), registry, store)
        sa.execute(_make_task(), {})

        tasks_by_title = {t.title: t for t in store.tasks.values()}
        assert tasks_by_title["Set up project scaffold"].acceptance_criteria == [
            "package.json exists", "src/ directory created"
        ]
        assert tasks_by_title["Implement calculator logic"].acceptance_criteria == [
            "add/subtract/multiply/divide work", "unit tests pass"
        ]

    def test_depends_on_resolution(self):
        """Second task's dependencies list contains the first task's id."""
        registry = mock.MagicMock()
        registry.call_json.return_value = MOCK_LLM_RESPONSE
        store = Store()

        sa = StrategyAgent(_make_agent(), registry, store)
        sa.execute(_make_task(), {})

        tasks_by_title = {t.title: t for t in store.tasks.values()}
        scaffold = tasks_by_title["Set up project scaffold"]
        calc = tasks_by_title["Implement calculator logic"]

        assert scaffold.dependencies == []
        assert calc.dependencies == [scaffold.id]

    def test_output_content_is_non_empty(self):
        """TaskOutput.content returned by execute() is non-empty."""
        registry = mock.MagicMock()
        registry.call_json.return_value = MOCK_LLM_RESPONSE
        store = Store()

        sa = StrategyAgent(_make_agent(), registry, store)
        result = sa.execute(_make_task(), {})

        assert isinstance(result, TaskOutput)
        assert len(result.content) > 0

    def test_no_real_llm_call(self):
        """ProviderRegistry.call_json is called exactly once (mocked)."""
        registry = mock.MagicMock()
        registry.call_json.return_value = MOCK_LLM_RESPONSE
        store = Store()

        sa = StrategyAgent(_make_agent(), registry, store)
        sa.execute(_make_task(), {})

        registry.call_json.assert_called_once()
        _, kwargs = registry.call_json.call_args
        assert kwargs.get("system") == StrategyAgent.SYSTEM_PROMPT

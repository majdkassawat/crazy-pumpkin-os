"""Tests for CodeGeneratorAgent."""

import sys
from pathlib import Path
from unittest import mock

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from crazypumpkin.agents.code_generator import CodeGeneratorAgent, _parse_fenced_blocks
from crazypumpkin.framework.models import Agent, AgentRole, Task, TaskOutput


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_agent() -> Agent:
    return Agent(name="test-codegen", role=AgentRole.EXECUTION)


def _make_task(title: str = "Build widget", description: str = "Create a widget module.") -> Task:
    return Task(
        title=title,
        description=description,
        acceptance_criteria=["Must compile", "Must pass tests"],
    )


LLM_RESPONSE_WITH_CODE = (
    "Here is the code:\n\n"
    "```widget.py\n"
    "class Widget:\n"
    "    pass\n"
    "```\n\n"
    "And a test:\n\n"
    "```test_widget.py\n"
    "def test_widget():\n"
    "    assert True\n"
    "```\n"
)

LLM_RESPONSE_NO_CODE = "I could not generate any code for this task."


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestCodeGeneratorAgentWithCodeBlocks:
    """execute() with a mocked provider returns TaskOutput with artifacts."""

    @mock.patch("crazypumpkin.agents.code_generator.safe_write_text")
    def test_execute_returns_task_output_with_artifacts(self, mock_write, tmp_path):
        registry = mock.MagicMock()
        registry.call.return_value = LLM_RESPONSE_WITH_CODE

        agent = CodeGeneratorAgent(_make_agent(), registry)
        task = _make_task()
        result = agent.execute(task, {"workspace": str(tmp_path)})

        assert isinstance(result, TaskOutput)
        assert "widget.py" in result.artifacts
        assert "test_widget.py" in result.artifacts
        assert "class Widget:" in result.artifacts["widget.py"]
        assert "def test_widget():" in result.artifacts["test_widget.py"]

    @mock.patch("crazypumpkin.agents.code_generator.safe_write_text")
    def test_artifacts_written_to_workspace(self, mock_write, tmp_path):
        registry = mock.MagicMock()
        registry.call.return_value = LLM_RESPONSE_WITH_CODE

        agent = CodeGeneratorAgent(_make_agent(), registry)
        result = agent.execute(_make_task(), {"workspace": str(tmp_path)})

        assert mock_write.call_count == 2
        written_paths = {str(call.args[0]) for call in mock_write.call_args_list}
        assert str(tmp_path / "widget.py") in written_paths
        assert str(tmp_path / "test_widget.py") in written_paths

    @mock.patch("crazypumpkin.agents.code_generator.safe_write_text")
    def test_prompt_contains_task_title(self, mock_write, tmp_path):
        registry = mock.MagicMock()
        registry.call.return_value = LLM_RESPONSE_WITH_CODE

        agent = CodeGeneratorAgent(_make_agent(), registry)
        task = _make_task(title="Implement FooBar")
        agent.execute(task, {"workspace": str(tmp_path)})

        prompt_arg = registry.call.call_args.args[0]
        assert "Implement FooBar" in prompt_arg


class TestCodeGeneratorAgentNoCodeBlocks:
    """A response with no fenced code blocks produces empty artifacts."""

    @mock.patch("crazypumpkin.agents.code_generator.safe_write_text")
    def test_no_code_blocks_returns_empty_artifacts(self, mock_write, tmp_path):
        registry = mock.MagicMock()
        registry.call.return_value = LLM_RESPONSE_NO_CODE

        agent = CodeGeneratorAgent(_make_agent(), registry)
        result = agent.execute(_make_task(), {"workspace": str(tmp_path)})

        assert isinstance(result, TaskOutput)
        assert result.artifacts == {}
        assert result.content != ""
        assert result.content == LLM_RESPONSE_NO_CODE
        mock_write.assert_not_called()

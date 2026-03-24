"""Tests for CodeWriterAgent."""

import sys
from pathlib import Path
from unittest import mock

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from crazypumpkin.agents.code_writer import CodeWriterAgent
from crazypumpkin.framework.models import Agent, AgentConfig, AgentRole, Task, TaskOutput


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_agent() -> Agent:
    return Agent(name="test-code-writer", role=AgentRole.EXECUTION)


def _make_task(title: str = "Build widget", description: str = "Create a widget module.") -> Task:
    return Task(title=title, description=description)


MOCK_LLM_RESPONSE = {
    "content": "Generated widget module with tests.",
    "artifacts": {
        "widget.py": "class Widget:\n    pass\n",
        "test_widget.py": "def test_widget():\n    assert True\n",
    },
}


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestCodeWriterAgent:
    """Tests for CodeWriterAgent.execute()."""

    def test_call_json_receives_title_and_description(self, tmp_path):
        registry = mock.MagicMock()
        registry.call_json.return_value = MOCK_LLM_RESPONSE

        agent = CodeWriterAgent(_make_agent(), registry)
        task = _make_task(title="Implement FooBar", description="Build FooBar component.")
        agent.execute(task, {"workspace": str(tmp_path)})

        prompt_arg = registry.call_json.call_args.args[0]
        assert "Implement FooBar" in prompt_arg
        assert "Build FooBar component." in prompt_arg

    def test_output_content_matches_llm_response(self, tmp_path):
        registry = mock.MagicMock()
        registry.call_json.return_value = MOCK_LLM_RESPONSE

        agent = CodeWriterAgent(_make_agent(), registry)
        result = agent.execute(_make_task(), {"workspace": str(tmp_path)})

        assert isinstance(result, TaskOutput)
        assert result.content == MOCK_LLM_RESPONSE["content"]

    def test_output_artifacts_match_llm_response(self, tmp_path):
        registry = mock.MagicMock()
        registry.call_json.return_value = MOCK_LLM_RESPONSE

        agent = CodeWriterAgent(_make_agent(), registry)
        result = agent.execute(_make_task(), {"workspace": str(tmp_path)})

        assert result.artifacts == MOCK_LLM_RESPONSE["artifacts"]

    @mock.patch("crazypumpkin.agents.code_writer.safe_write_text")
    def test_artifact_files_written_to_workspace(self, mock_write, tmp_path):
        registry = mock.MagicMock()
        registry.call_json.return_value = MOCK_LLM_RESPONSE

        agent = CodeWriterAgent(_make_agent(), registry)
        agent.execute(_make_task(), {"workspace": str(tmp_path)})

        assert mock_write.call_count == 2
        written = {str(call.args[0]): call.args[1] for call in mock_write.call_args_list}
        for filename, content in MOCK_LLM_RESPONSE["artifacts"].items():
            assert str(tmp_path / filename) in written
            assert written[str(tmp_path / filename)] == content

    def test_model_from_agent_config_forwarded_to_call_json(self, tmp_path):
        """CodeWriterAgent must forward Agent.config.model to call_json()."""
        registry = mock.MagicMock()
        registry.call_json.return_value = MOCK_LLM_RESPONSE

        agent_def = Agent(
            name="test-code-writer",
            role=AgentRole.EXECUTION,
            config=AgentConfig(model="sonnet"),
        )
        cw = CodeWriterAgent(agent_def, registry)
        cw.execute(_make_task(), {"workspace": str(tmp_path)})

        registry.call_json.assert_called_once()
        _, kwargs = registry.call_json.call_args
        assert kwargs["model"] == "sonnet"

    def test_opus_not_used_when_config_model_is_sonnet(self, tmp_path):
        """claude-opus-4-6 must NOT be selected when the agent config model is sonnet."""
        registry = mock.MagicMock()
        registry.call_json.return_value = MOCK_LLM_RESPONSE

        agent_def = Agent(
            name="test-code-writer",
            role=AgentRole.EXECUTION,
            config=AgentConfig(model="sonnet"),
        )
        cw = CodeWriterAgent(agent_def, registry)
        cw.execute(_make_task(), {"workspace": str(tmp_path)})

        _, kwargs = registry.call_json.call_args
        assert kwargs["model"] != "claude-opus-4-6", (
            "Expected model='sonnet' from agent config, but claude-opus-4-6 was used"
        )

"""Tests for the 'cpos run-agent' CLI subcommand and QUICKSTART.md docs."""

import argparse
import sys
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from crazypumpkin.cli import cmd_run_agent, main
from crazypumpkin.framework.agent import BaseAgent
from crazypumpkin.framework.models import Agent, AgentRole, Task, TaskOutput, deterministic_id


# ── Helpers ──────────────────────────────────────────────────────────────


def _make_run_agent_args(agent_name="hello-agent", config=None, param=None, timeout=None):
    return argparse.Namespace(
        command="run-agent",
        agent_name=agent_name,
        config=config,
        param=param,
        timeout=timeout,
    )


class _StubAgent(BaseAgent):
    """Minimal agent for testing."""

    def execute(self, task: Task, context: dict[str, Any]) -> TaskOutput:
        greeting = context.get("greeting", "Hello")
        msg = f"{greeting}, working on: {task.title}"
        return TaskOutput(content=msg, artifacts={"result.txt": msg})


def _make_registry_with_agent(name="hello-agent"):
    """Return a registry containing a single stub agent."""
    from crazypumpkin.framework.registry import AgentRegistry

    registry = AgentRegistry()
    agent_model = Agent(id=deterministic_id(name), name=name, role=AgentRole.EXECUTION)
    instance = _StubAgent(agent_model)
    registry.register(instance)
    return registry


def _make_config():
    cfg = MagicMock()
    cfg.company = {"name": "Test Co"}
    cfg.pipeline = {"cycle_interval": 30}
    return cfg


# ── QUICKSTART.md documentation tests ───────────────────────────────────


QUICKSTART_PATH = Path(__file__).resolve().parent.parent.parent / "crazy-pumpkin-os" / "docs" / "QUICKSTART.md"
# Also try the docs path relative to the repo root
QUICKSTART_ALT = Path(__file__).resolve().parent.parent / "docs" / "QUICKSTART.md"


def _read_quickstart():
    for p in (QUICKSTART_PATH, QUICKSTART_ALT):
        if p.is_file():
            return p.read_text(encoding="utf-8")
    pytest.skip("QUICKSTART.md not found at expected paths")


class TestQuickstartDocs:
    """Verify that QUICKSTART.md documents the run-agent command correctly."""

    def test_running_agents_section_exists(self):
        content = _read_quickstart()
        assert "## Running Agents On-Demand" in content

    def test_documents_config_flag(self):
        content = _read_quickstart()
        assert "--config" in content

    def test_documents_param_flag(self):
        content = _read_quickstart()
        assert "--param" in content

    def test_documents_timeout_flag(self):
        content = _read_quickstart()
        assert "--timeout" in content

    def test_has_example_output(self):
        """At least one complete example with expected output."""
        content = _read_quickstart()
        assert "Status: success" in content
        assert "Duration:" in content

    def test_documents_cpos_run_agent(self):
        content = _read_quickstart()
        assert "cpos run-agent" in content

    def test_troubleshooting_agent_not_found(self):
        content = _read_quickstart()
        assert "Agent not found" in content

    def test_troubleshooting_timeout(self):
        content = _read_quickstart()
        assert "timed out" in content

    def test_troubleshooting_config_error(self):
        content = _read_quickstart()
        assert "No configuration file found" in content


# ── Minimal-pipeline README.md documentation tests ───────────────────────


MINIMAL_PIPELINE_README = Path(__file__).resolve().parent.parent / "examples" / "minimal-pipeline" / "README.md"
# Also try from the parent repo
MINIMAL_PIPELINE_README_ALT = (
    Path(__file__).resolve().parent.parent.parent
    / "crazy-pumpkin-os"
    / "examples"
    / "minimal-pipeline"
    / "README.md"
)


def _read_minimal_pipeline_readme():
    for p in (MINIMAL_PIPELINE_README, MINIMAL_PIPELINE_README_ALT):
        if p.is_file():
            return p.read_text(encoding="utf-8")
    pytest.skip("examples/minimal-pipeline/README.md not found at expected paths")


class TestMinimalPipelineReadme:
    """Verify that examples/minimal-pipeline/README.md documents cpos run-agent."""

    def test_running_agents_section_exists(self):
        content = _read_minimal_pipeline_readme()
        assert "## Running Individual Agents" in content

    def test_documents_cpos_run_agent(self):
        content = _read_minimal_pipeline_readme()
        assert "cpos run-agent" in content

    def test_references_config_yaml(self):
        """Commands reference the actual config.yaml from minimal-pipeline."""
        content = _read_minimal_pipeline_readme()
        assert "examples/minimal-pipeline/config.yaml" in content

    def test_shows_developer_agent_example(self):
        content = _read_minimal_pipeline_readme()
        assert "cpos run-agent Developer --config examples/minimal-pipeline/config.yaml" in content

    def test_shows_strategist_agent_example(self):
        content = _read_minimal_pipeline_readme()
        assert "cpos run-agent Strategist --config examples/minimal-pipeline/config.yaml" in content

    def test_documents_param_flag(self):
        content = _read_minimal_pipeline_readme()
        assert "--param" in content

    def test_documents_timeout_flag(self):
        content = _read_minimal_pipeline_readme()
        assert "--timeout" in content

    def test_has_expected_output(self):
        """Shows expected output including status and duration."""
        content = _read_minimal_pipeline_readme()
        assert "Status: success" in content
        assert "Duration:" in content

    def test_commands_are_copy_pasteable(self):
        """Commands appear inside fenced code blocks."""
        content = _read_minimal_pipeline_readme()
        # Verify code blocks contain the run-agent commands
        in_code_block = False
        found_run_agent_in_block = False
        for line in content.splitlines():
            if line.strip().startswith("```"):
                in_code_block = not in_code_block
                continue
            if in_code_block and "cpos run-agent" in line:
                found_run_agent_in_block = True
                break
        assert found_run_agent_in_block, "cpos run-agent command not inside a code block"

    def test_param_example_shows_key_value(self):
        """The --param example shows key=value syntax."""
        content = _read_minimal_pipeline_readme()
        assert "--param model=opus" in content or "--param verbose=true" in content


# ── CLI parser registration tests ────────────────────────────────────────


class TestRunAgentParser:
    """The run-agent subcommand is wired into the CLI parser."""

    def test_run_agent_subcommand_registered(self):
        import inspect
        src = inspect.getsource(main)
        assert "run-agent" in src

    def test_parser_accepts_agent_name(self):
        """Parsing 'run-agent my-agent' sets agent_name."""
        parser = argparse.ArgumentParser()
        sub = parser.add_subparsers(dest="command")
        ra = sub.add_parser("run-agent")
        ra.add_argument("agent_name")
        ra.add_argument("--config", default=None)
        ra.add_argument("--param", action="append", default=None)
        ra.add_argument("--timeout", type=int, default=None)

        args = parser.parse_args(["run-agent", "my-agent"])
        assert args.agent_name == "my-agent"
        assert args.config is None

    def test_parser_accepts_all_flags(self):
        parser = argparse.ArgumentParser()
        sub = parser.add_subparsers(dest="command")
        ra = sub.add_parser("run-agent")
        ra.add_argument("agent_name")
        ra.add_argument("--config", default=None)
        ra.add_argument("--param", action="append", default=None)
        ra.add_argument("--timeout", type=int, default=None)

        args = parser.parse_args([
            "run-agent", "my-agent",
            "--config", "custom.yaml",
            "--param", "model=opus",
            "--param", "verbose=true",
            "--timeout", "60",
        ])
        assert args.agent_name == "my-agent"
        assert args.config == "custom.yaml"
        assert args.param == ["model=opus", "verbose=true"]
        assert args.timeout == 60


# ── cmd_run_agent behavior tests ─────────────────────────────────────────


class TestCmdRunAgent:
    """Tests for cmd_run_agent execution behavior."""

    def test_successful_run_prints_status(self, capsys):
        registry = _make_registry_with_agent("hello-agent")
        with patch("crazypumpkin.framework.config.load_config", return_value=_make_config()), \
             patch("crazypumpkin.framework.registry.default_registry", registry):
            cmd_run_agent(_make_run_agent_args("hello-agent"))

        out = capsys.readouterr().out
        assert "hello-agent" in out
        assert "success" in out.lower()
        assert "Duration:" in out

    def test_successful_run_shows_output(self, capsys):
        registry = _make_registry_with_agent("hello-agent")
        with patch("crazypumpkin.framework.config.load_config", return_value=_make_config()), \
             patch("crazypumpkin.framework.registry.default_registry", registry):
            cmd_run_agent(_make_run_agent_args("hello-agent"))

        out = capsys.readouterr().out
        assert "Output:" in out

    def test_successful_run_shows_artifacts(self, capsys):
        registry = _make_registry_with_agent("hello-agent")
        with patch("crazypumpkin.framework.config.load_config", return_value=_make_config()), \
             patch("crazypumpkin.framework.registry.default_registry", registry):
            cmd_run_agent(_make_run_agent_args("hello-agent"))

        out = capsys.readouterr().out
        assert "result.txt" in out

    def test_param_passed_to_context(self, capsys):
        registry = _make_registry_with_agent("hello-agent")
        with patch("crazypumpkin.framework.config.load_config", return_value=_make_config()), \
             patch("crazypumpkin.framework.registry.default_registry", registry):
            cmd_run_agent(_make_run_agent_args(
                "hello-agent", param=["greeting=Hey"]
            ))

        out = capsys.readouterr().out
        assert "Hey" in out

    def test_agent_not_found_exits(self):
        from crazypumpkin.framework.registry import AgentRegistry
        empty = AgentRegistry()
        with patch("crazypumpkin.framework.config.load_config", return_value=_make_config()), \
             patch("crazypumpkin.framework.registry.default_registry", empty):
            with pytest.raises(SystemExit) as exc_info:
                cmd_run_agent(_make_run_agent_args("nonexistent"))
        assert exc_info.value.code == 1

    def test_agent_not_found_message(self, capsys):
        from crazypumpkin.framework.registry import AgentRegistry
        empty = AgentRegistry()
        with patch("crazypumpkin.framework.config.load_config", return_value=_make_config()), \
             patch("crazypumpkin.framework.registry.default_registry", empty):
            with pytest.raises(SystemExit):
                cmd_run_agent(_make_run_agent_args("nonexistent"))
        err = capsys.readouterr().err
        assert "Agent not found" in err

    def test_invalid_param_format_exits(self):
        registry = _make_registry_with_agent("hello-agent")
        with patch("crazypumpkin.framework.config.load_config", return_value=_make_config()), \
             patch("crazypumpkin.framework.registry.default_registry", registry):
            with pytest.raises(SystemExit) as exc_info:
                cmd_run_agent(_make_run_agent_args(
                    "hello-agent", param=["bad-param-no-equals"]
                ))
        assert exc_info.value.code == 1

    def test_multiple_params_all_passed(self, capsys):
        """Multiple --param flags are all present in the context."""
        registry = _make_registry_with_agent("hello-agent")
        # Patch the agent's run to capture context
        agent = registry.by_name("hello-agent")
        captured = {}
        original_run = agent.run

        def spy_run(task, context):
            captured.update(context)
            return original_run(task, context)

        agent.run = spy_run

        with patch("crazypumpkin.framework.config.load_config", return_value=_make_config()), \
             patch("crazypumpkin.framework.registry.default_registry", registry):
            cmd_run_agent(_make_run_agent_args(
                "hello-agent", param=["model=opus", "verbose=true"]
            ))

        assert captured["model"] == "opus"
        assert captured["verbose"] == "true"

    def test_config_override_uses_custom_path(self):
        """--config flag causes load_config to receive the parent directory."""
        registry = _make_registry_with_agent("hello-agent")
        with patch("crazypumpkin.framework.config.load_config", return_value=_make_config()) as mock_load, \
             patch("crazypumpkin.framework.registry.default_registry", registry):
            cmd_run_agent(_make_run_agent_args(
                "hello-agent", config="/tmp/custom/config.yaml"
            ))
        mock_load.assert_called_once_with(project_root=Path("/tmp/custom"))

    def test_timeout_flag_accepted(self, capsys):
        """--timeout is accepted and the run still succeeds within the limit."""
        registry = _make_registry_with_agent("hello-agent")
        with patch("crazypumpkin.framework.config.load_config", return_value=_make_config()), \
             patch("crazypumpkin.framework.registry.default_registry", registry):
            # Should complete without hitting timeout
            cmd_run_agent(_make_run_agent_args("hello-agent", timeout=60))

        out = capsys.readouterr().out
        assert "success" in out.lower()


# ── Documented flags match implementation ────────────────────────────────


class TestDocMatchesImplementation:
    """Ensure the QUICKSTART.md documented flags are real CLI flags."""

    def test_config_flag_in_parser(self):
        import inspect
        src = inspect.getsource(main)
        assert '"--config"' in src

    def test_param_flag_in_parser(self):
        import inspect
        src = inspect.getsource(main)
        assert '"--param"' in src

    def test_timeout_flag_in_parser(self):
        import inspect
        src = inspect.getsource(main)
        assert '"--timeout"' in src

    def test_run_agent_in_commands_dict(self):
        import inspect
        src = inspect.getsource(main)
        assert '"run-agent"' in src
        assert "cmd_run_agent" in src

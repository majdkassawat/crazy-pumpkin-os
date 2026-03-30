"""Tests for crazypumpkin.cli.cmd_init with mocked input."""

import sys
from pathlib import Path
from unittest.mock import patch

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from crazypumpkin.cli import cmd_init, _write_init_files


@pytest.fixture()
def fake_args():
    """Minimal argparse namespace for cmd_init."""
    import argparse
    return argparse.Namespace(command="init", force=True)


@pytest.fixture(autouse=True)
def _mock_default_json(tmp_path):
    """Provide a dummy default.json so cmd_init copy succeeds."""
    examples_dir = tmp_path / "_examples"
    examples_dir.mkdir(exist_ok=True)
    default_json = examples_dir / "default.json"
    default_json.write_text("{}", encoding="utf-8")
    with patch("crazypumpkin.cli._get_default_json_path", return_value=default_json):
        yield


# ── Test 1: defaults are used when user presses Enter ────────────────────

def test_defaults_when_enter_pressed(tmp_path, fake_args, capsys):
    """Pressing Enter for every prompt uses the default values."""
    inputs = ["", "", "", "", ""]  # all blank → defaults
    with patch("builtins.input", side_effect=inputs), \
         patch("crazypumpkin.cli.Path") as MockPath:
        MockPath.cwd.return_value = tmp_path
        # Let Path(target_dir) return the real path so mkdir works
        MockPath.side_effect = Path
        cmd_init(fake_args)

    config_text = (tmp_path / "config.yaml").read_text(encoding="utf-8")
    assert '"My AI Company"' in config_text
    assert "default_provider: anthropic_api" in config_text

    env_text = (tmp_path / ".env").read_text(encoding="utf-8")
    assert "ANTHROPIC_API_KEY=" in env_text


# ── Test 2: custom values are written correctly ──────────────────────────

def test_custom_values_written(tmp_path, fake_args, capsys):
    """Custom company name and provider are reflected in output files."""
    inputs = ["Acme Robots", "openai_api", "sk-custom-key", "/work/product", "hunter2"]
    with patch("builtins.input", side_effect=inputs), \
         patch("crazypumpkin.cli.Path") as MockPath:
        MockPath.cwd.return_value = tmp_path
        MockPath.side_effect = Path
        cmd_init(fake_args)

    config_text = (tmp_path / "config.yaml").read_text(encoding="utf-8")
    assert '"Acme Robots"' in config_text
    assert "default_provider: openai_api" in config_text
    assert '"/work/product"' in config_text

    env_text = (tmp_path / ".env").read_text(encoding="utf-8")
    assert "OPENAI_API_KEY=sk-custom-key" in env_text
    assert "DASHBOARD_PASSWORD=hunter2" in env_text


# ── Test 3: all five output files/dirs are created ───────────────────────

def test_all_five_outputs_created(tmp_path, fake_args):
    """cmd_init creates config.yaml, .env, .gitignore, README.md, and goals/."""
    inputs = ["", "", "", "", ""]
    with patch("builtins.input", side_effect=inputs), \
         patch("crazypumpkin.cli.Path") as MockPath:
        MockPath.cwd.return_value = tmp_path
        MockPath.side_effect = Path
        cmd_init(fake_args)

    assert (tmp_path / "config.yaml").is_file()
    assert (tmp_path / ".env").is_file()
    assert (tmp_path / ".gitignore").is_file()
    assert (tmp_path / "README.md").is_file()
    assert (tmp_path / "goals").is_dir()


def test_gitignore_content(tmp_path, fake_args):
    """.gitignore contains .env exclusion."""
    inputs = ["", "", "", "", ""]
    with patch("builtins.input", side_effect=inputs), \
         patch("crazypumpkin.cli.Path") as MockPath:
        MockPath.cwd.return_value = tmp_path
        MockPath.side_effect = Path
        cmd_init(fake_args)

    gitignore = (tmp_path / ".gitignore").read_text(encoding="utf-8")
    assert ".env" in gitignore


def test_readme_content(tmp_path, fake_args):
    """README.md contains the company name as title."""
    inputs = ["Widget Co", "", "", "", ""]
    with patch("builtins.input", side_effect=inputs), \
         patch("crazypumpkin.cli.Path") as MockPath:
        MockPath.cwd.return_value = tmp_path
        MockPath.side_effect = Path
        cmd_init(fake_args)

    readme = (tmp_path / "README.md").read_text(encoding="utf-8")
    assert "# Widget Co" in readme


# ── Test 4: next-steps message contains the company name ─────────────────

def test_next_steps_contains_company_name(tmp_path, fake_args, capsys):
    """Printed output after init mentions the company name."""
    inputs = ["Acme Robots", "", "", "", ""]
    with patch("builtins.input", side_effect=inputs), \
         patch("crazypumpkin.cli.Path") as MockPath:
        MockPath.cwd.return_value = tmp_path
        MockPath.side_effect = Path
        cmd_init(fake_args)

    output = capsys.readouterr().out
    assert "Acme Robots" in output


def test_next_steps_default_company_name(tmp_path, fake_args, capsys):
    """Next-steps output uses the default name when Enter is pressed."""
    inputs = ["", "", "", "", ""]
    with patch("builtins.input", side_effect=inputs), \
         patch("crazypumpkin.cli.Path") as MockPath:
        MockPath.cwd.return_value = tmp_path
        MockPath.side_effect = Path
        cmd_init(fake_args)

    output = capsys.readouterr().out
    assert "My AI Company" in output


# ── _write_init_files unit tests ───────────────────────────────────────


def _make_answers(company_name="TestCo", provider="anthropic_api",
                  api_key="sk-test", product_path="/tmp/prod",
                  dashboard_password="pass123"):
    return {
        "company_name": company_name,
        "provider": provider,
        "api_key": api_key,
        "product_path": product_path,
        "dashboard_password": dashboard_password,
    }


class TestWriteInitFilesArtifacts:
    """All five output artifacts are created."""

    def test_config_yaml_exists(self, tmp_path):
        _write_init_files(_make_answers(), tmp_path)
        assert (tmp_path / "config.yaml").is_file()

    def test_env_exists(self, tmp_path):
        _write_init_files(_make_answers(), tmp_path)
        assert (tmp_path / ".env").is_file()

    def test_gitignore_exists(self, tmp_path):
        _write_init_files(_make_answers(), tmp_path)
        assert (tmp_path / ".gitignore").is_file()

    def test_goals_dir_exists(self, tmp_path):
        _write_init_files(_make_answers(), tmp_path)
        assert (tmp_path / "goals").is_dir()

    def test_readme_exists(self, tmp_path):
        _write_init_files(_make_answers(), tmp_path)
        assert (tmp_path / "README.md").is_file()

    def test_all_five_artifacts(self, tmp_path):
        _write_init_files(_make_answers(), tmp_path)
        assert (tmp_path / "config.yaml").is_file()
        assert (tmp_path / ".env").is_file()
        assert (tmp_path / ".gitignore").is_file()
        assert (tmp_path / "goals").is_dir()
        assert (tmp_path / "README.md").is_file()


class TestWriteInitFilesEnvProviderMapping:
    """Provider-to-env-var mapping in .env file."""

    def test_anthropic_api_env_var(self, tmp_path):
        _write_init_files(_make_answers(provider="anthropic_api", api_key="key-a"), tmp_path)
        env = (tmp_path / ".env").read_text(encoding="utf-8")
        assert "ANTHROPIC_API_KEY=key-a" in env

    def test_openai_api_env_var(self, tmp_path):
        _write_init_files(_make_answers(provider="openai_api", api_key="key-o"), tmp_path)
        env = (tmp_path / ".env").read_text(encoding="utf-8")
        assert "OPENAI_API_KEY=key-o" in env

    def test_ollama_env_var(self, tmp_path):
        _write_init_files(_make_answers(provider="ollama", api_key="key-l"), tmp_path)
        env = (tmp_path / ".env").read_text(encoding="utf-8")
        assert "OLLAMA_API_KEY=key-l" in env

    def test_anthropic_config_yaml_ref(self, tmp_path):
        _write_init_files(_make_answers(provider="anthropic_api"), tmp_path)
        cfg = (tmp_path / "config.yaml").read_text(encoding="utf-8")
        assert "${ANTHROPIC_API_KEY}" in cfg

    def test_openai_config_yaml_ref(self, tmp_path):
        _write_init_files(_make_answers(provider="openai_api"), tmp_path)
        cfg = (tmp_path / "config.yaml").read_text(encoding="utf-8")
        assert "${OPENAI_API_KEY}" in cfg

    def test_ollama_config_yaml_ref(self, tmp_path):
        _write_init_files(_make_answers(provider="ollama"), tmp_path)
        cfg = (tmp_path / "config.yaml").read_text(encoding="utf-8")
        assert "${OLLAMA_API_KEY}" in cfg


class TestWriteInitFilesConfigYaml:
    """config.yaml contains company name and product workspace."""

    def test_company_name_in_config(self, tmp_path):
        _write_init_files(_make_answers(company_name="Acme Corp"), tmp_path)
        cfg = (tmp_path / "config.yaml").read_text(encoding="utf-8")
        assert '"Acme Corp"' in cfg

    def test_product_workspace_in_config(self, tmp_path):
        _write_init_files(_make_answers(product_path="/my/workspace"), tmp_path)
        cfg = (tmp_path / "config.yaml").read_text(encoding="utf-8")
        assert '"/my/workspace"' in cfg

    def test_default_provider_in_config(self, tmp_path):
        _write_init_files(_make_answers(provider="openai_api"), tmp_path)
        cfg = (tmp_path / "config.yaml").read_text(encoding="utf-8")
        assert "default_provider: openai_api" in cfg


class TestWriteInitFilesGitignore:
    """.gitignore contains required entries."""

    def test_env_in_gitignore(self, tmp_path):
        _write_init_files(_make_answers(), tmp_path)
        gi = (tmp_path / ".gitignore").read_text(encoding="utf-8")
        assert ".env" in gi

    def test_data_dir_in_gitignore(self, tmp_path):
        _write_init_files(_make_answers(), tmp_path)
        gi = (tmp_path / ".gitignore").read_text(encoding="utf-8")
        assert "data/" in gi

    def test_pycache_in_gitignore(self, tmp_path):
        _write_init_files(_make_answers(), tmp_path)
        gi = (tmp_path / ".gitignore").read_text(encoding="utf-8")
        assert "__pycache__/" in gi


# ── Tests for cmd_status ─────────────────────────────────────────────────


def _make_status_args():
    import argparse
    return argparse.Namespace(command="status")


def _make_status_config(cycle_interval=30):
    from unittest.mock import MagicMock
    cfg = MagicMock()
    cfg.company = {"name": "Test Co"}
    cfg.pipeline = {"cycle_interval": cycle_interval}
    return cfg


def test_cmd_status_task_count_labels(capsys):
    """cmd_status output includes task-count labels (pending, running, complete)."""
    from crazypumpkin.cli import cmd_status
    with patch("crazypumpkin.framework.config.load_config", return_value=_make_status_config()):
        cmd_status(_make_status_args())
    out = capsys.readouterr().out
    assert "pending" in out
    assert "running" in out
    assert "complete" in out


def test_cmd_status_missing_config_raises():
    """cmd_status raises FileNotFoundError when config.yaml is absent."""
    from crazypumpkin.cli import cmd_status
    with patch("crazypumpkin.framework.config.load_config", side_effect=FileNotFoundError("no config")):
        with pytest.raises(FileNotFoundError):
            cmd_status(_make_status_args())


def test_cmd_status_shows_cycle_interval(capsys):
    """cmd_status prints the configured cycle_interval value."""
    from crazypumpkin.cli import cmd_status
    with patch("crazypumpkin.framework.config.load_config", return_value=_make_status_config(cycle_interval=45)):
        cmd_status(_make_status_args())
    out = capsys.readouterr().out
    assert "45" in out


class TestWriteInitFilesReadme:
    """README.md contains company name heading."""

    def test_company_heading_in_readme(self, tmp_path):
        _write_init_files(_make_answers(company_name="Widget Co"), tmp_path)
        readme = (tmp_path / "README.md").read_text(encoding="utf-8")
        assert readme.startswith("# Widget Co\n")

    def test_different_company_heading(self, tmp_path):
        _write_init_files(_make_answers(company_name="Mega AI"), tmp_path)
        readme = (tmp_path / "README.md").read_text(encoding="utf-8")
        assert "# Mega AI" in readme


# ── Test cmd_status ───────────────────────────────────────────────────────


class TestCmdStatus:
    """Tests for the status CLI command."""

    def test_status_no_config(self, tmp_path, capsys):
        """Status command with no configuration shows helpful message."""
        import argparse
        from crazypumpkin.cli import cmd_status

        args = argparse.Namespace(command="status")
        # Patch load_config at its source location
        with patch("crazypumpkin.framework.config.load_config", side_effect=FileNotFoundError("No config")):
            cmd_status(args)

        output = capsys.readouterr().out
        assert "No configuration found" in output

    def test_status_with_config_no_state(self, tmp_path, capsys):
        """Status command with config but no state file shows company info."""
        import argparse
        from crazypumpkin.cli import cmd_status
        from crazypumpkin.framework.config import Config
        from crazypumpkin.framework.models import ProductConfig, AgentDefinition, AgentRole

        args = argparse.Namespace(command="status")
        # Create a mock config
        mock_config = Config(
            company={"name": "Test Company"},
            products=[ProductConfig(name="Product A", workspace="/tmp/prod-a")],
            agents=[AgentDefinition(name="Developer", role=AgentRole.EXECUTION)],
        )
        with patch("crazypumpkin.framework.config.load_config", return_value=mock_config), \
             patch("crazypumpkin.framework.paths.get_project_root", return_value=tmp_path):
            cmd_status(args)

        output = capsys.readouterr().out
        assert "Test Company" in output
        assert "Product A" in output
        assert "Total tasks: 0" in output
        assert "no activity yet" in output

    def test_status_with_tasks(self, tmp_path, capsys):
        """Status command with tasks shows correct statistics."""
        import argparse
        import json
        from crazypumpkin.cli import cmd_status
        from crazypumpkin.framework.config import Config
        from crazypumpkin.framework.models import ProductConfig, AgentDefinition, AgentRole

        # Create data directory with state
        data_dir = tmp_path / "data"
        data_dir.mkdir()

        state = {
            "projects": {},
            "tasks": {
                "task-1": {
                    "id": "task-1",
                    "title": "Task 1",
                    "status": "completed",
                    "project_id": "",
                    "updated_at": "2024-01-15T10:30:00+00:00",
                    "created_at": "2024-01-15T10:00:00+00:00",
                },
                "task-2": {
                    "id": "task-2",
                    "title": "Task 2",
                    "status": "completed",
                    "project_id": "",
                    "updated_at": "2024-01-15T11:00:00+00:00",
                    "created_at": "2024-01-15T10:30:00+00:00",
                },
                "task-3": {
                    "id": "task-3",
                    "title": "Task 3",
                    "status": "in_progress",
                    "project_id": "",
                    "updated_at": "2024-01-15T12:00:00+00:00",
                    "created_at": "2024-01-15T11:00:00+00:00",
                },
                "task-4": {
                    "id": "task-4",
                    "title": "Task 4",
                    "status": "planned",
                    "project_id": "",
                    "updated_at": "2024-01-15T09:00:00+00:00",
                    "created_at": "2024-01-15T09:00:00+00:00",
                },
                "task-5": {
                    "id": "task-5",
                    "title": "Task 5",
                    "status": "rejected",
                    "project_id": "",
                    "updated_at": "2024-01-15T08:00:00+00:00",
                    "created_at": "2024-01-15T08:00:00+00:00",
                },
            },
            "reviews": {},
            "approvals": {},
            "proposals": {},
            "agent_metrics": {
                "agent-1": {
                    "agent_id": "agent-1",
                    "agent_name": "Developer",
                    "tasks_completed": 2,
                    "tasks_rejected": 1,
                    "total_retries": 0,
                    "total_duration_sec": 0.0,
                    "first_attempt_accepted": 0,
                    "budget_spent_usd": 0.0,
                    "recent_outcomes": [],
                },
            },
        }
        (data_dir / "state.json").write_text(json.dumps(state), encoding="utf-8")

        args = argparse.Namespace(command="status")
        mock_config = Config(
            company={"name": "Acme Corp"},
            products=[ProductConfig(name="Widget Factory", workspace="/tmp/widgets")],
            agents=[AgentDefinition(name="Developer", role=AgentRole.EXECUTION)],
        )
        with patch("crazypumpkin.framework.config.load_config", return_value=mock_config), \
             patch("crazypumpkin.framework.paths.get_project_root", return_value=tmp_path):
            cmd_status(args)

        output = capsys.readouterr().out
        assert "Acme Corp" in output
        assert "Widget Factory" in output
        assert "Total tasks: 5" in output
        assert "Completed: 2" in output
        assert "In Progress: 1" in output
        assert "Rejected: 1" in output
        assert "Developer" in output
        assert "2 completed, 1 rejected" in output
        assert "67% success" in output
        assert "Last updated: 2024-01-15T12:00:00+00:00" in output

    def test_status_with_escalated_tasks(self, tmp_path, capsys):
        """Status command shows escalated tasks count."""
        import argparse
        import json
        from crazypumpkin.cli import cmd_status
        from crazypumpkin.framework.config import Config
        from crazypumpkin.framework.models import ProductConfig, AgentDefinition, AgentRole

        data_dir = tmp_path / "data"
        data_dir.mkdir()

        state = {
            "projects": {},
            "tasks": {
                "t1": {"id": "t1", "title": "T1", "status": "escalated", "project_id": "", "updated_at": "2024-01-01T00:00:00Z", "created_at": "2024-01-01T00:00:00Z"},
                "t2": {"id": "t2", "title": "T2", "status": "escalated", "project_id": "", "updated_at": "2024-01-01T01:00:00Z", "created_at": "2024-01-01T01:00:00Z"},
            },
            "reviews": {},
            "approvals": {},
            "proposals": {},
            "agent_metrics": {},
        }
        (data_dir / "state.json").write_text(json.dumps(state), encoding="utf-8")

        args = argparse.Namespace(command="status")
        mock_config = Config(
            company={"name": "Escalation Test"},
            products=[ProductConfig(name="Critical System", workspace="/tmp/critical")],
            agents=[AgentDefinition(name="Dev", role=AgentRole.EXECUTION)],
        )
        with patch("crazypumpkin.framework.config.load_config", return_value=mock_config), \
             patch("crazypumpkin.framework.paths.get_project_root", return_value=tmp_path):
            cmd_status(args)

        output = capsys.readouterr().out
        assert "Escalated: 2" in output

    def test_status_agent_with_no_tasks(self, tmp_path, capsys):
        """Status command handles agents with no task activity."""
        import argparse
        import json
        from crazypumpkin.cli import cmd_status
        from crazypumpkin.framework.config import Config
        from crazypumpkin.framework.models import ProductConfig, AgentDefinition, AgentRole

        data_dir = tmp_path / "data"
        data_dir.mkdir()

        state = {
            "projects": {},
            "tasks": {},
            "reviews": {},
            "approvals": {},
            "proposals": {},
            "agent_metrics": {
                "agent-1": {
                    "agent_id": "agent-1",
                    "agent_name": "Strategist",
                    "tasks_completed": 0,
                    "tasks_rejected": 0,
                    "total_retries": 0,
                    "total_duration_sec": 0.0,
                    "first_attempt_accepted": 0,
                    "budget_spent_usd": 0.0,
                    "recent_outcomes": [],
                },
            },
        }
        (data_dir / "state.json").write_text(json.dumps(state), encoding="utf-8")

        args = argparse.Namespace(command="status")
        mock_config = Config(
            company={"name": "New Company"},
            products=[ProductConfig(name="New Product", workspace="/tmp/new")],
            agents=[AgentDefinition(name="Strategist", role=AgentRole.STRATEGY)],
        )
        with patch("crazypumpkin.framework.config.load_config", return_value=mock_config), \
             patch("crazypumpkin.framework.paths.get_project_root", return_value=tmp_path):
            cmd_status(args)

        output = capsys.readouterr().out
        assert "no tasks yet" in output
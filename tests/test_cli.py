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


# ── TestCmdStatus ─────────────────────────────────────────────────────────


class TestCmdStatus:
    """Tests for cmd_status registration, Namespace handling, and stdout."""

    def _make_args(self):
        import argparse
        return argparse.Namespace(command="status")

    def _make_config(self, cycle_interval=30, name="Test Co"):
        from unittest.mock import MagicMock
        cfg = MagicMock()
        cfg.company = {"name": name}
        cfg.pipeline = {"cycle_interval": cycle_interval}
        return cfg

    def test_registered_in_main_parser(self):
        """'status' subcommand is registered in the main CLI parser."""
        import argparse
        from crazypumpkin.cli import main
        import inspect
        src = inspect.getsource(main)
        assert "status" in src

    def test_namespace_command_attr(self):
        """Namespace with command='status' is accepted without error."""
        from crazypumpkin.cli import cmd_status
        with patch("crazypumpkin.framework.config.load_config",
                   return_value=self._make_config()):
            cmd_status(self._make_args())  # should not raise

    def test_stdout_contains_company_name(self, capsys):
        """cmd_status prints the company name."""
        from crazypumpkin.cli import cmd_status
        with patch("crazypumpkin.framework.config.load_config",
                   return_value=self._make_config(name="Skynet LLC")):
            cmd_status(self._make_args())
        out = capsys.readouterr().out
        assert "Skynet LLC" in out

    def test_stdout_contains_cycle_interval(self, capsys):
        """cmd_status prints the cycle_interval."""
        from crazypumpkin.cli import cmd_status
        with patch("crazypumpkin.framework.config.load_config",
                   return_value=self._make_config(cycle_interval=60)):
            cmd_status(self._make_args())
        out = capsys.readouterr().out
        assert "60" in out

    def test_stdout_contains_task_labels(self, capsys):
        """cmd_status prints pending/running/complete task labels."""
        from crazypumpkin.cli import cmd_status
        with patch("crazypumpkin.framework.config.load_config",
                   return_value=self._make_config()):
            cmd_status(self._make_args())
        out = capsys.readouterr().out
        assert "pending" in out
        assert "running" in out
        assert "complete" in out


# ── TestCmdRunContinuous ──────────────────────────────────────────────────


class TestCmdRunContinuous:
    """Tests for cmd_run continuous-mode: loop behavior and --interval override."""

    def _make_run_args(self, once=False, interval=None):
        import argparse
        return argparse.Namespace(command="run", once=once, interval=interval)

    def _make_config(self, cycle_interval=30):
        from unittest.mock import MagicMock
        cfg = MagicMock()
        cfg.company = {"name": "Test Co"}
        # Use a real dict so .get() works correctly
        cfg.pipeline = {"cycle_interval": cycle_interval}
        return cfg

    def _make_scheduler(self):
        from unittest.mock import MagicMock
        scheduler = MagicMock()
        scheduler.run_once.return_value = {"tasks_processed": 1}
        return scheduler

    def test_continuous_loop_calls_sleep(self, capsys):
        """Continuous mode calls time.sleep between cycles."""
        from crazypumpkin.cli import cmd_run
        scheduler = self._make_scheduler()
        sleep_calls = []

        def fake_sleep(n):
            sleep_calls.append(n)
            raise KeyboardInterrupt

        with patch("crazypumpkin.framework.config.load_config",
                   return_value=self._make_config()), \
             patch("crazypumpkin.scheduler.scheduler.Scheduler",
                   return_value=scheduler), \
             patch("crazypumpkin.cli.time.sleep", side_effect=fake_sleep):
            cmd_run(self._make_run_args())

        assert len(sleep_calls) >= 1

    def test_continuous_loop_stops_on_keyboard_interrupt(self, capsys):
        """KeyboardInterrupt exits the loop gracefully."""
        from crazypumpkin.cli import cmd_run
        scheduler = self._make_scheduler()

        with patch("crazypumpkin.framework.config.load_config",
                   return_value=self._make_config()), \
             patch("crazypumpkin.scheduler.scheduler.Scheduler",
                   return_value=scheduler), \
             patch("crazypumpkin.cli.time.sleep", side_effect=KeyboardInterrupt):
            cmd_run(self._make_run_args())  # should not raise

        out = capsys.readouterr().out
        assert "stopped" in out.lower() or "pipeline" in out.lower()

    def test_interval_override_used_in_sleep(self):
        """--interval flag overrides config cycle_interval for time.sleep."""
        from crazypumpkin.cli import cmd_run
        scheduler = self._make_scheduler()
        sleep_calls = []

        def fake_sleep(n):
            sleep_calls.append(n)
            raise KeyboardInterrupt

        with patch("crazypumpkin.framework.config.load_config",
                   return_value=self._make_config(cycle_interval=30)), \
             patch("crazypumpkin.scheduler.scheduler.Scheduler",
                   return_value=scheduler), \
             patch("crazypumpkin.cli.time.sleep", side_effect=fake_sleep):
            cmd_run(self._make_run_args(interval=5))

        assert sleep_calls[0] == 5

    def test_interval_default_from_config(self):
        """Without --interval, cycle_interval from config is used for sleep."""
        from crazypumpkin.cli import cmd_run
        scheduler = self._make_scheduler()
        sleep_calls = []

        def fake_sleep(n):
            sleep_calls.append(n)
            raise KeyboardInterrupt

        with patch("crazypumpkin.framework.config.load_config",
                   return_value=self._make_config(cycle_interval=42)), \
             patch("crazypumpkin.scheduler.scheduler.Scheduler",
                   return_value=scheduler), \
             patch("crazypumpkin.cli.time.sleep", side_effect=fake_sleep):
            cmd_run(self._make_run_args(interval=None))

        assert sleep_calls[0] == 42

    def test_run_once_does_not_call_sleep(self):
        """--once flag runs a single cycle without calling time.sleep."""
        from crazypumpkin.cli import cmd_run
        scheduler = self._make_scheduler()

        with patch("crazypumpkin.framework.config.load_config",
                   return_value=self._make_config()), \
             patch("crazypumpkin.scheduler.scheduler.Scheduler",
                   return_value=scheduler), \
             patch("crazypumpkin.cli.time.sleep") as mock_sleep:
            cmd_run(self._make_run_args(once=True))

        mock_sleep.assert_not_called()

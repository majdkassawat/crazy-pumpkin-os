"""Tests for crazypumpkin.cli.cmd_init with mocked input."""

import sys
from pathlib import Path
from unittest.mock import patch

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from crazypumpkin.cli import cmd_init


@pytest.fixture()
def fake_args():
    """Minimal argparse namespace for cmd_init."""
    import argparse
    return argparse.Namespace(command="init")


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

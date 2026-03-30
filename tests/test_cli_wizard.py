"""Tests for crazypumpkin wizard CLI command."""

import sys
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest
import yaml

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from crazypumpkin.cli.wizard import run_wizard, _prompt, _confirm, _prompt_product, _prompt_agent


# ── _prompt helper ───────────────────────────────────────────────────────


def test_prompt_returns_user_input():
    with patch("builtins.input", return_value="hello"):
        assert _prompt("Name") == "hello"


def test_prompt_returns_default_on_empty():
    with patch("builtins.input", return_value=""):
        assert _prompt("Name", "default_val") == "default_val"


def test_prompt_strips_whitespace():
    with patch("builtins.input", return_value="  spaced  "):
        assert _prompt("Name") == "spaced"


# ── _confirm helper ──────────────────────────────────────────────────────


def test_confirm_yes():
    with patch("builtins.input", return_value="y"):
        assert _confirm("OK?") is True


def test_confirm_no():
    with patch("builtins.input", return_value="n"):
        assert _confirm("OK?") is False


def test_confirm_empty_uses_default_true():
    with patch("builtins.input", return_value=""):
        assert _confirm("OK?", default=True) is True


def test_confirm_empty_uses_default_false():
    with patch("builtins.input", return_value=""):
        assert _confirm("OK?", default=False) is False


# ── _prompt_product ──────────────────────────────────────────────────────


def test_prompt_product_with_defaults():
    """Accepting all defaults returns a valid product dict."""
    with patch("builtins.input", return_value=""):
        product = _prompt_product()
    assert product["name"] == "MyApp"
    assert product["source_dir"] == "src"
    assert product["test_dir"] == "tests"
    assert product["auto_pm"] is False  # _confirm default=False, empty input → False


def test_prompt_product_custom_values():
    inputs = iter(["WebApp", "./products/web", "lib", "spec", "npm test", "dev", "y"])
    with patch("builtins.input", side_effect=inputs):
        product = _prompt_product()
    assert product["name"] == "WebApp"
    assert product["workspace"] == "./products/web"
    assert product["git_branch"] == "dev"


# ── _prompt_agent ────────────────────────────────────────────────────────


def test_prompt_agent_with_defaults():
    """Accepting all defaults returns a valid agent dict."""
    # name, role, model, group, description, class_path, trigger
    with patch("builtins.input", return_value=""):
        agent = _prompt_agent()
    assert agent["name"] == "Developer"
    assert agent["role"] == "execution"
    assert agent["model"] == "sonnet"
    assert "class" not in agent  # empty class_path → not included


def test_prompt_agent_invalid_role_retries():
    """Invalid role is rejected, then a valid one accepted."""
    inputs = iter(["TestAgent", "bogus_role", "execution", "opus", "group1", "desc", "", ""])
    with patch("builtins.input", side_effect=inputs):
        agent = _prompt_agent()
    assert agent["role"] == "execution"
    assert agent["name"] == "TestAgent"


def test_prompt_agent_includes_class_and_trigger():
    inputs = iter(["Dev", "execution", "opus", "exec", "My dev", "my.module.Agent", "backlog > 0"])
    with patch("builtins.input", side_effect=inputs):
        agent = _prompt_agent()
    assert agent["class"] == "my.module.Agent"
    assert agent["trigger"] == "backlog > 0"


# ── run_wizard end-to-end ────────────────────────────────────────────────


def test_run_wizard_writes_config_yaml(tmp_path):
    """Wizard writes a valid config.yaml with expected structure."""
    # Inputs: company_name, product fields (6 + confirm auto_pm),
    #   "n" to stop products, agent fields (7),
    #   "n" to stop agents, "n" for triggers,
    #   pipeline cycle + timeout, "y" to overwrite
    inputs = iter([
        "Acme Corp",                     # company name
        # product
        "MyApp", "./products/myapp", "src", "tests",
        "python -m pytest", "main",
        "n",                              # auto_pm = no
        "n",                              # add another product = no
        # agent
        "Developer", "execution", "sonnet", "execution", "dev agent", "", "",
        "n",                              # add another agent = no
        "n",                              # set triggers = no
        # pipeline
        "30", "3600",
        # overwrite confirm
        "y",
    ])

    mock_validate = MagicMock()

    with patch("builtins.input", side_effect=inputs), \
         patch("crazypumpkin.cli.wizard.Path") as MockPath, \
         patch("crazypumpkin.framework.config._validate_and_build", mock_validate):
        MockPath.cwd.return_value = tmp_path

        run_wizard()

    config_path = tmp_path / "config.yaml"
    assert config_path.exists()
    cfg = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    assert cfg["company"]["name"] == "Acme Corp"
    assert len(cfg["products"]) == 1
    assert len(cfg["agents"]) == 1
    assert cfg["pipeline"]["cycle_interval"] == 30


def test_run_wizard_cancelled_on_overwrite_decline(tmp_path, capsys):
    """If user declines overwrite, wizard exits without writing."""
    # Create an existing config
    existing = tmp_path / "config.yaml"
    existing.write_text("old: config\n", encoding="utf-8")

    inputs = iter([
        "Corp",
        "App", "./p", "src", "tests", "pytest", "main", "n", "n",
        "Dev", "execution", "sonnet", "exec", "", "", "",
        "n", "n",
        "30", "3600",
        "n",  # decline overwrite
    ])

    mock_validate = MagicMock()

    with patch("builtins.input", side_effect=inputs), \
         patch("crazypumpkin.cli.wizard.Path") as MockPath, \
         patch("crazypumpkin.framework.config._validate_and_build", mock_validate):
        MockPath.cwd.return_value = tmp_path

        run_wizard()

    # Old file should be unchanged
    assert existing.read_text(encoding="utf-8") == "old: config\n"
    output = capsys.readouterr().out
    assert "cancelled" in output.lower()

"""Tests for crazypumpkin.cli._write_init_files."""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from crazypumpkin.cli import _write_init_files


@pytest.fixture()
def answers():
    return {
        "company_name": "Test Corp",
        "provider": "anthropic_api",
        "api_key": "sk-test-key",
        "product_path": "/some/product",
        "dashboard_password": "s3cr3t",
    }


def test_env_file_created(tmp_path, answers):
    """.env file is created in the target directory."""
    _write_init_files(answers, tmp_path)
    assert (tmp_path / ".env").exists()


def test_env_file_contains_api_key(tmp_path, answers):
    """.env contains the correct API key env var for the chosen provider."""
    _write_init_files(answers, tmp_path)
    env_text = (tmp_path / ".env").read_text(encoding="utf-8")
    assert "ANTHROPIC_API_KEY=sk-test-key" in env_text


def test_env_file_contains_dashboard_password(tmp_path, answers):
    """.env contains the DASHBOARD_PASSWORD entry."""
    _write_init_files(answers, tmp_path)
    env_text = (tmp_path / ".env").read_text(encoding="utf-8")
    assert "DASHBOARD_PASSWORD=s3cr3t" in env_text


def test_env_file_line_order(tmp_path, answers):
    """.env first line is provider env var, second line is DASHBOARD_PASSWORD."""
    _write_init_files(answers, tmp_path)
    lines = (tmp_path / ".env").read_text(encoding="utf-8").splitlines()
    assert len(lines) == 2
    assert lines[0] == "ANTHROPIC_API_KEY=sk-test-key"
    assert lines[1] == "DASHBOARD_PASSWORD=s3cr3t"


def test_env_file_empty_dashboard_password(tmp_path, answers):
    """.env uses empty string when dashboard_password is missing."""
    del answers["dashboard_password"]
    _write_init_files(answers, tmp_path)
    lines = (tmp_path / ".env").read_text(encoding="utf-8").splitlines()
    assert lines[1] == "DASHBOARD_PASSWORD="


def test_env_file_openai_provider(tmp_path, answers):
    """Provider openai_api maps to OPENAI_API_KEY in .env."""
    answers["provider"] = "openai_api"
    _write_init_files(answers, tmp_path)
    env_text = (tmp_path / ".env").read_text(encoding="utf-8")
    assert "OPENAI_API_KEY=sk-test-key" in env_text


def test_gitignore_excludes_env(tmp_path, answers):
    """.gitignore is written and contains .env."""
    _write_init_files(answers, tmp_path)
    gitignore = (tmp_path / ".gitignore").read_text(encoding="utf-8")
    assert ".env" in gitignore


def test_gitignore_excludes_data(tmp_path, answers):
    """.gitignore contains data/ entry."""
    _write_init_files(answers, tmp_path)
    gitignore = (tmp_path / ".gitignore").read_text(encoding="utf-8")
    assert "data/" in gitignore


def test_gitignore_excludes_pycache(tmp_path, answers):
    """.gitignore contains __pycache__ entry."""
    _write_init_files(answers, tmp_path)
    gitignore = (tmp_path / ".gitignore").read_text(encoding="utf-8")
    assert "__pycache__" in gitignore


def test_config_yaml_created(tmp_path, answers):
    """config.yaml is created alongside .env."""
    _write_init_files(answers, tmp_path)
    assert (tmp_path / "config.yaml").exists()


def test_goals_dir_created(tmp_path, answers):
    """goals/ directory is created."""
    _write_init_files(answers, tmp_path)
    assert (tmp_path / "goals").is_dir()


# --- Products section tests ---

def _load_config(tmp_path):
    """Helper: parse config.yaml and return dict."""
    import yaml

    return yaml.safe_load((tmp_path / "config.yaml").read_text(encoding="utf-8"))


def test_products_name(tmp_path, answers):
    """products[0].name equals '{company_name} Product'."""
    _write_init_files(answers, tmp_path)
    cfg = _load_config(tmp_path)
    assert cfg["products"][0]["name"] == f"{answers['company_name']} Product"


def test_products_workspace(tmp_path, answers):
    """products[0].workspace equals answers['product_path']."""
    _write_init_files(answers, tmp_path)
    cfg = _load_config(tmp_path)
    assert cfg["products"][0]["workspace"] == answers["product_path"]


def test_products_static_fields(tmp_path, answers):
    """products[0] contains the expected static fields."""
    _write_init_files(answers, tmp_path)
    product = _load_config(tmp_path)["products"][0]
    assert product["source_dir"] == "src"
    assert product["test_dir"] == "tests"
    assert product["test_command"] == "python -m pytest tests/ -v --tb=short"
    assert product["git_branch"] == "main"
    assert product["auto_pm"] is False


def test_products_exactly_one_entry(tmp_path, answers):
    """The products section is valid YAML with exactly one entry."""
    _write_init_files(answers, tmp_path)
    cfg = _load_config(tmp_path)
    assert isinstance(cfg["products"], list)
    assert len(cfg["products"]) == 1

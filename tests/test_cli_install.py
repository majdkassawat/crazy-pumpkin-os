"""Smoke tests for CLI install and init flow.

Verifies:
 - `crazypumpkin --help` exits with code 0
 - `crazypumpkin init` creates the config file
 - The generated config is valid YAML matching the expected schema
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path
from unittest.mock import patch

import pytest
import yaml

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from crazypumpkin.cli import _write_init_files, main


# ---------------------------------------------------------------------------
# 1. --help returns exit 0
# ---------------------------------------------------------------------------

def test_help_exits_zero():
    """crazypumpkin --help exits with code 0."""
    src_dir = str(Path(__file__).resolve().parent.parent / "src")
    env = {**__import__("os").environ, "PYTHONPATH": src_dir}
    result = subprocess.run(
        [sys.executable, "-m", "crazypumpkin.cli", "--help"],
        capture_output=True,
        env=env,
    )
    assert result.returncode == 0


def test_help_via_main_exits_zero():
    """main() called with --help raises SystemExit(0)."""
    with patch("sys.argv", ["crazypumpkin", "--help"]):
        with pytest.raises(SystemExit) as exc_info:
            main()
    assert exc_info.value.code == 0


# ---------------------------------------------------------------------------
# 2. init creates config file
# ---------------------------------------------------------------------------

def test_init_creates_config_file(tmp_path):
    """_write_init_files creates config.yaml in the target directory."""
    answers = {
        "company_name": "Smoke Test Co",
        "provider": "anthropic_api",
        "api_key": "sk-smoke",
        "product_path": "/tmp/product",
        "dashboard_password": "pw",
    }
    _write_init_files(answers, tmp_path)
    assert (tmp_path / "config.yaml").exists()


# ---------------------------------------------------------------------------
# 3. Config is valid YAML matching expected schema
# ---------------------------------------------------------------------------

_REQUIRED_SECTIONS = ("company", "products", "llm", "agents", "pipeline",
                      "notifications", "dashboard", "voice")

_ANSWERS = {
    "company_name": "Schema Test Co",
    "provider": "anthropic_api",
    "api_key": "sk-schema",
    "product_path": "/tmp/product",
    "dashboard_password": "pw",
}


def test_config_is_valid_yaml(tmp_path):
    """Generated config.yaml parses without errors."""
    _write_init_files(_ANSWERS, tmp_path)
    content = (tmp_path / "config.yaml").read_text(encoding="utf-8")
    parsed = yaml.safe_load(content)
    assert isinstance(parsed, dict)


@pytest.mark.parametrize("section", _REQUIRED_SECTIONS)
def test_config_has_required_section(tmp_path, section):
    """Generated config.yaml contains the required top-level section."""
    _write_init_files(_ANSWERS, tmp_path)
    content = (tmp_path / "config.yaml").read_text(encoding="utf-8")
    parsed = yaml.safe_load(content)
    assert section in parsed, f"Missing section: {section}"

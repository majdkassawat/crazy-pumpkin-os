"""Tests for crazypumpkin doctor CLI command."""

import os
import sys
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from crazypumpkin.cli.doctor import (
    _check_python_version,
    _check_dependencies,
    _check_config,
    check_config_valid,
    check_env_overrides,
    cmd_doctor,
    MIN_PYTHON,
    REQUIRED_DEPS,
)


# ── _check_python_version ───────────────────────────────────────────────


def test_python_version_pass():
    """Current Python should satisfy the min version check."""
    ok, msg = _check_python_version()
    # We're running on >= 3.11 if the project works at all
    assert ok is True
    assert "PASS" not in msg  # msg is just the description, not the formatted line
    assert ">=" in msg


def test_python_version_fail():
    """Simulated old Python version fails the check."""
    fake_version = (3, 9, 0, "final", 0)
    with patch("crazypumpkin.cli.doctor.sys") as mock_sys:
        mock_sys.version_info = fake_version
        ok, msg = _check_python_version()
    assert ok is False
    assert "3.9" in msg
    assert "requires" in msg


# ── _check_dependencies ─────────────────────────────────────────────────


def test_check_dependencies_all_present():
    """When all deps are importable, all results are True."""
    results = _check_dependencies()
    # At minimum pyyaml should be installed (we import it in tests)
    yaml_check = [r for r in results if "pyyaml" in r[1]]
    assert len(yaml_check) == 1
    assert yaml_check[0][0] is True


def test_check_dependencies_missing_package():
    """A missing import yields a False result."""
    original_import = __builtins__.__import__ if hasattr(__builtins__, "__import__") else __import__

    def fake_import(name, *args, **kwargs):
        if name == "httpx":
            raise ImportError("No module named 'httpx'")
        return original_import(name, *args, **kwargs)

    with patch("importlib.import_module", side_effect=fake_import):
        results = _check_dependencies()

    httpx_check = [r for r in results if "httpx" in r[1]]
    assert len(httpx_check) == 1
    assert httpx_check[0][0] is False
    assert "not installed" in httpx_check[0][1]


# ── _check_config ────────────────────────────────────────────────────────


def test_check_config_valid():
    """Valid config returns pass."""
    mock_config = MagicMock()
    with patch("crazypumpkin.cli.doctor.load_config", return_value=mock_config, create=True), \
         patch.dict("sys.modules", {}):
        # Patch at the point of use inside the function
        with patch("crazypumpkin.framework.config.load_config", return_value=mock_config):
            ok, msg = _check_config()
    assert ok is True
    assert "valid" in msg


def test_check_config_file_not_found():
    """Missing config file yields a helpful message."""
    with patch("crazypumpkin.framework.config.load_config", side_effect=FileNotFoundError):
        ok, msg = _check_config()
    assert ok is False
    assert "no config file found" in msg


def test_check_config_invalid():
    """Invalid config content yields a failure."""
    with patch("crazypumpkin.framework.config.load_config", side_effect=ValueError("bad field")):
        ok, msg = _check_config()
    assert ok is False
    assert "invalid" in msg
    assert "bad field" in msg


# ── cmd_doctor integration ───────────────────────────────────────────────


def test_cmd_doctor_all_pass(capsys):
    """When everything is healthy, doctor prints 'All checks passed.'."""
    with patch("crazypumpkin.cli.doctor._check_python_version", return_value=(True, "Python OK")), \
         patch("crazypumpkin.cli.doctor._check_dependencies", return_value=[(True, "dep OK")]), \
         patch("crazypumpkin.cli.doctor._check_config", return_value=(True, "config OK")):
        cmd_doctor(MagicMock())

    output = capsys.readouterr().out
    assert "All checks passed" in output
    assert "[PASS]" in output


def test_cmd_doctor_failure_exits(capsys):
    """When a check fails, doctor exits with code 1."""
    with patch("crazypumpkin.cli.doctor._check_python_version", return_value=(False, "Python too old")), \
         patch("crazypumpkin.cli.doctor._check_dependencies", return_value=[]), \
         patch("crazypumpkin.cli.doctor._check_config", return_value=(True, "config OK")):
        with pytest.raises(SystemExit) as exc_info:
            cmd_doctor(MagicMock())

    assert exc_info.value.code == 1
    output = capsys.readouterr().out
    assert "[FAIL]" in output
    assert "Some checks failed" in output


def test_cmd_doctor_dep_failure(capsys):
    """A single failed dependency triggers exit 1."""
    with patch("crazypumpkin.cli.doctor._check_python_version", return_value=(True, "OK")), \
         patch("crazypumpkin.cli.doctor._check_dependencies", return_value=[
             (True, "pyyaml installed"),
             (False, "httpx not installed"),
         ]), \
         patch("crazypumpkin.cli.doctor._check_config", return_value=(True, "OK")):
        with pytest.raises(SystemExit) as exc_info:
            cmd_doctor(MagicMock())

    assert exc_info.value.code == 1
    output = capsys.readouterr().out
    assert "[FAIL]" in output
    assert "httpx" in output


# ── check_config_valid ────────────────────────────────────────────────


def test_check_config_valid_ok():
    """Valid config returns Config schema OK."""
    config = {
        "company": {"name": "TestCo"},
        "agents": [{"name": "Dev", "role": "execution"}],
    }
    name, passed, detail = check_config_valid(config)
    assert name == "Config schema"
    assert passed is True
    assert detail == "OK"


def test_check_config_valid_fail_missing_company():
    """Missing required field 'company' yields FAIL with detail."""
    config = {"agents": [{"name": "Dev", "role": "execution"}]}
    name, passed, detail = check_config_valid(config)
    assert name == "Config schema"
    assert passed is False
    assert "FAIL" in detail
    assert "company" in detail


def test_check_config_valid_fail_missing_agents():
    """Missing required field 'agents' yields FAIL."""
    config = {"company": {"name": "TestCo"}}
    name, passed, detail = check_config_valid(config)
    assert name == "Config schema"
    assert passed is False
    assert "FAIL" in detail
    assert "agents" in detail


# ── check_env_overrides ──────────────────────────────────────────────


def test_check_env_overrides_none_active():
    """No CPOS_* env vars → 'none active'."""
    # Clear any CPOS_* vars that might be set
    env = {k: v for k, v in os.environ.items() if not k.startswith("CPOS_")}
    with patch.dict(os.environ, env, clear=True):
        name, passed, detail = check_env_overrides({"company": {"name": "X"}})
    assert name == "Env overrides"
    assert passed is True
    assert "none active" in detail


def test_check_env_overrides_with_active():
    """Active CPOS_* vars are reported."""
    env = {k: v for k, v in os.environ.items() if not k.startswith("CPOS_")}
    env["CPOS_COMPANY__NAME"] = "OverrideCo"
    with patch.dict(os.environ, env, clear=True):
        name, passed, detail = check_env_overrides({"company": {"name": "X"}})
    assert name == "Env overrides"
    assert passed is True
    assert "CPOS_COMPANY__NAME" in detail
    assert "OverrideCo" in detail


# ── cmd_doctor structured output ─────────────────────────────────────


class _FakeConfig:
    """A plain object whose __dict__ exposes valid config fields."""
    def __init__(self, overrides=None):
        self.company = {"name": "TestCo"}
        self.agents = [{"name": "Dev", "role": "execution"}]
        self.products = []
        self.llm = {}
        self.pipeline = {}
        self.notifications = {}
        self.dashboard = {}
        self.voice = {}
        if overrides:
            self.__dict__.update(overrides)


def _make_valid_config():
    return _FakeConfig()


def test_cmd_doctor_shows_config_schema_ok(capsys):
    """Doctor output includes 'Config schema: OK' for valid config."""
    mock_config = _make_valid_config()
    env = {k: v for k, v in os.environ.items() if not k.startswith("CPOS_")}
    with patch("crazypumpkin.cli.doctor._check_python_version", return_value=(True, "Python OK")), \
         patch("crazypumpkin.cli.doctor._check_dependencies", return_value=[(True, "dep OK")]), \
         patch("crazypumpkin.cli.doctor._check_config", return_value=(True, "config OK")), \
         patch("crazypumpkin.cli.doctor._check_validation", return_value=(True, "config schema valid")), \
         patch("crazypumpkin.framework.config.load_config", return_value=mock_config), \
         patch.dict(os.environ, env, clear=True):
        cmd_doctor(MagicMock())

    output = capsys.readouterr().out
    assert "Config schema: OK" in output


def test_cmd_doctor_shows_config_schema_fail(capsys):
    """Doctor output includes 'Config schema: FAIL' for invalid config."""
    mock_config = _FakeConfig()
    # Remove agents to trigger validation failure
    del mock_config.agents
    env = {k: v for k, v in os.environ.items() if not k.startswith("CPOS_")}
    with patch("crazypumpkin.cli.doctor._check_python_version", return_value=(True, "Python OK")), \
         patch("crazypumpkin.cli.doctor._check_dependencies", return_value=[(True, "dep OK")]), \
         patch("crazypumpkin.cli.doctor._check_config", return_value=(True, "config OK")), \
         patch("crazypumpkin.cli.doctor._check_validation", return_value=(True, "config schema valid")), \
         patch("crazypumpkin.framework.config.load_config", return_value=mock_config), \
         patch.dict(os.environ, env, clear=True):
        cmd_doctor(MagicMock())

    output = capsys.readouterr().out
    assert "Config schema: FAIL" in output
    assert "agents" in output


def test_cmd_doctor_shows_env_overrides(capsys):
    """Doctor output includes 'Env overrides:' section listing CPOS_* vars."""
    mock_config = _make_valid_config()
    env = {k: v for k, v in os.environ.items() if not k.startswith("CPOS_")}
    env["CPOS_COMPANY__NAME"] = "OverrideCo"
    with patch("crazypumpkin.cli.doctor._check_python_version", return_value=(True, "Python OK")), \
         patch("crazypumpkin.cli.doctor._check_dependencies", return_value=[(True, "dep OK")]), \
         patch("crazypumpkin.cli.doctor._check_config", return_value=(True, "config OK")), \
         patch("crazypumpkin.cli.doctor._check_validation", return_value=(True, "config schema valid")), \
         patch("crazypumpkin.framework.config.load_config", return_value=mock_config), \
         patch.dict(os.environ, env, clear=True):
        cmd_doctor(MagicMock())

    output = capsys.readouterr().out
    assert "Env overrides:" in output
    assert "CPOS_COMPANY__NAME" in output


def test_cmd_doctor_env_overrides_none(capsys):
    """Doctor output shows 'Env overrides: none active' when no CPOS_* vars set."""
    mock_config = _make_valid_config()
    env = {k: v for k, v in os.environ.items() if not k.startswith("CPOS_")}
    with patch("crazypumpkin.cli.doctor._check_python_version", return_value=(True, "Python OK")), \
         patch("crazypumpkin.cli.doctor._check_dependencies", return_value=[(True, "dep OK")]), \
         patch("crazypumpkin.cli.doctor._check_config", return_value=(True, "config OK")), \
         patch("crazypumpkin.cli.doctor._check_validation", return_value=(True, "config schema valid")), \
         patch("crazypumpkin.framework.config.load_config", return_value=mock_config), \
         patch.dict(os.environ, env, clear=True):
        cmd_doctor(MagicMock())

    output = capsys.readouterr().out
    assert "Env overrides: none active" in output


# ── Config loading applies env overrides ─────────────────────────────


def test_config_loading_applies_env_overrides(tmp_path):
    """Config loading in framework/config.py applies env overrides before returning."""
    import yaml
    config_data = {
        "company": {"name": "OriginalCo"},
        "products": [{"name": "P", "workspace": str(tmp_path)}],
        "agents": [{"name": "Dev", "role": "execution"}],
    }
    config_file = tmp_path / "config.yaml"
    config_file.write_text(yaml.dump(config_data), encoding="utf-8")

    env = {k: v for k, v in os.environ.items() if not k.startswith("CPOS_")}
    env["CPOS_COMPANY__NAME"] = "OverriddenCo"

    from crazypumpkin.framework.config import load_config
    with patch.dict(os.environ, env, clear=True):
        cfg = load_config(tmp_path)

    assert cfg.company["name"] == "OverriddenCo"


# ── Init validates generated config ──────────────────────────────────


def test_init_validates_default_template_no_warnings(tmp_path, capsys):
    """cpos init validates the generated config and prints no warnings for default template."""
    from crazypumpkin.cli import _write_init_files
    from crazypumpkin.config.validation import validate_config
    import yaml

    # Use forward slashes to avoid YAML escaping issues on Windows
    product_workspace = str(tmp_path / "products" / "app").replace("\\", "/")
    answers = {
        "company_name": "TestCo",
        "provider": "anthropic_api",
        "api_key": "sk-test",
        "product_path": product_workspace,
        "dashboard_password": "secret",
    }
    _write_init_files(answers, tmp_path)

    config_text = (tmp_path / "config.yaml").read_text(encoding="utf-8")
    config_dict = yaml.safe_load(config_text)
    result = validate_config(config_dict)

    # Default template should have no validation errors
    assert result.valid is True, f"Validation errors: {[e.message for e in result.errors]}"

"""Tests for crazypumpkin doctor CLI command."""

import sys
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from crazypumpkin.cli.doctor import (
    _check_python_version,
    _check_dependencies,
    _check_config,
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

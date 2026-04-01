"""Tests for scripts/demo_config_validation.py — verify demo functions run without errors."""
import importlib
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

_demo = importlib.import_module("demo_config_validation")
demo_validation = _demo.demo_validation
demo_env_overrides = _demo.demo_env_overrides


def test_demo_validation_runs_without_exception(capsys):
    """demo_validation() should complete without raising."""
    demo_validation()
    captured = capsys.readouterr()
    # Should test 3 configs and print results
    assert "Config 1" in captured.out
    assert "Config 2" in captured.out
    assert "Config 3" in captured.out
    assert "Valid!" in captured.out


def test_demo_env_overrides_runs_without_exception(capsys):
    """demo_env_overrides() should complete without raising and clean up env vars."""
    import os

    demo_env_overrides()
    captured = capsys.readouterr()
    # Should print overridden values with type coercion
    assert "dashboard.port" in captured.out
    assert "voice.enabled" in captured.out
    # Env vars should be cleaned up
    assert "CPOS_DASHBOARD__PORT" not in os.environ
    assert "CPOS_VOICE__ENABLED" not in os.environ

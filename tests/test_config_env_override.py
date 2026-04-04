"""Tests for crazypumpkin.config.env_override."""

import os
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from crazypumpkin.config.env_override import apply_env_overrides, env_key_for_path


# -- env_key_for_path ----------------------------------------------------------


def test_env_key_for_path_basic():
    assert env_key_for_path("pipeline.max_retries") == "CPOS_PIPELINE_MAX_RETRIES"


def test_env_key_for_path_single_segment():
    assert env_key_for_path("debug") == "CPOS_DEBUG"


def test_env_key_for_path_custom_prefix():
    assert env_key_for_path("a.b", prefix="MYAPP") == "MYAPP_A_B"


# -- apply_env_overrides: string replacement -----------------------------------


def test_override_replaces_nested_string(monkeypatch):
    monkeypatch.setenv("CPOS_OBSERVABILITY_LOGGING_LEVEL", "DEBUG")
    config = {"observability": {"logging": {"level": "INFO"}}}
    result = apply_env_overrides(config)
    assert result["observability"]["logging"]["level"] == "DEBUG"


# -- apply_env_overrides: int coercion -----------------------------------------


def test_override_coerces_to_int(monkeypatch):
    monkeypatch.setenv("CPOS_SCHEDULER_INTERVAL", "3")
    config = {"scheduler": {"interval": 30}}
    result = apply_env_overrides(config)
    assert result["scheduler"]["interval"] == 3
    assert isinstance(result["scheduler"]["interval"], int)


# -- apply_env_overrides: float coercion ---------------------------------------


def test_override_coerces_to_float(monkeypatch):
    monkeypatch.setenv("CPOS_PIPELINE_THRESHOLD", "0.75")
    config = {"pipeline": {"threshold": 0.5}}
    result = apply_env_overrides(config)
    assert result["pipeline"]["threshold"] == 0.75
    assert isinstance(result["pipeline"]["threshold"], float)


# -- apply_env_overrides: bool coercion ----------------------------------------


def test_override_coerces_true(monkeypatch):
    monkeypatch.setenv("CPOS_VOICE_ENABLED", "true")
    config = {"voice": {"enabled": False}}
    result = apply_env_overrides(config)
    assert result["voice"]["enabled"] is True


def test_override_coerces_false(monkeypatch):
    monkeypatch.setenv("CPOS_VOICE_ENABLED", "false")
    config = {"voice": {"enabled": True}}
    result = apply_env_overrides(config)
    assert result["voice"]["enabled"] is False


# -- apply_env_overrides: no mutation ------------------------------------------


def test_original_config_not_mutated(monkeypatch):
    monkeypatch.setenv("CPOS_SCHEDULER_INTERVAL", "99")
    config = {"scheduler": {"interval": 30}}
    result = apply_env_overrides(config)
    assert config["scheduler"]["interval"] == 30
    assert result["scheduler"]["interval"] == 99


# -- apply_env_overrides: no env var set => value unchanged --------------------


def test_no_env_var_leaves_value_unchanged():
    config = {"scheduler": {"interval": 30}}
    result = apply_env_overrides(config)
    assert result["scheduler"]["interval"] == 30

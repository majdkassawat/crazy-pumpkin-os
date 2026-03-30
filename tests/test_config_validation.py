"""Tests for crazypumpkin.config validation and defaults."""

import importlib
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

_cfg_mod = importlib.import_module("crazypumpkin.config")
DEFAULT_CONFIG = _cfg_mod.DEFAULT_CONFIG
get_default_config = _cfg_mod.get_default_config
ConfigValidationError = _cfg_mod.ConfigValidationError
validate_config = _cfg_mod.validate_config
merge_with_defaults = _cfg_mod.merge_with_defaults


# -- get_default_config --------------------------------------------------------


def test_get_default_config_has_required_keys():
    """get_default_config() returns a dict with all top-level keys."""
    cfg = get_default_config()
    assert isinstance(cfg, dict)
    for key in ("agents", "triggers", "plugins", "observability", "scheduler"):
        assert key in cfg, f"Missing key: {key}"


def test_get_default_config_returns_deep_copy():
    """Mutating the result does not affect DEFAULT_CONFIG."""
    cfg = get_default_config()
    cfg["agents"] = []
    assert len(DEFAULT_CONFIG["agents"]) > 0


# -- validate_config -----------------------------------------------------------


def test_validate_empty_config_returns_errors():
    """validate_config({}) returns errors listing missing required keys."""
    errors = validate_config({})
    assert len(errors) > 0
    for key in ("agents", "triggers", "plugins", "observability", "scheduler"):
        assert any(key in e for e in errors), f"No error mentioning '{key}'"


def test_validate_default_config_returns_no_errors():
    """validate_config(get_default_config()) returns empty list."""
    errors = validate_config(get_default_config())
    assert errors == []


def test_validate_agents_must_be_non_empty():
    """An empty agents list produces a validation error."""
    cfg = get_default_config()
    cfg["agents"] = []
    errors = validate_config(cfg)
    assert any("agents" in e for e in errors)


def test_validate_agent_missing_name():
    """An agent without 'name' produces a validation error."""
    cfg = get_default_config()
    cfg["agents"] = [{"role": "execution"}]
    errors = validate_config(cfg)
    assert any("name" in e for e in errors)


def test_validate_agent_missing_role():
    """An agent without 'role' produces a validation error."""
    cfg = get_default_config()
    cfg["agents"] = [{"name": "dev"}]
    errors = validate_config(cfg)
    assert any("role" in e for e in errors)


def test_validate_agent_non_string_name():
    """An agent with a non-string 'name' produces a validation error."""
    cfg = get_default_config()
    cfg["agents"] = [{"name": 123, "role": "dev"}]
    errors = validate_config(cfg)
    assert any("name" in e for e in errors)


def test_validate_trigger_expression_must_be_string():
    """A trigger with a non-string expression produces a validation error."""
    cfg = get_default_config()
    cfg["triggers"] = [{"expression": 42}]
    errors = validate_config(cfg)
    assert any("expression" in e for e in errors)


def test_validate_plugin_path_must_be_string():
    """A plugin with a non-string path produces a validation error."""
    cfg = get_default_config()
    cfg["plugins"] = [{"path": 42}]
    errors = validate_config(cfg)
    assert any("path" in e for e in errors)


# -- merge_with_defaults -------------------------------------------------------


def test_merge_fills_missing_sections():
    """merge_with_defaults fills all sections from defaults when user only supplies agents."""
    merged = merge_with_defaults({"agents": [{"name": "x", "role": "dev"}]})
    assert merged["agents"] == [{"name": "x", "role": "dev"}]
    for key in ("triggers", "plugins", "observability", "scheduler"):
        assert key in merged
        assert merged[key] == get_default_config()[key]


def test_merge_preserves_user_overrides():
    """User-provided values override defaults."""
    merged = merge_with_defaults({"scheduler": {"interval": 60, "enabled": False}})
    assert merged["scheduler"]["interval"] == 60
    assert merged["scheduler"]["enabled"] is False


def test_merge_deep_merges_nested_dicts():
    """Nested dicts are deep-merged, not replaced."""
    merged = merge_with_defaults({"observability": {"metrics": {"enabled": True}}})
    assert merged["observability"]["metrics"]["enabled"] is True
    # logging key from defaults is preserved
    assert "logging" in merged["observability"]


def test_merge_does_not_mutate_defaults():
    """merge_with_defaults does not modify DEFAULT_CONFIG."""
    import copy
    before = copy.deepcopy(DEFAULT_CONFIG)
    merge_with_defaults({"agents": [{"name": "z", "role": "r"}]})
    assert DEFAULT_CONFIG == before


# -- ConfigValidationError -----------------------------------------------------


def test_config_validation_error_stores_errors():
    """ConfigValidationError stores the list of error strings."""
    errs = ["missing key: agents", "missing key: triggers"]
    exc = ConfigValidationError(errs)
    assert exc.errors == errs
    assert isinstance(exc, Exception)


def test_config_validation_error_message():
    """ConfigValidationError has a meaningful str representation."""
    exc = ConfigValidationError(["err1"])
    assert "err1" in str(exc)

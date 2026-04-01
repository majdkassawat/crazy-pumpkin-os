"""Tests for crazypumpkin.config.env_override.

Covers resolve_env_overrides and list_active_overrides with schema-aware
type coercion, boolean/integer/list handling, nested-key resolution,
deep-copy safety, and security edge cases.
"""

import copy
import importlib
import os
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

_mod = importlib.import_module("crazypumpkin.config.env_override")
resolve_env_overrides = _mod.resolve_env_overrides
list_active_overrides = _mod.list_active_overrides


def _base_config():
    return {
        "llm": {
            "default_provider": "anthropic_api",
        },
        "dashboard": {
            "enabled": False,
            "port": 8500,
        },
        "agents": {
            "tags": [],
        },
    }


class TestResolveEnvOverrides:
    def test_nested_string_override(self, monkeypatch):
        """CPOS_LLM__DEFAULT_PROVIDER=openai overrides config['llm']['default_provider']."""
        monkeypatch.setenv("CPOS_LLM__DEFAULT_PROVIDER", "openai")
        cfg = _base_config()
        result = resolve_env_overrides(cfg)
        assert result["llm"]["default_provider"] == "openai"

    def test_boolean_true(self, monkeypatch):
        """CPOS_DASHBOARD__ENABLED=true sets config['dashboard']['enabled'] to True."""
        monkeypatch.setenv("CPOS_DASHBOARD__ENABLED", "true")
        cfg = _base_config()
        result = resolve_env_overrides(cfg)
        assert result["dashboard"]["enabled"] is True

    def test_boolean_false(self, monkeypatch):
        """CPOS_DASHBOARD__ENABLED=false sets to boolean False."""
        monkeypatch.setenv("CPOS_DASHBOARD__ENABLED", "false")
        cfg = _base_config()
        result = resolve_env_overrides(cfg)
        assert result["dashboard"]["enabled"] is False

    def test_boolean_one(self, monkeypatch):
        """CPOS_DASHBOARD__ENABLED=1 sets to boolean True (field is bool)."""
        monkeypatch.setenv("CPOS_DASHBOARD__ENABLED", "1")
        cfg = _base_config()
        result = resolve_env_overrides(cfg)
        assert result["dashboard"]["enabled"] is True

    def test_boolean_zero(self, monkeypatch):
        """CPOS_DASHBOARD__ENABLED=0 sets to boolean False (field is bool)."""
        monkeypatch.setenv("CPOS_DASHBOARD__ENABLED", "0")
        cfg = _base_config()
        result = resolve_env_overrides(cfg)
        assert result["dashboard"]["enabled"] is False

    def test_list_comma_separated(self, monkeypatch):
        """CPOS_AGENTS__TAGS=a,b,c sets config['agents']['tags'] to ['a','b','c']."""
        monkeypatch.setenv("CPOS_AGENTS__TAGS", "a,b,c")
        cfg = _base_config()
        result = resolve_env_overrides(cfg)
        assert result["agents"]["tags"] == ["a", "b", "c"]

    def test_integer_coercion(self, monkeypatch):
        """CPOS_DASHBOARD__PORT=9000 sets to int 9000."""
        monkeypatch.setenv("CPOS_DASHBOARD__PORT", "9000")
        cfg = _base_config()
        result = resolve_env_overrides(cfg)
        assert result["dashboard"]["port"] == 9000
        assert isinstance(result["dashboard"]["port"], int)

    def test_schema_aware_int_zero(self, monkeypatch):
        """CPOS_DASHBOARD__PORT=0 must stay int 0, not become bool False."""
        monkeypatch.setenv("CPOS_DASHBOARD__PORT", "0")
        cfg = _base_config()
        result = resolve_env_overrides(cfg)
        assert result["dashboard"]["port"] == 0
        assert isinstance(result["dashboard"]["port"], int)
        assert result["dashboard"]["port"] is not False

    def test_schema_aware_int_one(self, monkeypatch):
        """CPOS_DASHBOARD__PORT=1 must stay int 1, not become bool True."""
        monkeypatch.setenv("CPOS_DASHBOARD__PORT", "1")
        cfg = _base_config()
        result = resolve_env_overrides(cfg)
        assert result["dashboard"]["port"] == 1
        assert isinstance(result["dashboard"]["port"], int)

    def test_deep_copy_original_not_mutated(self, monkeypatch):
        """Original config dict must not be mutated."""
        monkeypatch.setenv("CPOS_LLM__DEFAULT_PROVIDER", "openai")
        cfg = _base_config()
        original = copy.deepcopy(cfg)
        resolve_env_overrides(cfg)
        assert cfg == original

    def test_no_overrides_returns_copy(self):
        """With no matching env vars, returns an equal but distinct copy."""
        cfg = _base_config()
        result = resolve_env_overrides(cfg, prefix="XYZUNUSED")
        assert result == cfg
        assert result is not cfg

    def test_creates_missing_sections(self, monkeypatch):
        """Env var for a non-existent section creates it."""
        monkeypatch.setenv("CPOS_NEW_SECTION__KEY", "value")
        cfg = _base_config()
        result = resolve_env_overrides(cfg)
        assert result["new_section"]["key"] == "value"

    def test_custom_prefix(self, monkeypatch):
        """Custom prefix works correctly."""
        monkeypatch.setenv("MYAPP_FOO__BAR", "baz")
        cfg = {"foo": {"bar": "old"}}
        result = resolve_env_overrides(cfg, prefix="MYAPP")
        assert result["foo"]["bar"] == "baz"

    def test_malformed_env_key_empty_segment(self, monkeypatch):
        """Env vars with empty path segments (triple underscore) are skipped."""
        monkeypatch.setenv("CPOS___BAD", "value")
        cfg = _base_config()
        original = copy.deepcopy(cfg)
        result = resolve_env_overrides(cfg)
        # Should not crash or inject keys; config unchanged for this var
        assert "bad" not in result
        assert "" not in result

    def test_malformed_env_key_prefix_only(self, monkeypatch):
        """Env var that is exactly PREFIX_ with nothing after is skipped."""
        monkeypatch.setenv("CPOS_", "value")
        cfg = _base_config()
        result = resolve_env_overrides(cfg)
        assert "" not in result

    def test_heuristic_new_key_zero_is_int(self, monkeypatch):
        """For new keys not in config, '0' becomes int 0 (not bool False)."""
        monkeypatch.setenv("CPOS_BRAND_NEW__COUNT", "0")
        cfg = _base_config()
        result = resolve_env_overrides(cfg)
        assert result["brand_new"]["count"] == 0
        assert isinstance(result["brand_new"]["count"], int)

    def test_heuristic_new_key_one_is_int(self, monkeypatch):
        """For new keys not in config, '1' becomes int 1 (not bool True)."""
        monkeypatch.setenv("CPOS_BRAND_NEW__COUNT", "1")
        cfg = _base_config()
        result = resolve_env_overrides(cfg)
        assert result["brand_new"]["count"] == 1
        assert isinstance(result["brand_new"]["count"], int)


class TestListActiveOverrides:
    def test_returns_correct_tuples(self, monkeypatch):
        """list_active_overrides returns (env_var_name, config_path, value) tuples."""
        monkeypatch.setenv("CPOS_LLM__DEFAULT_PROVIDER", "openai")
        monkeypatch.setenv("CPOS_DASHBOARD__ENABLED", "true")
        cfg = _base_config()
        overrides = list_active_overrides(cfg)
        env_names = [o[0] for o in overrides]
        assert "CPOS_LLM__DEFAULT_PROVIDER" in env_names
        assert "CPOS_DASHBOARD__ENABLED" in env_names
        for name, path, value in overrides:
            if name == "CPOS_LLM__DEFAULT_PROVIDER":
                assert path == "llm.default_provider"
                assert value == "openai"
            if name == "CPOS_DASHBOARD__ENABLED":
                assert path == "dashboard.enabled"
                assert value is True

    def test_empty_when_no_env_vars(self):
        """Returns empty list when no matching env vars are set."""
        cfg = _base_config()
        overrides = list_active_overrides(cfg, prefix="XYZUNUSED")
        assert overrides == []

    def test_list_value_in_overrides(self, monkeypatch):
        """Comma-separated values are coerced in list_active_overrides too."""
        monkeypatch.setenv("CPOS_AGENTS__TAGS", "x,y")
        cfg = _base_config()
        overrides = list_active_overrides(cfg)
        match = [o for o in overrides if o[0] == "CPOS_AGENTS__TAGS"]
        assert len(match) == 1
        assert match[0][2] == ["x", "y"]

    def test_schema_aware_in_overrides(self, monkeypatch):
        """list_active_overrides also uses schema-aware coercion."""
        monkeypatch.setenv("CPOS_DASHBOARD__PORT", "0")
        cfg = _base_config()
        overrides = list_active_overrides(cfg)
        match = [o for o in overrides if o[0] == "CPOS_DASHBOARD__PORT"]
        assert len(match) == 1
        assert match[0][2] == 0
        assert isinstance(match[0][2], int)

    def test_skips_malformed_keys(self, monkeypatch):
        """Malformed env var keys are excluded from the override list."""
        monkeypatch.setenv("CPOS___BAD", "value")
        cfg = _base_config()
        overrides = list_active_overrides(cfg)
        paths = [o[0] for o in overrides]
        assert "CPOS___BAD" not in paths

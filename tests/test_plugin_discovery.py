"""Tests for entry-point plugin discovery via discover_plugins().

Covers:
- discover_plugins() returns list[PluginManifest] from installed entry-points
- Invalid or missing manifest dicts are skipped with a warning log
- PluginManifest validates name, version, agent_class as required strings
- Custom group parameter is forwarded to entry_points()
"""

import logging
import sys
import types
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

_src = str(Path(__file__).resolve().parent.parent / "src")
if _src not in sys.path:
    sys.path.insert(0, _src)

from crazypumpkin.framework.models import PluginManifest
from crazypumpkin.framework.plugin_loader import ENTRY_POINT_GROUP, discover_plugins


# -- helpers ----------------------------------------------------------------


def _make_ep(name: str, value: str):
    """Create a mock entry-point object."""
    ep = MagicMock()
    ep.name = name
    ep.value = value
    return ep


def _make_module(mod_name: str, manifest_dict):
    """Create a fake module with a plugin_manifest attribute."""
    mod = types.ModuleType(mod_name)
    mod.plugin_manifest = manifest_dict  # type: ignore[attr-defined]
    return mod


def _patch_eps(eps, *, version=(3, 12)):
    """Context manager that mocks sys.version_info and entry_points."""
    sys_patch = patch("crazypumpkin.framework.plugin_loader.sys")
    ep_patch = patch("importlib.metadata.entry_points", return_value=eps)

    class _Ctx:
        def __enter__(self):
            mock_sys = sys_patch.__enter__()
            mock_sys.version_info = version
            ep_patch.__enter__()
            return self

        def __exit__(self, *args):
            ep_patch.__exit__(*args)
            sys_patch.__exit__(*args)

    return _Ctx()


# -- discover_plugins returns list[PluginManifest] -------------------------


class TestDiscoverPluginsReturnsManifests:
    """discover_plugins() returns list[PluginManifest] from installed entry-points."""

    def test_returns_list_of_plugin_manifest(self):
        ep = _make_ep("my-plugin", "my_plugin.mod:Agent")
        mod = _make_module("my_plugin.mod", {
            "name": "my-plugin",
            "version": "1.0.0",
            "agent_class": "MyAgent",
        })

        with _patch_eps([ep]):
            with patch("importlib.import_module", return_value=mod):
                result = discover_plugins()

        assert isinstance(result, list)
        assert len(result) == 1
        assert isinstance(result[0], PluginManifest)

    def test_manifest_fields_populated_from_dict(self):
        ep = _make_ep("test-plugin", "test_mod:Cls")
        mod = _make_module("test_mod", {
            "name": "test-plugin",
            "version": "2.0.0",
            "agent_class": "TestAgent",
            "config_schema": {"key": "value"},
        })

        with _patch_eps([ep]):
            with patch("importlib.import_module", return_value=mod):
                result = discover_plugins()

        m = result[0]
        assert m.name == "test-plugin"
        assert m.version == "2.0.0"
        assert m.agent_class == "TestAgent"
        assert m.config_schema == {"key": "value"}
        assert m.entry_point == "test_mod:Cls"

    def test_config_schema_defaults_to_none(self):
        ep = _make_ep("simple", "simple_mod:Cls")
        mod = _make_module("simple_mod", {
            "name": "simple",
            "version": "1.0.0",
            "agent_class": "SimpleAgent",
        })

        with _patch_eps([ep]):
            with patch("importlib.import_module", return_value=mod):
                result = discover_plugins()

        assert result[0].config_schema is None

    def test_multiple_entry_points(self):
        ep1 = _make_ep("alpha", "alpha_mod:A")
        ep2 = _make_ep("beta", "beta_mod:B")
        mod1 = _make_module("alpha_mod", {
            "name": "alpha", "version": "1.0.0", "agent_class": "AlphaAgent",
        })
        mod2 = _make_module("beta_mod", {
            "name": "beta", "version": "2.0.0", "agent_class": "BetaAgent",
        })

        def _import(name):
            return {"alpha_mod": mod1, "beta_mod": mod2}[name]

        with _patch_eps([ep1, ep2]):
            with patch("importlib.import_module", side_effect=_import):
                result = discover_plugins()

        assert len(result) == 2
        names = [m.name for m in result]
        assert "alpha" in names
        assert "beta" in names

    def test_empty_entry_points_returns_empty_list(self):
        with _patch_eps([]):
            result = discover_plugins()
        assert result == []

    def test_uses_default_group(self):
        """discover_plugins() defaults to the crazypumpkin.plugins group."""
        assert ENTRY_POINT_GROUP == "crazypumpkin.plugins"

        with _patch_eps([]):
            result = discover_plugins()
        assert result == []

    def test_custom_group_parameter(self):
        ep = _make_ep("custom", "custom_mod:Cls")
        mod = _make_module("custom_mod", {
            "name": "custom", "version": "1.0.0", "agent_class": "CustomAgent",
        })

        with patch("crazypumpkin.framework.plugin_loader.sys") as mock_sys:
            mock_sys.version_info = (3, 12)
            with patch("importlib.metadata.entry_points", return_value=[ep]) as mock_eps:
                with patch("importlib.import_module", return_value=mod):
                    result = discover_plugins(group="my.custom.group")

        mock_eps.assert_called_once_with(group="my.custom.group")
        assert len(result) == 1
        assert result[0].name == "custom"


# -- Invalid / missing manifest dicts are skipped with warning -------------


class TestDiscoverPluginsSkipsInvalid:
    """Invalid or missing manifest dicts are skipped with a warning log."""

    def test_skips_module_without_plugin_manifest(self, caplog):
        ep = _make_ep("no-manifest", "no_manifest_mod:Cls")
        mod = types.ModuleType("no_manifest_mod")
        # No plugin_manifest attribute

        with _patch_eps([ep]):
            with patch("importlib.import_module", return_value=mod):
                with caplog.at_level(logging.WARNING, logger="crazypumpkin.plugin_loader"):
                    result = discover_plugins()

        assert result == []
        assert any("no-manifest" in r.message and "plugin_manifest" in r.message
                    for r in caplog.records)

    def test_skips_non_dict_plugin_manifest(self, caplog):
        ep = _make_ep("not-dict", "not_dict_mod:Cls")
        mod = _make_module("not_dict_mod", "not a dict")

        with _patch_eps([ep]):
            with patch("importlib.import_module", return_value=mod):
                with caplog.at_level(logging.WARNING, logger="crazypumpkin.plugin_loader"):
                    result = discover_plugins()

        assert result == []
        assert any("not-dict" in r.message for r in caplog.records)

    def test_skips_dict_missing_name_key(self, caplog):
        ep = _make_ep("no-name", "no_name_mod:Cls")
        mod = _make_module("no_name_mod", {
            "version": "1.0.0", "agent_class": "Agent",
        })

        with _patch_eps([ep]):
            with patch("importlib.import_module", return_value=mod):
                with caplog.at_level(logging.WARNING, logger="crazypumpkin.plugin_loader"):
                    result = discover_plugins()

        assert result == []
        assert any("no-name" in r.message for r in caplog.records)

    def test_skips_dict_missing_version_key(self, caplog):
        ep = _make_ep("no-ver", "no_ver_mod:Cls")
        mod = _make_module("no_ver_mod", {
            "name": "no-ver", "agent_class": "Agent",
        })

        with _patch_eps([ep]):
            with patch("importlib.import_module", return_value=mod):
                with caplog.at_level(logging.WARNING, logger="crazypumpkin.plugin_loader"):
                    result = discover_plugins()

        assert result == []
        assert any("no-ver" in r.message for r in caplog.records)

    def test_skips_dict_missing_agent_class_key(self, caplog):
        ep = _make_ep("no-ac", "no_ac_mod:Cls")
        mod = _make_module("no_ac_mod", {
            "name": "no-ac", "version": "1.0.0",
        })

        with _patch_eps([ep]):
            with patch("importlib.import_module", return_value=mod):
                with caplog.at_level(logging.WARNING, logger="crazypumpkin.plugin_loader"):
                    result = discover_plugins()

        assert result == []
        assert any("no-ac" in r.message for r in caplog.records)

    def test_skips_import_failure(self, caplog):
        ep = _make_ep("bad-import", "bad_import_mod:Cls")

        with _patch_eps([ep]):
            with patch("importlib.import_module", side_effect=ImportError("no such module")):
                with caplog.at_level(logging.WARNING, logger="crazypumpkin.plugin_loader"):
                    result = discover_plugins()

        assert result == []
        assert any("bad-import" in r.message for r in caplog.records)

    def test_does_not_raise_on_invalid_manifest(self):
        """Invalid manifests produce warnings, never exceptions."""
        ep = _make_ep("bad", "bad_mod:Cls")
        mod = _make_module("bad_mod", {"wrong": "keys"})

        with _patch_eps([ep]):
            with patch("importlib.import_module", return_value=mod):
                # Should NOT raise
                result = discover_plugins()

        assert result == []

    def test_valid_plugins_returned_despite_invalid_ones(self, caplog):
        ep_good = _make_ep("good", "good_mod:Cls")
        ep_bad = _make_ep("bad", "bad_mod:Cls")

        good_mod = _make_module("good_mod", {
            "name": "good", "version": "1.0.0", "agent_class": "GoodAgent",
        })
        bad_mod = _make_module("bad_mod", {"incomplete": True})

        def _import(name):
            return {"good_mod": good_mod, "bad_mod": bad_mod}[name]

        with _patch_eps([ep_good, ep_bad]):
            with patch("importlib.import_module", side_effect=_import):
                with caplog.at_level(logging.WARNING, logger="crazypumpkin.plugin_loader"):
                    result = discover_plugins()

        assert len(result) == 1
        assert result[0].name == "good"


# -- PluginManifest validates required string fields -------------------------


class TestPluginManifestValidation:
    """PluginManifest model validates name, version, agent_class as required strings."""

    def test_name_is_required_string(self):
        m = PluginManifest(name="test", version="1.0", agent_class="A")
        assert isinstance(m.name, str)
        assert m.name == "test"

    def test_version_is_required_string(self):
        m = PluginManifest(name="test", version="2.0", agent_class="A")
        assert isinstance(m.version, str)
        assert m.version == "2.0"

    def test_agent_class_is_required_string(self):
        m = PluginManifest(name="test", version="1.0", agent_class="MyAgent")
        assert isinstance(m.agent_class, str)
        assert m.agent_class == "MyAgent"

    def test_discover_rejects_manifest_without_required_name(self, caplog):
        """discover_plugins skips entry-points whose dict lacks 'name'."""
        ep = _make_ep("ep", "mod:C")
        mod = _make_module("mod", {"version": "1.0", "agent_class": "A"})

        with _patch_eps([ep]):
            with patch("importlib.import_module", return_value=mod):
                with caplog.at_level(logging.WARNING):
                    result = discover_plugins()

        assert result == []

    def test_discover_rejects_manifest_without_required_version(self, caplog):
        """discover_plugins skips entry-points whose dict lacks 'version'."""
        ep = _make_ep("ep", "mod:C")
        mod = _make_module("mod", {"name": "x", "agent_class": "A"})

        with _patch_eps([ep]):
            with patch("importlib.import_module", return_value=mod):
                with caplog.at_level(logging.WARNING):
                    result = discover_plugins()

        assert result == []

    def test_discover_rejects_manifest_without_required_agent_class(self, caplog):
        """discover_plugins skips entry-points whose dict lacks 'agent_class'."""
        ep = _make_ep("ep", "mod:C")
        mod = _make_module("mod", {"name": "x", "version": "1.0"})

        with _patch_eps([ep]):
            with patch("importlib.import_module", return_value=mod):
                with caplog.at_level(logging.WARNING):
                    result = discover_plugins()

        assert result == []

    def test_all_three_required_fields_present_succeeds(self):
        ep = _make_ep("ok", "ok_mod:C")
        mod = _make_module("ok_mod", {
            "name": "ok", "version": "1.0", "agent_class": "OkAgent",
        })

        with _patch_eps([ep]):
            with patch("importlib.import_module", return_value=mod):
                result = discover_plugins()

        assert len(result) == 1
        assert result[0].name == "ok"
        assert result[0].version == "1.0"
        assert result[0].agent_class == "OkAgent"

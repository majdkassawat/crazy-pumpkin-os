"""Unit tests for crazypumpkin.framework.plugin_loader.

Tests cover:
- PluginManifest creation and field defaults
- validate_plugin rejecting invalid manifests
- discover_plugins finding plugins from mocked entry-points and local directories
- load_plugin successfully loading a valid plugin class
- sandbox wrapper catching exceptions from faulty plugins
- load_plugin handling missing/broken entry-points gracefully
"""

import importlib
import logging
import sys
import types
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

_src = str(Path(__file__).resolve().parent.parent / "src")
if _src not in sys.path:
    sys.path.insert(0, _src)

_loader_mod = importlib.import_module("crazypumpkin.framework.plugin_loader")
_models_mod = importlib.import_module("crazypumpkin.framework.models")

PluginManifest = _models_mod.PluginManifest
discover_plugins = _loader_mod.discover_plugins
validate_plugin = _loader_mod.validate_plugin
load_plugin = _loader_mod.load_plugin
_sandbox_call = _loader_mod._sandbox_call
ENTRY_POINT_GROUP = _loader_mod.ENTRY_POINT_GROUP


# -- PluginManifest creation ---------------------------------------------------


class TestPluginManifestCreation:
    """PluginManifest dataclass creation and defaults."""

    def test_manifest_with_all_fields(self):
        m = PluginManifest(
            name="my-plugin",
            version="1.0.0",
            description="A test plugin",
            entry_point="my_plugin.mod:MyClass",
            plugin_type="agent",
            min_framework_version="0.1.0",
            permissions=["read", "write"],
        )
        assert m.name == "my-plugin"
        assert m.version == "1.0.0"
        assert m.description == "A test plugin"
        assert m.entry_point == "my_plugin.mod:MyClass"
        assert m.plugin_type == "agent"
        assert m.min_framework_version == "0.1.0"
        assert m.permissions == ["read", "write"]

    def test_manifest_defaults(self):
        m = PluginManifest()
        assert m.name == ""
        assert m.version == ""
        assert m.description == ""
        assert m.entry_point == ""
        assert m.plugin_type == ""
        assert m.min_framework_version == ""
        assert m.permissions == []

    def test_manifest_partial_fields(self):
        m = PluginManifest(name="partial", entry_point="some.mod", plugin_type="provider")
        assert m.name == "partial"
        assert m.version == ""
        assert m.entry_point == "some.mod"
        assert m.plugin_type == "provider"

    def test_manifest_permissions_default_is_independent(self):
        m1 = PluginManifest()
        m2 = PluginManifest()
        m1.permissions.append("x")
        assert m2.permissions == []


# -- validate_plugin -----------------------------------------------------------


class TestValidatePlugin:
    """validate_plugin rejects invalid manifests."""

    def test_valid_manifest_no_errors(self):
        m = PluginManifest(
            name="good",
            version="1.0.0",
            entry_point="pkg.mod:Cls",
            plugin_type="agent",
        )
        assert validate_plugin(m) == []

    def test_missing_name(self):
        m = PluginManifest(version="1.0.0", entry_point="pkg:Cls", plugin_type="agent")
        errors = validate_plugin(m)
        assert any("name" in e.lower() for e in errors)

    def test_missing_version(self):
        m = PluginManifest(name="x", entry_point="pkg:Cls", plugin_type="agent")
        errors = validate_plugin(m)
        assert any("version" in e.lower() for e in errors)

    def test_missing_entry_point(self):
        m = PluginManifest(name="x", version="1.0.0", plugin_type="agent")
        errors = validate_plugin(m)
        assert any("entry_point" in e.lower() for e in errors)

    def test_missing_plugin_type(self):
        m = PluginManifest(name="x", version="1.0.0", entry_point="pkg:Cls")
        errors = validate_plugin(m)
        assert any("plugin_type" in e.lower() for e in errors)

    def test_invalid_plugin_type(self):
        m = PluginManifest(
            name="x", version="1.0.0", entry_point="pkg:Cls", plugin_type="unknown"
        )
        errors = validate_plugin(m)
        assert any("invalid plugin_type" in e.lower() for e in errors)

    def test_plugin_type_agent_accepted(self):
        m = PluginManifest(
            name="x", version="1.0.0", entry_point="pkg:Cls", plugin_type="agent"
        )
        errors = validate_plugin(m)
        assert not any("plugin_type" in e.lower() for e in errors)

    def test_plugin_type_provider_accepted(self):
        m = PluginManifest(
            name="x", version="1.0.0", entry_point="pkg:Cls", plugin_type="provider"
        )
        errors = validate_plugin(m)
        assert not any("plugin_type" in e.lower() for e in errors)

    def test_min_framework_version_too_high(self):
        m = PluginManifest(
            name="x",
            version="1.0.0",
            entry_point="pkg:Cls",
            plugin_type="agent",
            min_framework_version="99.0.0",
        )
        errors = validate_plugin(m)
        assert any("framework" in e.lower() for e in errors)

    def test_min_framework_version_satisfied(self):
        m = PluginManifest(
            name="x",
            version="1.0.0",
            entry_point="pkg:Cls",
            plugin_type="agent",
            min_framework_version="0.0.1",
        )
        errors = validate_plugin(m)
        assert not any("framework" in e.lower() for e in errors)


# -- discover_plugins (entry-points) -------------------------------------------


class TestDiscoverEntryPoints:
    """discover_plugins finds entry-point plugins via mocked importlib.metadata."""

    def _make_ep(self, name: str, value: str):
        ep = MagicMock()
        ep.name = name
        ep.value = value
        return ep

    def test_discovers_entry_point_plugins(self, tmp_path):
        eps = [
            self._make_ep("myplugin", "myplugin.core:Agent"),
            self._make_ep("other", "other.mod:Plugin"),
        ]
        empty_dir = tmp_path / "empty_plugins"
        empty_dir.mkdir()

        with patch(
            "crazypumpkin.framework.plugin_loader.sys"
        ) as mock_sys:
            mock_sys.version_info = (3, 12)
            with patch(
                "importlib.metadata.entry_points", return_value=eps
            ):
                result = discover_plugins(plugins_dir=empty_dir)

        names = [m.name for m in result]
        assert "myplugin" in names
        assert "other" in names

    def test_no_entry_points(self, tmp_path):
        empty_dir = tmp_path / "empty_plugins"
        empty_dir.mkdir()

        with patch(
            "crazypumpkin.framework.plugin_loader.sys"
        ) as mock_sys:
            mock_sys.version_info = (3, 12)
            with patch(
                "importlib.metadata.entry_points", return_value=[]
            ):
                result = discover_plugins(plugins_dir=empty_dir)

        assert result == []


# -- discover_plugins (local directory) ----------------------------------------


class TestDiscoverLocalDirectory:
    """discover_plugins finds plugins in a local directory with .py files."""

    def test_discovers_py_files(self, tmp_path):
        plugins_dir = tmp_path / "plugins"
        plugins_dir.mkdir()
        (plugins_dir / "alpha_plugin.py").write_text("class Plugin: pass")
        (plugins_dir / "beta_plugin.py").write_text("class Plugin: pass")
        (plugins_dir / "__init__.py").write_text("")
        (plugins_dir / "readme.txt").write_text("not a plugin")

        with patch(
            "crazypumpkin.framework.plugin_loader.sys"
        ) as mock_sys:
            mock_sys.version_info = (3, 12)
            with patch(
                "importlib.metadata.entry_points", return_value=[]
            ):
                result = discover_plugins(plugins_dir=plugins_dir)

        names = [m.name for m in result]
        assert "alpha_plugin" in names
        assert "beta_plugin" in names
        assert "__init__" not in names
        assert "readme" not in names

    def test_empty_directory(self, tmp_path):
        plugins_dir = tmp_path / "plugins"
        plugins_dir.mkdir()

        with patch(
            "crazypumpkin.framework.plugin_loader.sys"
        ) as mock_sys:
            mock_sys.version_info = (3, 12)
            with patch(
                "importlib.metadata.entry_points", return_value=[]
            ):
                result = discover_plugins(plugins_dir=plugins_dir)

        assert result == []

    def test_nonexistent_directory(self, tmp_path):
        plugins_dir = tmp_path / "no_such_dir"

        with patch(
            "crazypumpkin.framework.plugin_loader.sys"
        ) as mock_sys:
            mock_sys.version_info = (3, 12)
            with patch(
                "importlib.metadata.entry_points", return_value=[]
            ):
                result = discover_plugins(plugins_dir=plugins_dir)

        assert result == []


# -- load_plugin ---------------------------------------------------------------


class TestLoadPlugin:
    """load_plugin imports and instantiates plugins."""

    def test_load_valid_plugin_with_attribute(self):
        class FakePlugin:
            pass

        fake_mod = types.ModuleType("fake_plugin_mod")
        fake_mod.MyPlugin = FakePlugin

        m = PluginManifest(
            name="good",
            version="1.0.0",
            entry_point="fake_plugin_mod:MyPlugin",
            plugin_type="agent",
        )

        with patch("importlib.import_module", return_value=fake_mod):
            result = load_plugin(m)

        assert isinstance(result, FakePlugin)

    def test_load_valid_plugin_default_class(self):
        class Plugin:
            pass

        fake_mod = types.ModuleType("fake_plugin_mod2")
        fake_mod.Plugin = Plugin

        m = PluginManifest(
            name="default-cls",
            version="1.0.0",
            entry_point="fake_plugin_mod2",
            plugin_type="agent",
        )

        with patch("importlib.import_module", return_value=fake_mod):
            result = load_plugin(m)

        assert isinstance(result, Plugin)

    def test_load_plugin_import_error(self, caplog):
        m = PluginManifest(
            name="missing",
            version="1.0.0",
            entry_point="nonexistent.module:Cls",
            plugin_type="agent",
        )

        with patch(
            "importlib.import_module",
            side_effect=ImportError("No module named 'nonexistent.module'"),
        ):
            with caplog.at_level(logging.ERROR, logger="crazypumpkin.plugin_loader"):
                result = load_plugin(m)

        assert result is None
        assert any("import failed" in r.message.lower() for r in caplog.records)

    def test_load_plugin_no_plugin_class_no_attr(self, caplog):
        fake_mod = types.ModuleType("no_plugin_cls")

        m = PluginManifest(
            name="noplugin",
            version="1.0.0",
            entry_point="no_plugin_cls",
            plugin_type="agent",
        )

        with patch("importlib.import_module", return_value=fake_mod):
            with caplog.at_level(logging.ERROR, logger="crazypumpkin.plugin_loader"):
                result = load_plugin(m)

        assert result is None
        assert any("no 'plugin' class" in r.message.lower() for r in caplog.records)

    def test_load_plugin_rejects_invalid_manifest(self):
        m = PluginManifest(name="", entry_point="mod:Cls", plugin_type="agent")
        result = load_plugin(m)
        assert result is None


# -- sandbox wrapper -----------------------------------------------------------


class TestSandboxWrapper:
    """_sandbox_call catches exceptions from faulty plugins."""

    def test_sandbox_returns_instance_on_success(self):
        class GoodPlugin:
            pass

        m = PluginManifest(name="good", plugin_type="agent")
        result = _sandbox_call(m, GoodPlugin)
        assert isinstance(result, GoodPlugin)

    def test_sandbox_catches_exception(self, caplog):
        class BadPlugin:
            def __init__(self):
                raise RuntimeError("Plugin init exploded")

        m = PluginManifest(name="bad", plugin_type="agent")

        with caplog.at_level(logging.ERROR, logger="crazypumpkin.plugin_loader"):
            result = _sandbox_call(m, BadPlugin)

        assert result is None
        assert any("sandboxed" in r.message.lower() for r in caplog.records)

    def test_sandbox_does_not_propagate(self):
        class CrashPlugin:
            def __init__(self):
                raise ValueError("kaboom")

        m = PluginManifest(name="crash", plugin_type="agent")
        # Should NOT raise
        result = _sandbox_call(m, CrashPlugin)
        assert result is None

    def test_sandbox_catches_type_error(self, caplog):
        class NeedsArgs:
            def __init__(self, required_arg):
                pass

        m = PluginManifest(name="needsargs", plugin_type="agent")

        with caplog.at_level(logging.ERROR, logger="crazypumpkin.plugin_loader"):
            result = _sandbox_call(m, NeedsArgs)

        assert result is None
        assert any("sandboxed" in r.message.lower() for r in caplog.records)

    def test_load_plugin_with_sandbox_catching_init_error(self, caplog):
        """End-to-end: load_plugin uses sandbox to catch __init__ errors."""

        class ExplodingPlugin:
            def __init__(self):
                raise RuntimeError("boom")

        fake_mod = types.ModuleType("exploding_mod")
        fake_mod.Plugin = ExplodingPlugin

        m = PluginManifest(
            name="exploding",
            version="1.0.0",
            entry_point="exploding_mod",
            plugin_type="agent",
        )

        with patch("importlib.import_module", return_value=fake_mod):
            with caplog.at_level(logging.ERROR, logger="crazypumpkin.plugin_loader"):
                result = load_plugin(m)

        assert result is None
        assert any("sandboxed" in r.message.lower() for r in caplog.records)

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
check_requires = _loader_mod.check_requires
_parse_dependency_spec = _loader_mod._parse_dependency_spec
_version_satisfies = _loader_mod._version_satisfies
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


# -- _parse_dependency_spec ----------------------------------------------------


class TestParseDependencySpec:
    """_parse_dependency_spec parses dependency specification strings."""

    def test_name_only(self):
        name, constraints = _parse_dependency_spec("my-plugin")
        assert name == "my-plugin"
        assert constraints == []

    def test_single_gte_constraint(self):
        name, constraints = _parse_dependency_spec("auth-plugin>=1.0.0")
        assert name == "auth-plugin"
        assert constraints == [(">=", "1.0.0")]

    def test_multiple_constraints(self):
        name, constraints = _parse_dependency_spec("db-plugin>=1.0,<2.0")
        assert name == "db-plugin"
        assert constraints == [(">=", "1.0"), ("<", "2.0")]

    def test_exact_version(self):
        name, constraints = _parse_dependency_spec("core==3.2.1")
        assert name == "core"
        assert constraints == [("==", "3.2.1")]

    def test_not_equal(self):
        name, constraints = _parse_dependency_spec("buggy!=1.0.0")
        assert name == "buggy"
        assert constraints == [("!=", "1.0.0")]

    def test_whitespace_handling(self):
        name, constraints = _parse_dependency_spec("  plugin >= 1.0 , < 2.0  ")
        assert name == "plugin"
        assert constraints == [(">=", "1.0"), ("<", "2.0")]


# -- _version_satisfies -------------------------------------------------------


class TestVersionSatisfies:
    """_version_satisfies checks version constraints."""

    def test_gte_satisfied(self):
        assert _version_satisfies("1.2.0", ">=", "1.0.0") is True

    def test_gte_equal(self):
        assert _version_satisfies("1.0.0", ">=", "1.0.0") is True

    def test_gte_not_satisfied(self):
        assert _version_satisfies("0.9.0", ">=", "1.0.0") is False

    def test_lt_satisfied(self):
        assert _version_satisfies("1.9.0", "<", "2.0.0") is True

    def test_lt_not_satisfied(self):
        assert _version_satisfies("2.0.0", "<", "2.0.0") is False

    def test_gt_satisfied(self):
        assert _version_satisfies("2.0.1", ">", "2.0.0") is True

    def test_gt_not_satisfied(self):
        assert _version_satisfies("2.0.0", ">", "2.0.0") is False

    def test_lte_satisfied(self):
        assert _version_satisfies("2.0.0", "<=", "2.0.0") is True

    def test_eq_satisfied(self):
        assert _version_satisfies("1.0.0", "==", "1.0.0") is True

    def test_eq_not_satisfied(self):
        assert _version_satisfies("1.0.1", "==", "1.0.0") is False

    def test_ne_satisfied(self):
        assert _version_satisfies("1.0.1", "!=", "1.0.0") is True

    def test_ne_not_satisfied(self):
        assert _version_satisfies("1.0.0", "!=", "1.0.0") is False

    def test_two_part_version(self):
        assert _version_satisfies("1.5", ">=", "1.0") is True

    def test_mismatched_version_parts(self):
        assert _version_satisfies("1.0", ">=", "1.0.0") is True


# -- check_requires -----------------------------------------------------------


class TestCheckRequires:
    """check_requires validates plugin dependency requirements."""

    def _base_manifest(self, **kwargs):
        defaults = dict(
            name="test-plugin",
            version="1.0.0",
            entry_point="pkg:Cls",
            plugin_type="agent",
        )
        defaults.update(kwargs)
        return PluginManifest(**defaults)

    def test_no_requires_returns_empty(self):
        m = self._base_manifest()
        assert check_requires(m) == []

    def test_empty_requires_returns_empty(self):
        m = self._base_manifest(requires=[])
        assert check_requires(m) == []

    def test_plugin_dependency_satisfied(self):
        m = self._base_manifest(requires=["auth-plugin>=1.0.0"])
        errors = check_requires(m, available_plugins={"auth-plugin": "1.2.0"})
        assert errors == []

    def test_plugin_dependency_missing(self):
        m = self._base_manifest(requires=["auth-plugin>=1.0.0"])
        errors = check_requires(m, available_plugins={})
        assert len(errors) == 1
        assert "auth-plugin" in errors[0]
        assert "not available" in errors[0]

    def test_plugin_dependency_version_too_low(self):
        m = self._base_manifest(requires=["auth-plugin>=2.0.0"])
        errors = check_requires(m, available_plugins={"auth-plugin": "1.5.0"})
        assert len(errors) == 1
        assert "does not satisfy" in errors[0]

    def test_plugin_dependency_version_range(self):
        m = self._base_manifest(requires=["db-plugin>=1.0,<2.0"])
        errors = check_requires(m, available_plugins={"db-plugin": "1.5.0"})
        assert errors == []

    def test_plugin_dependency_version_range_too_high(self):
        m = self._base_manifest(requires=["db-plugin>=1.0,<2.0"])
        errors = check_requires(m, available_plugins={"db-plugin": "2.0.0"})
        assert len(errors) == 1
        assert "<2.0" in errors[0]

    def test_framework_dependency_satisfied(self):
        m = self._base_manifest(requires=["crazypumpkin>=0.1.0"])
        errors = check_requires(m, framework_version="0.1.0")
        assert errors == []

    def test_framework_dependency_not_satisfied(self):
        m = self._base_manifest(requires=["crazypumpkin>=1.0.0"])
        errors = check_requires(m, framework_version="0.1.0")
        assert len(errors) == 1
        assert "framework version" in errors[0].lower()

    def test_cp_os_alias_for_framework(self):
        m = self._base_manifest(requires=["cp-os>=0.1.0"])
        errors = check_requires(m, framework_version="0.1.0")
        assert errors == []

    def test_framework_range_constraint(self):
        m = self._base_manifest(requires=["crazypumpkin>=0.1.0,<1.0.0"])
        errors = check_requires(m, framework_version="0.5.0")
        assert errors == []

    def test_framework_range_constraint_exceeded(self):
        m = self._base_manifest(requires=["crazypumpkin>=0.1.0,<1.0.0"])
        errors = check_requires(m, framework_version="1.0.0")
        assert len(errors) == 1

    def test_multiple_dependencies(self):
        m = self._base_manifest(requires=["auth>=1.0", "db>=2.0", "crazypumpkin>=0.1.0"])
        errors = check_requires(
            m,
            available_plugins={"auth": "1.5.0", "db": "2.1.0"},
            framework_version="0.1.0",
        )
        assert errors == []

    def test_multiple_dependencies_some_missing(self):
        m = self._base_manifest(requires=["auth>=1.0", "db>=2.0"])
        errors = check_requires(m, available_plugins={"auth": "1.5.0"})
        assert len(errors) == 1
        assert "db" in errors[0]

    def test_name_only_dependency_present(self):
        m = self._base_manifest(requires=["some-plugin"])
        errors = check_requires(m, available_plugins={"some-plugin": "0.0.1"})
        assert errors == []

    def test_name_only_dependency_missing(self):
        m = self._base_manifest(requires=["some-plugin"])
        errors = check_requires(m, available_plugins={})
        assert len(errors) == 1
        assert "not available" in errors[0]

    def test_defaults_to_framework_version_constant(self):
        m = self._base_manifest(requires=["crazypumpkin>=99.0.0"])
        errors = check_requires(m)
        assert len(errors) == 1


# -- load_plugin with dependency checks ----------------------------------------


class TestLoadPluginWithDependencies:
    """load_plugin rejects plugins whose dependencies are not met."""

    def test_load_fails_missing_dependency(self, caplog):
        m = PluginManifest(
            name="needs-auth",
            version="1.0.0",
            entry_point="pkg:Cls",
            plugin_type="agent",
            requires=["auth-plugin>=1.0.0"],
        )
        with caplog.at_level(logging.ERROR, logger="crazypumpkin.plugin_loader"):
            result = load_plugin(m, available_plugins={})
        assert result is None
        assert any("dependency check failed" in r.message.lower() for r in caplog.records)

    def test_load_fails_version_constraint(self, caplog):
        m = PluginManifest(
            name="needs-new-auth",
            version="1.0.0",
            entry_point="pkg:Cls",
            plugin_type="agent",
            requires=["auth-plugin>=2.0.0"],
        )
        with caplog.at_level(logging.ERROR, logger="crazypumpkin.plugin_loader"):
            result = load_plugin(m, available_plugins={"auth-plugin": "1.0.0"})
        assert result is None
        assert any("dependency check failed" in r.message.lower() for r in caplog.records)

    def test_load_succeeds_with_satisfied_deps(self):
        class FakePlugin:
            pass

        fake_mod = types.ModuleType("dep_ok_mod")
        fake_mod.MyPlugin = FakePlugin

        m = PluginManifest(
            name="dep-ok",
            version="1.0.0",
            entry_point="dep_ok_mod:MyPlugin",
            plugin_type="agent",
            requires=["auth>=1.0"],
        )

        with patch("importlib.import_module", return_value=fake_mod):
            result = load_plugin(m, available_plugins={"auth": "1.5.0"})

        assert isinstance(result, FakePlugin)

    def test_load_succeeds_no_requires(self):
        class FakePlugin:
            pass

        fake_mod = types.ModuleType("no_req_mod")
        fake_mod.MyPlugin = FakePlugin

        m = PluginManifest(
            name="no-req",
            version="1.0.0",
            entry_point="no_req_mod:MyPlugin",
            plugin_type="agent",
        )

        with patch("importlib.import_module", return_value=fake_mod):
            result = load_plugin(m)

        assert isinstance(result, FakePlugin)

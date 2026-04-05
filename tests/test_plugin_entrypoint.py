"""Tests for entry-point plugin discovery in plugin_loader.

Covers:
- discover_entry_point_plugins() returns PluginManifest objects for installed entry points
- Entry points whose module lacks plugin_manifest() are skipped with a warning
- Entry points whose plugin_manifest() raises are skipped with a warning
- load_plugins() merges entry-point and directory-based plugins without duplicates
- Empty entry-point group returns an empty list
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
from crazypumpkin.framework.plugin_loader import (
    ENTRY_POINT_GROUP,
    discover_entry_point_plugins,
    load_plugins,
)


# -- helpers ----------------------------------------------------------------


def _make_ep(name: str, value: str):
    """Create a mock entry-point object."""
    ep = MagicMock()
    ep.name = name
    ep.value = value
    return ep


def _make_module_with_manifest(mod_name: str, manifest: PluginManifest):
    """Create a fake module that has a plugin_manifest() callable."""
    mod = types.ModuleType(mod_name)
    mod.plugin_manifest = lambda: manifest  # type: ignore[attr-defined]
    return mod


# -- discover_entry_point_plugins -------------------------------------------


class TestDiscoverEntryPointPlugins:
    """discover_entry_point_plugins returns a list of PluginManifest objects."""

    @patch("crazypumpkin.framework.plugin_loader.sys")
    @patch("importlib.metadata.entry_points")
    def test_returns_manifests_for_valid_entry_points(self, mock_eps, mock_sys):
        mock_sys.version_info = (3, 12)

        manifest = PluginManifest(
            name="test-plugin",
            version="1.0.0",
            entry_point="test_plugin.core:Plugin",
            plugin_type="agent",
        )
        fake_mod = _make_module_with_manifest("test_plugin_mod", manifest)

        ep = _make_ep("test-plugin", "test_plugin_mod")
        mock_eps.return_value = [ep]

        with patch("importlib.import_module", return_value=fake_mod):
            result = discover_entry_point_plugins()

        assert len(result) == 1
        assert isinstance(result[0], PluginManifest)
        assert result[0].name == "test-plugin"
        assert result[0].version == "1.0.0"

    @patch("crazypumpkin.framework.plugin_loader.sys")
    @patch("importlib.metadata.entry_points")
    def test_multiple_entry_points(self, mock_eps, mock_sys):
        mock_sys.version_info = (3, 12)

        m1 = PluginManifest(name="alpha", version="1.0.0", entry_point="a:P", plugin_type="agent")
        m2 = PluginManifest(name="beta", version="2.0.0", entry_point="b:P", plugin_type="provider")

        mod1 = _make_module_with_manifest("alpha_mod", m1)
        mod2 = _make_module_with_manifest("beta_mod", m2)

        ep1 = _make_ep("alpha", "alpha_mod")
        ep2 = _make_ep("beta", "beta_mod")
        mock_eps.return_value = [ep1, ep2]

        def _import(name):
            return {"alpha_mod": mod1, "beta_mod": mod2}[name]

        with patch("importlib.import_module", side_effect=_import):
            result = discover_entry_point_plugins()

        assert len(result) == 2
        names = [m.name for m in result]
        assert "alpha" in names
        assert "beta" in names

    @patch("crazypumpkin.framework.plugin_loader.sys")
    @patch("importlib.metadata.entry_points")
    def test_skips_module_without_plugin_manifest(self, mock_eps, mock_sys, caplog):
        mock_sys.version_info = (3, 12)

        fake_mod = types.ModuleType("no_manifest_mod")
        # No plugin_manifest attribute on this module

        ep = _make_ep("bad-plugin", "no_manifest_mod")
        mock_eps.return_value = [ep]

        with patch("importlib.import_module", return_value=fake_mod):
            with caplog.at_level(logging.WARNING, logger="crazypumpkin.plugin_loader"):
                result = discover_entry_point_plugins()

        assert result == []
        assert any("plugin_manifest" in r.message for r in caplog.records)

    @patch("crazypumpkin.framework.plugin_loader.sys")
    @patch("importlib.metadata.entry_points")
    def test_skips_when_plugin_manifest_raises(self, mock_eps, mock_sys, caplog):
        mock_sys.version_info = (3, 12)

        fake_mod = types.ModuleType("raising_mod")
        fake_mod.plugin_manifest = MagicMock(  # type: ignore[attr-defined]
            side_effect=RuntimeError("boom"),
        )

        ep = _make_ep("raise-plugin", "raising_mod")
        mock_eps.return_value = [ep]

        with patch("importlib.import_module", return_value=fake_mod):
            with caplog.at_level(logging.WARNING, logger="crazypumpkin.plugin_loader"):
                result = discover_entry_point_plugins()

        assert result == []
        assert any("raise-plugin" in r.message for r in caplog.records)

    @patch("crazypumpkin.framework.plugin_loader.sys")
    @patch("importlib.metadata.entry_points")
    def test_returns_empty_when_no_entry_points(self, mock_eps, mock_sys):
        mock_sys.version_info = (3, 12)
        mock_eps.return_value = []

        result = discover_entry_point_plugins()
        assert result == []

    @patch("crazypumpkin.framework.plugin_loader.sys")
    @patch("importlib.metadata.entry_points")
    def test_skips_module_import_failure(self, mock_eps, mock_sys, caplog):
        mock_sys.version_info = (3, 12)

        ep = _make_ep("import-fail", "nonexistent_mod")
        mock_eps.return_value = [ep]

        with patch(
            "importlib.import_module",
            side_effect=ImportError("No module named 'nonexistent_mod'"),
        ):
            with caplog.at_level(logging.WARNING, logger="crazypumpkin.plugin_loader"):
                result = discover_entry_point_plugins()

        assert result == []
        assert any("import-fail" in r.message for r in caplog.records)

    @patch("crazypumpkin.framework.plugin_loader.sys")
    @patch("importlib.metadata.entry_points")
    def test_mixed_valid_and_invalid_entry_points(self, mock_eps, mock_sys, caplog):
        """Valid plugins are returned even when some entry points fail."""
        mock_sys.version_info = (3, 12)

        good_manifest = PluginManifest(
            name="good", version="1.0.0", entry_point="g:P", plugin_type="agent",
        )
        good_mod = _make_module_with_manifest("good_mod", good_manifest)
        bad_mod = types.ModuleType("bad_mod")  # no plugin_manifest

        ep_good = _make_ep("good", "good_mod")
        ep_bad = _make_ep("bad", "bad_mod")
        mock_eps.return_value = [ep_good, ep_bad]

        def _import(name):
            return {"good_mod": good_mod, "bad_mod": bad_mod}[name]

        with patch("importlib.import_module", side_effect=_import):
            with caplog.at_level(logging.WARNING, logger="crazypumpkin.plugin_loader"):
                result = discover_entry_point_plugins()

        assert len(result) == 1
        assert result[0].name == "good"


# -- load_plugins (merge behaviour) -----------------------------------------


class TestLoadPluginsMerge:
    """load_plugins merges directory and entry-point plugins without duplicates."""

    @patch("crazypumpkin.framework.plugin_loader.discover_entry_point_plugins")
    @patch("crazypumpkin.framework.plugin_loader.discover_plugins")
    def test_merges_without_duplicates(self, mock_dir, mock_ep):
        dir_plugin = PluginManifest(
            name="shared", version="1.0.0", entry_point="d:C", plugin_type="agent",
        )
        ep_plugin = PluginManifest(
            name="shared", version="2.0.0", entry_point="e:C", plugin_type="agent",
        )
        ep_only = PluginManifest(
            name="ep-only", version="1.0.0", entry_point="e2:C", plugin_type="agent",
        )

        mock_dir.return_value = [dir_plugin]
        mock_ep.return_value = [ep_plugin, ep_only]

        result = load_plugins()

        names = [m.name for m in result]
        assert names.count("shared") == 1
        # Directory plugin should win (loaded first)
        shared = [m for m in result if m.name == "shared"][0]
        assert shared.version == "1.0.0"
        assert "ep-only" in names

    @patch("crazypumpkin.framework.plugin_loader.discover_entry_point_plugins")
    @patch("crazypumpkin.framework.plugin_loader.discover_plugins")
    def test_directory_plugins_come_first(self, mock_dir, mock_ep):
        dir_p = PluginManifest(
            name="dir-plugin", version="1.0.0", entry_point="d:C", plugin_type="agent",
        )
        ep_p = PluginManifest(
            name="ep-plugin", version="1.0.0", entry_point="e:C", plugin_type="agent",
        )

        mock_dir.return_value = [dir_p]
        mock_ep.return_value = [ep_p]

        result = load_plugins()

        assert len(result) == 2
        assert result[0].name == "dir-plugin"
        assert result[1].name == "ep-plugin"

    @patch("crazypumpkin.framework.plugin_loader.discover_entry_point_plugins")
    @patch("crazypumpkin.framework.plugin_loader.discover_plugins")
    def test_empty_sources(self, mock_dir, mock_ep):
        mock_dir.return_value = []
        mock_ep.return_value = []

        result = load_plugins()
        assert result == []

    @patch("crazypumpkin.framework.plugin_loader.discover_entry_point_plugins")
    @patch("crazypumpkin.framework.plugin_loader.discover_plugins")
    def test_only_entry_point_plugins(self, mock_dir, mock_ep):
        mock_dir.return_value = []
        ep_p = PluginManifest(
            name="ep-only", version="1.0.0", entry_point="e:C", plugin_type="agent",
        )
        mock_ep.return_value = [ep_p]

        result = load_plugins()

        assert len(result) == 1
        assert result[0].name == "ep-only"

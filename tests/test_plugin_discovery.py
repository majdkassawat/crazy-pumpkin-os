"""Tests for entry_points plugin discovery in the framework plugin_loader."""

import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from crazypumpkin.framework.plugin_loader import discover_entry_point_plugins, get_plugin_info


# -- helpers ----------------------------------------------------------------


def _make_entry_point(name: str, value: str, version: str = "1.0.0",
                      dist_name: str = "unknown"):
    """Create a fake entry point object mimicking importlib.metadata.EntryPoint."""
    ep = MagicMock()
    ep.name = name
    ep.value = value
    ep.dist = MagicMock()
    ep.dist.metadata = {"Name": dist_name, "Version": version}
    return ep


# -- discover_entry_point_plugins -------------------------------------------


@patch("importlib.metadata.entry_points")
def test_discover_no_plugins(mock_ep):
    """discover_entry_point_plugins returns [] when no entry points are found."""
    if sys.version_info >= (3, 12):
        mock_ep.return_value = []
    else:
        all_eps = MagicMock()
        all_eps.get.return_value = []
        mock_ep.return_value = all_eps

    result = discover_entry_point_plugins()
    assert result == []


class TestDiscoverEntryPointPlugins:
    """Tests for discover_entry_point_plugins."""

    @patch("importlib.metadata.entry_points")
    def test_empty_entry_points_returns_empty_list(self, mock_ep):
        mock_ep.return_value = {}
        mock_ep.return_value = []
        # For Python < 3.12 path: entry_points() returns a dict-like
        mock_ep.return_value = MagicMock()
        mock_ep.return_value.get.return_value = []
        # For Python >= 3.12 path: entry_points(group=...) returns iterable
        if sys.version_info >= (3, 12):
            mock_ep.return_value = []
        else:
            all_eps = MagicMock()
            all_eps.get.return_value = []
            mock_ep.return_value = all_eps

        result = discover_entry_point_plugins()
        assert result == []

    @patch("importlib.metadata.entry_points")
    def test_returns_plugin_dict_from_mock_entry_point(self, mock_ep):
        """Verify discover returns correct dict for a single mocked EP."""
        ep = _make_entry_point("mock-plugin", "mock_module:MockClass",
                               version="1.0.0", dist_name="mock-dist")

        if sys.version_info >= (3, 12):
            mock_ep.return_value = [ep]
        else:
            all_eps = MagicMock()
            all_eps.get.return_value = [ep]
            mock_ep.return_value = all_eps

        result = discover_entry_point_plugins()

        assert len(result) == 1
        plugin = result[0]
        assert plugin["name"] == "mock-plugin"
        assert plugin["module"] == "mock_module"
        assert plugin["version"] == "1.0.0"
        assert plugin["status"] in ("loaded", "available")

    @patch("importlib.metadata.entry_points")
    def test_single_plugin_returns_correct_dict_structure(self, mock_ep):
        ep = _make_entry_point("my-plugin", "my_plugin.core:Plugin", "2.0.0")

        if sys.version_info >= (3, 12):
            mock_ep.return_value = [ep]
        else:
            all_eps = MagicMock()
            all_eps.get.return_value = [ep]
            mock_ep.return_value = all_eps

        with patch("crazypumpkin.framework.plugin_loader.importlib") as mock_importlib:
            mock_importlib.import_module.return_value = MagicMock()
            result = discover_entry_point_plugins()

        assert len(result) == 1
        plugin = result[0]
        # Validate dict key presence
        assert "name" in plugin
        assert "version" in plugin
        assert "module" in plugin
        assert "status" in plugin
        # Validate value types
        assert isinstance(plugin["name"], str)
        assert isinstance(plugin["version"], str)
        assert isinstance(plugin["module"], str)
        assert isinstance(plugin["status"], str)
        # Validate values
        assert plugin["name"] == "my-plugin"
        assert plugin["version"] == "2.0.0"
        assert plugin["module"] == "my_plugin.core"
        assert plugin["status"] == "loaded"

    @patch("importlib.metadata.entry_points")
    def test_discover_plugin_no_dist(self, mock_ep):
        """discover_entry_point_plugins handles entry points with dist=None."""
        ep = MagicMock()
        ep.name = "nodist-plugin"
        ep.value = "nodist_mod:Cls"
        ep.dist = None

        if sys.version_info >= (3, 12):
            mock_ep.return_value = [ep]
        else:
            all_eps = MagicMock()
            all_eps.get.return_value = [ep]
            mock_ep.return_value = all_eps

        with patch("crazypumpkin.framework.plugin_loader.importlib") as mock_importlib:
            mock_importlib.import_module.return_value = MagicMock()
            result = discover_entry_point_plugins()

        assert len(result) == 1
        plugin = result[0]
        assert plugin["name"] == "nodist-plugin"
        assert plugin["module"] == "nodist_mod"
        # With dist=None, version info is unavailable
        assert plugin["version"] == "unknown"
        assert plugin["status"] == "loaded"

    @patch("importlib.metadata.entry_points")
    def test_multiple_plugins_returns_all(self, mock_ep):
        ep1 = _make_entry_point("alpha", "alpha_mod:Plugin", "1.0.0")
        ep2 = _make_entry_point("beta", "beta_mod:Plugin", "2.0.0")
        ep3 = _make_entry_point("gamma", "gamma_mod:Plugin", "3.0.0")

        if sys.version_info >= (3, 12):
            mock_ep.return_value = [ep1, ep2, ep3]
        else:
            all_eps = MagicMock()
            all_eps.get.return_value = [ep1, ep2, ep3]
            mock_ep.return_value = all_eps

        with patch("crazypumpkin.framework.plugin_loader.importlib") as mock_importlib:
            mock_importlib.import_module.return_value = MagicMock()
            result = discover_entry_point_plugins()

        assert len(result) == 3
        names = [p["name"] for p in result]
        assert "alpha" in names
        assert "beta" in names
        assert "gamma" in names

        # All entries have correct structure
        for plugin in result:
            assert isinstance(plugin, dict)
            assert set(plugin.keys()) == {"name", "version", "module", "status"}
            for v in plugin.values():
                assert isinstance(v, str)


# -- get_plugin_info --------------------------------------------------------


class TestGetPluginInfo:
    """Tests for get_plugin_info."""

    @patch("crazypumpkin.framework.plugin_loader.discover_entry_point_plugins")
    def test_returns_none_for_unknown_name(self, mock_discover):
        mock_discover.return_value = [
            {"name": "alpha", "version": "1.0.0", "module": "alpha_mod", "status": "loaded"},
        ]
        result = get_plugin_info("nonexistent")
        assert result is None

    @patch("crazypumpkin.framework.plugin_loader.discover_entry_point_plugins")
    def test_returns_correct_dict_for_known_plugin(self, mock_discover):
        plugins = [
            {"name": "alpha", "version": "1.0.0", "module": "alpha_mod", "status": "loaded"},
            {"name": "beta", "version": "2.5.0", "module": "beta_mod", "status": "available"},
        ]
        mock_discover.return_value = plugins

        result = get_plugin_info("beta")
        assert result is not None
        assert isinstance(result, dict)
        assert result["name"] == "beta"
        assert result["version"] == "2.5.0"
        assert result["module"] == "beta_mod"
        assert result["status"] == "available"
        assert set(result.keys()) == {"name", "version", "module", "status"}

"""Tests for entry-point-based plugin discovery via PluginLoader.

Tests cover:
- Discovering valid entry-point plugins
- Handling broken entry points gracefully (ImportError logged as warning)
- Config plugins overriding entry-point plugins by name
- Empty entry-point group returning empty list
"""

import logging
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

_src = str(Path(__file__).resolve().parent.parent / "src")
if _src not in sys.path:
    sys.path.insert(0, _src)

from crazypumpkin.framework.plugin_loader import PluginLoader, ENTRY_POINT_GROUP
from crazypumpkin.framework.models import PluginManifest


def _make_entry_point(name, value, load_return=None, load_side_effect=None):
    """Create a mock entry point object."""
    ep = MagicMock()
    ep.name = name
    ep.value = value
    if load_side_effect is not None:
        ep.load.side_effect = load_side_effect
    elif load_return is not None:
        ep.load.return_value = load_return
    return ep


def _mock_entry_points(eps):
    """Return a side_effect function that works for both 3.12+ and older APIs."""
    def _side_effect(*args, **kwargs):
        if "group" in kwargs:
            # Python >= 3.12 API: entry_points(group=...)
            return eps
        # Python < 3.12 API: entry_points() -> dict
        return {ENTRY_POINT_GROUP: eps}
    return _side_effect


class TestDiscoverEntrypointPlugins:
    """Entry-point-based plugin discovery via PluginLoader."""

    def test_discover_valid_entrypoint(self):
        """Mock one valid entry point returning a PluginManifest dict,
        assert it appears in discover_entrypoint_plugins() result."""
        manifest_dict = {
            "name": "test-plugin",
            "version": "1.0.0",
            "entry_point": "test_plugin.core:Agent",
            "plugin_type": "agent",
        }
        ep = _make_entry_point(
            "test-plugin", "test_plugin.core:Agent", load_return=manifest_dict
        )

        with patch("importlib.metadata.entry_points", side_effect=_mock_entry_points([ep])):
            loader = PluginLoader()
            result = loader.discover_entrypoint_plugins()

        assert len(result) == 1
        assert result[0].name == "test-plugin"
        assert result[0].version == "1.0.0"
        assert result[0].entry_point == "test_plugin.core:Agent"
        assert result[0].plugin_type == "agent"

    def test_discover_broken_entrypoint(self, caplog):
        """Mock entry point that raises ImportError on load(),
        assert empty list returned and warning logged."""
        ep = _make_entry_point(
            "broken-plugin",
            "broken.module:Cls",
            load_side_effect=ImportError("No module named 'broken'"),
        )

        with patch("importlib.metadata.entry_points", side_effect=_mock_entry_points([ep])):
            loader = PluginLoader()
            with caplog.at_level(logging.WARNING):
                result = loader.discover_entrypoint_plugins()

        assert result == []
        warning_records = [
            r for r in caplog.records if r.levelno >= logging.WARNING
        ]
        assert len(warning_records) >= 1
        assert any("broken-plugin" in r.message for r in warning_records)

    def test_config_overrides_entrypoint(self):
        """Provide config plugin with same name as entry-point plugin,
        assert config version is used."""
        config_manifest = PluginManifest(
            name="my-plugin",
            version="2.0.0",
            entry_point="config_plugin.core:Agent",
            plugin_type="provider",
        )
        ep_dict = {
            "name": "my-plugin",
            "version": "1.0.0",
            "entry_point": "ep_plugin.core:Agent",
            "plugin_type": "agent",
        }
        ep = _make_entry_point(
            "my-plugin", "ep_plugin.core:Agent", load_return=ep_dict
        )

        with patch("importlib.metadata.entry_points", side_effect=_mock_entry_points([ep])):
            loader = PluginLoader(config_plugins=[config_manifest])
            result = loader.discover_entrypoint_plugins()

        assert len(result) == 1
        assert result[0].version == "2.0.0"
        assert result[0].entry_point == "config_plugin.core:Agent"
        assert result[0].plugin_type == "provider"
        # entry point load() should not have been called
        ep.load.assert_not_called()

    def test_no_entrypoints(self):
        """Mock empty entry points, assert empty list."""
        with patch("importlib.metadata.entry_points", side_effect=_mock_entry_points([])):
            loader = PluginLoader()
            result = loader.discover_entrypoint_plugins()

        assert result == []

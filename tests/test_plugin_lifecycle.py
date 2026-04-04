"""Tests for PluginLifecycleManager enable/disable operations."""

import logging
import sys
from datetime import datetime
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from crazypumpkin.framework.models import PluginManifest
from crazypumpkin.framework.plugin_lifecycle import PluginLifecycleManager

_DISCOVER = "crazypumpkin.framework.plugin_lifecycle.discover_plugins"


def _make_manifest(name="my-plugin", version="1.0.0", entry_point="pkg.mod:Cls",
                   plugin_type="agent"):
    return PluginManifest(
        name=name, version=version, entry_point=entry_point,
        plugin_type=plugin_type,
    )


class TestPluginLifecycleEnableDisable:
    """Unit tests for PluginLifecycleManager enable/disable operations."""

    def test_enable_plugin_success(self, tmp_path):
        """discover returns manifest; assert state has enabled=True and enabled_at set."""
        manifests = [_make_manifest(name="alpha")]
        state_path = tmp_path / "plugin_state.json"

        with patch(_DISCOVER, return_value=manifests):
            mgr = PluginLifecycleManager(state_path=state_path)
            mgr.enable_plugin("alpha")

        state = mgr._state["alpha"]
        assert state["enabled"] is True
        assert "enabled_at" in state
        # Verify enabled_at is a valid ISO datetime string
        dt = datetime.fromisoformat(state["enabled_at"])
        assert dt is not None

    def test_enable_plugin_not_found(self, tmp_path):
        """discover returns []; assert KeyError raised for unknown plugin."""
        state_path = tmp_path / "plugin_state.json"

        with patch(_DISCOVER, return_value=[]):
            mgr = PluginLifecycleManager(state_path=state_path)
            with pytest.raises(KeyError, match="missing-plugin"):
                mgr.enable_plugin("missing-plugin")

        # Plugin should not appear in state
        assert "missing-plugin" not in mgr._state

    def test_enable_plugin_validation_fails(self, tmp_path):
        """discover returns manifests that don't include the target; assert KeyError."""
        manifests = [_make_manifest(name="other-plugin")]
        state_path = tmp_path / "plugin_state.json"

        with patch(_DISCOVER, return_value=manifests):
            mgr = PluginLifecycleManager(state_path=state_path)
            with pytest.raises(KeyError, match="wanted-plugin"):
                mgr.enable_plugin("wanted-plugin")

        assert "wanted-plugin" not in mgr._state

    def test_disable_plugin_existing(self, tmp_path):
        """Enable then disable; assert state has enabled=False and disabled_at set."""
        manifests = [_make_manifest(name="beta")]
        state_path = tmp_path / "plugin_state.json"

        with patch(_DISCOVER, return_value=manifests):
            mgr = PluginLifecycleManager(state_path=state_path)
            mgr.enable_plugin("beta")

            # Verify enabled first
            assert mgr._state["beta"]["enabled"] is True
            assert "enabled_at" in mgr._state["beta"]

            mgr.disable_plugin("beta")

        state = mgr._state["beta"]
        assert state["enabled"] is False
        assert "disabled_at" in state
        dt = datetime.fromisoformat(state["disabled_at"])
        assert dt is not None

    def test_disable_plugin_nonexistent(self, tmp_path):
        """Plugin known but has no prior state; assert DISABLED after disable."""
        manifests = [_make_manifest(name="fresh")]
        state_path = tmp_path / "plugin_state.json"

        with patch(_DISCOVER, return_value=manifests):
            mgr = PluginLifecycleManager(state_path=state_path)
            # No prior enable — state doesn't exist yet
            assert "fresh" not in mgr._state

            mgr.disable_plugin("fresh")

        state = mgr._state["fresh"]
        assert state["enabled"] is False
        assert "disabled_at" in state

    def test_list_active(self, tmp_path):
        """get_status returns mix; assert only ENABLED ones filtered correctly."""
        manifests = [
            _make_manifest(name="enabled-one"),
            _make_manifest(name="disabled-one"),
            _make_manifest(name="default-one"),
        ]
        state_path = tmp_path / "plugin_state.json"

        with patch(_DISCOVER, return_value=manifests):
            mgr = PluginLifecycleManager(state_path=state_path)
            mgr.enable_plugin("enabled-one")
            mgr.disable_plugin("disabled-one")
            # default-one is never explicitly enabled/disabled

            statuses = mgr.get_status()

        enabled = [s for s in statuses if s["status"] == "ENABLED"]
        disabled = [s for s in statuses if s["status"] == "DISABLED"]

        enabled_names = {s["name"] for s in enabled}
        assert "enabled-one" in enabled_names
        assert "default-one" in enabled_names  # defaults to ENABLED
        assert len(enabled) == 2

        assert len(disabled) == 1
        assert disabled[0]["name"] == "disabled-one"

    def test_sync_discovered(self, tmp_path):
        """discover returns 2 manifests, one already in store;
        get_status shows both, new one defaults to ENABLED."""
        state_path = tmp_path / "plugin_state.json"

        # Phase 1: enable one plugin with only it discovered
        with patch(_DISCOVER, return_value=[_make_manifest(name="existing")]):
            mgr = PluginLifecycleManager(state_path=state_path)
            mgr.enable_plugin("existing")

        # Phase 2: reload manager with 2 discovered plugins (simulating new discovery)
        both = [
            _make_manifest(name="existing"),
            _make_manifest(name="new-discovery"),
        ]
        with patch(_DISCOVER, return_value=both):
            mgr2 = PluginLifecycleManager(state_path=state_path)
            statuses = mgr2.get_status()

        names = {s["name"] for s in statuses}
        assert "existing" in names
        assert "new-discovery" in names
        assert len(statuses) == 2

        # The existing plugin keeps its ENABLED state
        existing_status = next(s for s in statuses if s["name"] == "existing")
        assert existing_status["status"] == "ENABLED"

        # The newly discovered plugin defaults to ENABLED (no state stored yet)
        new_status = next(s for s in statuses if s["name"] == "new-discovery")
        assert new_status["status"] == "ENABLED"

        # Only the pre-existing plugin should have state in the store
        assert "existing" in mgr2._state
        assert "new-discovery" not in mgr2._state

    def test_enable_already_enabled_returns_cached_without_rediscovery(self, tmp_path):
        """Calling enable_plugin twice returns cached state on the second call
        without calling discover_plugins again."""
        manifests = [_make_manifest(name="alpha")]
        state_path = tmp_path / "plugin_state.json"

        with patch(_DISCOVER, return_value=manifests) as mock_discover:
            mgr = PluginLifecycleManager(state_path=state_path)
            mgr.enable_plugin("alpha")

            calls_after_first_enable = mock_discover.call_count

            result = mgr.enable_plugin("alpha")

            # discover_plugins must NOT be called again
            assert mock_discover.call_count == calls_after_first_enable
            # Second call returns the cached enabled state dict
            assert result["enabled"] is True

    def test_enable_already_enabled_logs_info_with_plugin_name(self, tmp_path):
        """logger.info is called with a message containing the plugin name
        when the plugin is already enabled."""
        manifests = [_make_manifest(name="beta")]
        state_path = tmp_path / "plugin_state.json"

        with patch(_DISCOVER, return_value=manifests):
            mgr = PluginLifecycleManager(state_path=state_path)
            mgr.enable_plugin("beta")

            with patch(
                "crazypumpkin.framework.plugin_lifecycle.logger"
            ) as mock_logger:
                mgr.enable_plugin("beta")

            mock_logger.info.assert_called_once()
            log_message = mock_logger.info.call_args[0][0] % mock_logger.info.call_args[0][1:]
            assert "beta" in log_message

    def test_enable_path_traversal_name_rejected(self, tmp_path):
        """Plugin names containing path-traversal sequences are rejected."""
        state_path = tmp_path / "plugin_state.json"

        with patch(_DISCOVER, return_value=[]):
            mgr = PluginLifecycleManager(state_path=state_path)
            for bad_name in ["../etc/passwd", "foo/bar", "a\\b", "", "ha\x00ck"]:
                with pytest.raises(KeyError):
                    mgr.enable_plugin(bad_name)

    def test_disable_already_disabled_returns_without_updating_timestamp(self, tmp_path):
        """Calling disable_plugin on an already-disabled plugin returns
        without updating the disabled_at timestamp."""
        manifests = [_make_manifest(name="gamma")]
        state_path = tmp_path / "plugin_state.json"

        with patch(_DISCOVER, return_value=manifests):
            mgr = PluginLifecycleManager(state_path=state_path)
            mgr.enable_plugin("gamma")
            mgr.disable_plugin("gamma")

            original_disabled_at = mgr._state["gamma"]["disabled_at"]

            result = mgr.disable_plugin("gamma")

            # disabled_at must not have changed
            assert mgr._state["gamma"]["disabled_at"] == original_disabled_at
            # Second call returns the cached disabled state dict
            assert result["enabled"] is False

    def test_disable_already_disabled_logs_info_with_plugin_name(self, tmp_path):
        """logger.info is called with a message containing the plugin name
        when the plugin is already disabled."""
        manifests = [_make_manifest(name="delta")]
        state_path = tmp_path / "plugin_state.json"

        with patch(_DISCOVER, return_value=manifests):
            mgr = PluginLifecycleManager(state_path=state_path)
            mgr.enable_plugin("delta")
            mgr.disable_plugin("delta")

            with patch(
                "crazypumpkin.framework.plugin_lifecycle.logger"
            ) as mock_logger:
                mgr.disable_plugin("delta")

            mock_logger.info.assert_called_once()
            log_message = mock_logger.info.call_args[0][0] % mock_logger.info.call_args[0][1:]
            assert "delta" in log_message

    def test_disable_path_traversal_name_rejected(self, tmp_path):
        """Plugin names containing path-traversal sequences are rejected by disable_plugin."""
        state_path = tmp_path / "plugin_state.json"

        with patch(_DISCOVER, return_value=[]):
            mgr = PluginLifecycleManager(state_path=state_path)
            for bad_name in ["../etc/passwd", "foo/bar", "a\\b", "", "ha\x00ck"]:
                with pytest.raises(KeyError):
                    mgr.disable_plugin(bad_name)

    def test_plugin_state_persistence(self, tmp_path):
        """Save state, create new manager with same store, verify state loads."""
        manifests = [_make_manifest(name="persist-me")]
        state_path = tmp_path / "plugin_state.json"

        # Phase 1: enable plugin and let manager save state
        with patch(_DISCOVER, return_value=manifests):
            mgr1 = PluginLifecycleManager(state_path=state_path)
            mgr1.enable_plugin("persist-me")

        assert state_path.exists()

        # Phase 2: create a brand new manager pointing at the same file
        with patch(_DISCOVER, return_value=manifests):
            mgr2 = PluginLifecycleManager(state_path=state_path)

        # The new manager should have loaded the persisted state
        assert "persist-me" in mgr2._state
        assert mgr2._state["persist-me"]["enabled"] is True
        assert "enabled_at" in mgr2._state["persist-me"]

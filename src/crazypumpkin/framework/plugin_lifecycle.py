"""Plugin lifecycle management — enable, disable, and sync plugins."""

from __future__ import annotations

import logging
from typing import Any

from crazypumpkin.framework.models import PluginManifest
from crazypumpkin.framework.plugin_loader import discover_plugins, validate_plugin, load_plugin
from crazypumpkin.framework.store import Store

logger = logging.getLogger("crazypumpkin.plugin_lifecycle")


class PluginLifecycleManager:
    """Manages the full lifecycle of discovered plugins."""

    def __init__(self, store: Store) -> None:
        self._store = store
        self._active: dict[str, Any] = {}

    def enable_plugin(self, name: str) -> bool:
        """Find, validate, load, and enable a plugin by name.

        Returns True on success, False on failure.
        """
        manifests = discover_plugins()
        manifest = next((m for m in manifests if m.name == name), None)
        if manifest is None:
            logger.error("Plugin '%s' not found in discovered plugins", name)
            return False

        errors = validate_plugin(manifest)
        if errors:
            for err in errors:
                logger.error("Plugin '%s' validation failed: %s", name, err)
            return False

        plugin_obj = load_plugin(manifest)
        if plugin_obj is None:
            return False

        self._active[name] = plugin_obj
        logger.info("Enabled plugin '%s'", name)
        return True

    def disable_plugin(self, name: str) -> bool:
        """Disable and remove a plugin by name."""
        if name not in self._active:
            logger.warning("Plugin '%s' is not active", name)
            return False
        del self._active[name]
        logger.info("Disabled plugin '%s'", name)
        return True

    def list_active(self) -> list[str]:
        """Return names of all active plugins."""
        return list(self._active.keys())

    def sync_discovered(self) -> list[PluginManifest]:
        """Discover all plugins and return their manifests."""
        return discover_plugins()

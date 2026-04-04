"""Plugin lifecycle management — enable, disable, and query plugin states."""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from crazypumpkin.framework.models import PluginManifest
from crazypumpkin.framework.plugin_loader import discover_plugins

logger = logging.getLogger("crazypumpkin.plugin_lifecycle")


class PluginLifecycleManager:
    """Manages plugin enable/disable state with JSON file persistence."""

    def __init__(self, state_path: Path | None = None) -> None:
        if state_path is None:
            state_path = Path.cwd() / "data" / "plugin_state.json"
        self._state_path = state_path
        self._state: dict[str, dict[str, Any]] = self._load_state()

    def _load_state(self) -> dict[str, dict[str, Any]]:
        if self._state_path.is_file():
            try:
                return json.loads(self._state_path.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError):
                logger.warning("Could not read plugin state file; starting fresh.")
        return {}

    def _save_state(self) -> None:
        self._state_path.parent.mkdir(parents=True, exist_ok=True)
        self._state_path.write_text(
            json.dumps(self._state, indent=2), encoding="utf-8"
        )

    def _known_plugin_names(self) -> set[str]:
        return {m.name for m in discover_plugins()}

    def enable_plugin(self, name: str) -> None:
        """Enable a plugin by name. Raises ``KeyError`` if not found."""
        if not name or ".." in name or "/" in name or "\\" in name or "\x00" in name:
            raise KeyError(name)
        existing = self._state.get(name, {})
        if existing.get("enabled", False):
            logger.info("Plugin '%s' is already enabled", name)
            return existing
        if name not in self._known_plugin_names():
            raise KeyError(name)
        self._state[name] = {
            "enabled": True,
            "enabled_at": datetime.now(timezone.utc).isoformat(),
        }
        self._save_state()

    def disable_plugin(self, name: str) -> None:
        """Disable a plugin by name. Raises ``KeyError`` if not found."""
        if not name or ".." in name or "/" in name or "\\" in name or "\x00" in name:
            raise KeyError(name)
        existing = self._state.get(name, {})
        if existing.get("enabled") is False:
            logger.info("Plugin '%s' is already disabled", name)
            return existing
        if name not in self._known_plugin_names():
            raise KeyError(name)
        self._state[name] = {
            "enabled": False,
            "disabled_at": datetime.now(timezone.utc).isoformat(),
        }
        self._save_state()

    def get_status(self, name: str | None = None) -> list[dict[str, Any]]:
        """Return status dicts for all plugins, or one specific plugin."""
        manifests = discover_plugins()
        if name is not None:
            manifests = [m for m in manifests if m.name == name]

        result: list[dict[str, Any]] = []
        for m in manifests:
            info = self._state.get(m.name, {})
            enabled = info.get("enabled", True)
            result.append({
                "name": m.name,
                "version": m.version or "unknown",
                "status": "ENABLED" if enabled else "DISABLED",
                "type": m.plugin_type or "unknown",
                "enabled_at": info.get("enabled_at", info.get("disabled_at", "")),
            })
        return result

"""Plugin discovery, validation, and loading for the Crazy Pumpkin framework."""

from __future__ import annotations

import importlib
import logging
import sys
from pathlib import Path
from typing import Any

from crazypumpkin.framework.models import PluginManifest

logger = logging.getLogger("crazypumpkin.plugin_loader")

FRAMEWORK_VERSION = "0.1.0"
ENTRY_POINT_GROUP = "crazypumpkin.plugins"
REQUIRED_MANIFEST_FIELDS = ("name", "version", "entry_point", "plugin_type")


def _parse_version(version: str) -> tuple[int, ...]:
    """Parse a dotted version string into a comparable tuple."""
    try:
        return tuple(int(p) for p in version.split("."))
    except (ValueError, AttributeError):
        return (0,)


def discover_plugins(plugins_dir: str | Path | None = None) -> list[PluginManifest]:
    """Discover plugins from entry-points and a local plugins directory.

    Scans:
      1. Python entry-points in the ``crazypumpkin.plugins`` group.
      2. A local plugins directory (defaults to ``src/crazypumpkin/plugins/``).

    Returns a list of :class:`PluginManifest` instances (one per discovered
    plugin).  Duplicates (same name) are kept — callers should validate.
    """
    manifests: list[PluginManifest] = []

    # 1. Entry-points
    if sys.version_info >= (3, 12):
        from importlib.metadata import entry_points
        eps = entry_points(group=ENTRY_POINT_GROUP)
    else:
        from importlib.metadata import entry_points
        all_eps = entry_points()
        eps = all_eps.get(ENTRY_POINT_GROUP, [])  # type: ignore[union-attr]

    for ep in eps:
        manifests.append(PluginManifest(
            name=ep.name,
            entry_point=ep.value,
            plugin_type="agent",
        ))

    # 2. Local plugins directory
    if plugins_dir is None:
        plugins_dir = Path(__file__).resolve().parent.parent / "plugins"
    else:
        plugins_dir = Path(plugins_dir)

    if plugins_dir.is_dir():
        for child in sorted(plugins_dir.iterdir()):
            if child.suffix == ".py" and child.name != "__init__.py":
                module_name = child.stem
                manifests.append(PluginManifest(
                    name=module_name,
                    entry_point=f"crazypumpkin.plugins.{module_name}",
                    plugin_type="agent",
                ))

    return manifests


def validate_plugin(manifest: PluginManifest) -> list[str]:
    """Validate a plugin manifest.

    Returns a list of error strings.  An empty list means the manifest is
    valid.
    """
    errors: list[str] = []

    for field_name in REQUIRED_MANIFEST_FIELDS:
        if not getattr(manifest, field_name, ""):
            errors.append(f"Missing required field: {field_name}")

    if manifest.plugin_type and manifest.plugin_type not in ("agent", "provider"):
        errors.append(
            f"Invalid plugin_type '{manifest.plugin_type}'; expected 'agent' or 'provider'"
        )

    if manifest.min_framework_version:
        required = _parse_version(manifest.min_framework_version)
        current = _parse_version(FRAMEWORK_VERSION)
        if required > current:
            errors.append(
                f"Plugin requires framework >= {manifest.min_framework_version}, "
                f"but current is {FRAMEWORK_VERSION}"
            )

    return errors


def load_plugin(manifest: PluginManifest) -> Any:
    """Import and instantiate the plugin described by *manifest*.

    The entry-point string is either a dotted module path (the module's
    default export is used) or ``module:attribute``.

    Plugin code runs inside a sandbox wrapper that catches exceptions and
    logs them without crashing the host.

    Returns the loaded plugin object, or ``None`` on failure.
    """
    errors = validate_plugin(manifest)
    if errors:
        for err in errors:
            logger.error("Plugin '%s' validation failed: %s", manifest.name, err)
        return None

    try:
        module_path, _, attr_name = manifest.entry_point.partition(":")
        module = importlib.import_module(module_path)

        if attr_name:
            plugin_cls = getattr(module, attr_name)
        else:
            # Convention: look for a class named ``Plugin`` in the module
            plugin_cls = getattr(module, "Plugin", None)
            if plugin_cls is None:
                logger.error(
                    "Plugin '%s': module '%s' has no 'Plugin' class and no "
                    "attribute was specified in entry_point",
                    manifest.name,
                    module_path,
                )
                return None

        plugin_obj = _sandbox_call(manifest, plugin_cls)
        if plugin_obj is not None:
            logger.info("Loaded plugin '%s' (%s)", manifest.name, manifest.plugin_type)
        return plugin_obj

    except ImportError as exc:
        logger.error("Plugin '%s' import failed: %s", manifest.name, exc)
        return None
    except Exception as exc:
        logger.error("Plugin '%s' load error: %s", manifest.name, exc)
        return None


def _sandbox_call(manifest: PluginManifest, plugin_cls: Any) -> Any:
    """Instantiate *plugin_cls* inside a sandbox that catches exceptions."""
    try:
        return plugin_cls()
    except Exception as exc:
        logger.error(
            "Plugin '%s' instantiation failed (sandboxed): %s",
            manifest.name,
            exc,
        )
        return None

"""Plugin discovery, validation, and loading for the Crazy Pumpkin framework."""

from __future__ import annotations

import importlib
import logging
import re
import sys
from pathlib import Path
from typing import Any

from crazypumpkin.framework.models import PluginManifest

logger = logging.getLogger("crazypumpkin.plugin_loader")

FRAMEWORK_VERSION = "0.1.0"
ENTRY_POINT_GROUP = "crazypumpkin.plugins"
REQUIRED_MANIFEST_FIELDS = ("name", "version", "entry_point", "plugin_type")

_CONSTRAINT_RE = re.compile(r"(>=|<=|!=|==|>|<)(.+)")


def _parse_version(version: str) -> tuple[int, ...]:
    """Parse a dotted version string into a comparable tuple."""
    try:
        return tuple(int(p) for p in version.split("."))
    except (ValueError, AttributeError):
        return (0,)


def _parse_dependency_spec(spec: str) -> tuple[str, list[tuple[str, str]]]:
    """Parse a dependency spec like ``plugin-name>=1.0,<2.0``.

    Returns ``(name, [(operator, version), ...])``.
    """
    spec = spec.strip()
    # Find the first operator character to split name from constraints
    match = re.match(r"^([A-Za-z0-9_-]+)(.*)", spec)
    if not match:
        return (spec, [])

    name = match.group(1)
    rest = match.group(2).strip()
    if not rest:
        return (name, [])

    constraints: list[tuple[str, str]] = []
    for part in rest.split(","):
        part = part.strip()
        m = _CONSTRAINT_RE.match(part)
        if m:
            constraints.append((m.group(1), m.group(2).strip()))
    return (name, constraints)


def _version_satisfies(version: str, op: str, target: str) -> bool:
    """Return True if *version* satisfies the constraint *op target*."""
    v = _parse_version(version)
    t = _parse_version(target)
    # Pad to equal length so (1,0) and (1,0,0) compare as equal
    max_len = max(len(v), len(t))
    v = v + (0,) * (max_len - len(v))
    t = t + (0,) * (max_len - len(t))
    if op == ">=":
        return v >= t
    if op == "<=":
        return v <= t
    if op == ">":
        return v > t
    if op == "<":
        return v < t
    if op == "==":
        return v == t
    if op == "!=":
        return v != t
    return False


def check_requires(
    manifest: PluginManifest,
    available_plugins: dict[str, str] | None = None,
    framework_version: str | None = None,
) -> list[str]:
    """Check whether the plugin's ``requires`` dependencies are satisfied.

    Args:
        manifest: The plugin manifest to check.
        available_plugins: Mapping of plugin name to version for loaded/available plugins.
        framework_version: Current framework version.  Defaults to *FRAMEWORK_VERSION*.

    Returns:
        A list of error strings.  Empty means all requirements are met.
    """
    if not manifest.requires:
        return []

    if available_plugins is None:
        available_plugins = {}
    if framework_version is None:
        framework_version = FRAMEWORK_VERSION

    errors: list[str] = []

    for dep_spec in manifest.requires:
        name, constraints = _parse_dependency_spec(dep_spec)

        if name in ("crazypumpkin", "cp-os"):
            # Framework version constraint
            for op, ver in constraints:
                if not _version_satisfies(framework_version, op, ver):
                    errors.append(
                        f"Framework version {framework_version} does not satisfy "
                        f"constraint '{name}{op}{ver}'"
                    )
        else:
            # Plugin dependency
            if name not in available_plugins:
                errors.append(f"Required plugin '{name}' is not available")
            elif constraints:
                plugin_ver = available_plugins[name]
                for op, ver in constraints:
                    if not _version_satisfies(plugin_ver, op, ver):
                        errors.append(
                            f"Plugin '{name}' version {plugin_ver} does not satisfy "
                            f"constraint '{name}{op}{ver}'"
                        )

    return errors


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


def load_plugin(
    manifest: PluginManifest,
    available_plugins: dict[str, str] | None = None,
) -> Any:
    """Import and instantiate the plugin described by *manifest*.

    The entry-point string is either a dotted module path (the module's
    default export is used) or ``module:attribute``.

    Plugin code runs inside a sandbox wrapper that catches exceptions and
    logs them without crashing the host.

    Args:
        manifest: The plugin manifest describing the plugin to load.
        available_plugins: Mapping of plugin name to version string for
            already-loaded plugins.  Used to check ``requires`` constraints.

    Returns the loaded plugin object, or ``None`` on failure.
    """
    errors = validate_plugin(manifest)
    if errors:
        for err in errors:
            logger.error("Plugin '%s' validation failed: %s", manifest.name, err)
        return None

    dep_errors = check_requires(manifest, available_plugins=available_plugins)
    if dep_errors:
        for err in dep_errors:
            logger.error("Plugin '%s' dependency check failed: %s", manifest.name, err)
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


class PluginLoader:
    """High-level plugin discovery and loading."""

    def __init__(self, config_plugins: list[PluginManifest] | None = None) -> None:
        self._config_plugins: dict[str, PluginManifest] = {
            p.name: p for p in (config_plugins or [])
        }

    def discover_entrypoint_plugins(
        self, group: str = ENTRY_POINT_GROUP
    ) -> list[PluginManifest]:
        """Discover plugins registered as Python entry points.

        Each entry point's ``load()`` should return a dict of
        :class:`PluginManifest` fields.  If a config plugin with the same
        name was provided at construction time, it takes precedence.
        """
        from importlib.metadata import entry_points as _entry_points

        try:
            if sys.version_info >= (3, 12):
                eps = _entry_points(group=group)
            else:
                all_eps = _entry_points()
                eps = all_eps.get(group, [])  # type: ignore[union-attr]
        except Exception:
            eps = []

        manifests: list[PluginManifest] = []
        for ep in eps:
            if ep.name in self._config_plugins:
                manifests.append(self._config_plugins[ep.name])
                continue
            try:
                loaded = ep.load()
                if isinstance(loaded, dict):
                    manifests.append(PluginManifest(**loaded))
                elif isinstance(loaded, PluginManifest):
                    manifests.append(loaded)
                else:
                    manifests.append(
                        PluginManifest(
                            name=ep.name,
                            entry_point=ep.value,
                            plugin_type="agent",
                        )
                    )
            except ImportError as exc:
                logger.warning(
                    "Entry-point '%s' failed to load: %s", ep.name, exc
                )
            except Exception as exc:
                logger.warning(
                    "Entry-point '%s' error: %s", ep.name, exc
                )

        return manifests


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

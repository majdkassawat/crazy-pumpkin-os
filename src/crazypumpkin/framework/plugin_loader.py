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


_UNSET = object()


def discover_plugins(group: str = ENTRY_POINT_GROUP, plugins_dir: str | Path | None = _UNSET) -> list[PluginManifest]:  # type: ignore[assignment]
    """Scan installed packages for entry-points in the given group and return validated manifests.

    Each entry-point should resolve to a module exporting a ``plugin_manifest``
    dict (keys: name, version, agent_class, config_schema).  The function
    validates each dict into a :class:`PluginManifest` model.  Invalid or
    missing manifest dicts are skipped with a warning log.

    When *plugins_dir* is provided, also scans a local directory for ``.py``
    files (backward-compatible path).
    """
    manifests: list[PluginManifest] = []

    # 1. Entry-points — load module and validate plugin_manifest dict
    if sys.version_info >= (3, 12):
        from importlib.metadata import entry_points
        eps = entry_points(group=group)
    else:
        from importlib.metadata import entry_points
        all_eps = entry_points()
        eps = all_eps.get(group, [])  # type: ignore[union-attr]

    for ep in eps:
        try:
            module_path = ep.value.split(":")[0]
            mod = importlib.import_module(module_path)
        except Exception as exc:
            logger.warning("Entry-point '%s' failed to load: %s", ep.name, exc)
            continue

        manifest_dict = getattr(mod, "plugin_manifest", None)
        if not isinstance(manifest_dict, dict):
            logger.warning(
                "Entry-point '%s': module has no plugin_manifest dict; skipping",
                ep.name,
            )
            continue

        try:
            manifest = PluginManifest(
                name=manifest_dict["name"],
                version=manifest_dict["version"],
                agent_class=manifest_dict["agent_class"],
                config_schema=manifest_dict.get("config_schema"),
                entry_point=ep.value,
            )
        except (KeyError, TypeError) as exc:
            logger.warning(
                "Entry-point '%s': invalid manifest dict (%s); skipping",
                ep.name,
                exc,
            )
            continue

        manifests.append(manifest)

    # 2. Local plugins directory (backward-compatible path)
    if plugins_dir is not _UNSET:
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


def discover_entry_point_plugins() -> list[PluginManifest]:
    """Discover plugins via the ``crazypumpkin.plugins`` entry-point group.

    Each entry point should resolve to a module containing a
    ``plugin_manifest() -> PluginManifest`` callable.  If the callable is
    missing or raises, a warning is logged and the entry point is skipped.

    Returns a list of :class:`PluginManifest` instances.
    """
    from importlib.metadata import entry_points as _entry_points

    manifests: list[PluginManifest] = []

    if sys.version_info >= (3, 12):
        eps = _entry_points(group=ENTRY_POINT_GROUP)
    else:
        all_eps = _entry_points()
        eps = all_eps.get(ENTRY_POINT_GROUP, [])  # type: ignore[union-attr]

    for ep in eps:
        try:
            module_path = ep.value.split(":")[0]
            mod = importlib.import_module(module_path)
        except Exception as exc:
            logger.warning("Entry-point '%s' failed to load: %s", ep.name, exc)
            continue

        manifest_fn = getattr(mod, "plugin_manifest", None)
        if manifest_fn is None:
            logger.warning(
                "Entry-point '%s': module has no plugin_manifest() callable; skipping",
                ep.name,
            )
            continue

        try:
            manifest = manifest_fn()
        except Exception as exc:
            logger.warning(
                "Entry-point '%s': plugin_manifest() raised %s; skipping",
                ep.name,
                exc,
            )
            continue

        manifests.append(manifest)

    return manifests


def get_plugin_info(name: str) -> PluginManifest | None:
    """Return the :class:`PluginManifest` for the plugin with the given *name*, or ``None``."""
    for plugin in discover_entry_point_plugins():
        if plugin.name == name:
            return plugin
    return None


def load_plugins(plugins_dir: str | Path | None = None) -> list[PluginManifest]:
    """Load plugins from directory and entry-points, deduplicating by name.

    Directory-based plugins are loaded first, then entry-point plugins.
    Duplicates (by name) are skipped — the first occurrence wins.
    """
    dir_manifests = discover_plugins(plugins_dir=plugins_dir)
    ep_manifests = discover_entry_point_plugins()

    seen_names: set[str] = set()
    merged: list[PluginManifest] = []

    for m in dir_manifests:
        if m.name not in seen_names:
            seen_names.add(m.name)
            merged.append(m)

    for m in ep_manifests:
        if m.name not in seen_names:
            seen_names.add(m.name)
            merged.append(m)

    return merged


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

"""Config schema migration — applies sequential upgrade steps to transform
a config dict from one version to another."""

from __future__ import annotations

from typing import Callable

# Each migration function takes a config dict and returns the upgraded dict.
MigrationFunc = Callable[[dict], dict]

# Registry: maps (from_version, to_version) to a migration function.
_migrations: dict[tuple[str, str], MigrationFunc] = {}

# Ordered list of known versions for path resolution.
_version_order: list[str] = []


def register_migration(from_version: str, to_version: str) -> Callable[[MigrationFunc], MigrationFunc]:
    """Decorator to register a migration function between two adjacent versions."""
    def decorator(func: MigrationFunc) -> MigrationFunc:
        _migrations[(from_version, to_version)] = func
        for v in (from_version, to_version):
            if v not in _version_order:
                _version_order.append(v)
        return func
    return decorator


def clear_migrations() -> None:
    """Remove all registered migrations (useful for testing)."""
    _migrations.clear()
    _version_order.clear()


def _build_path(old_version: str, new_version: str) -> list[tuple[str, str]]:
    """Find the sequential chain of migration steps from old_version to new_version."""
    if old_version == new_version:
        return []

    # BFS to find path through the migration graph
    visited: set[str] = {old_version}
    queue: list[tuple[str, list[tuple[str, str]]]] = [(old_version, [])]

    while queue:
        current, path = queue.pop(0)
        for (src, dst), _ in _migrations.items():
            if src == current and dst not in visited:
                new_path = path + [(src, dst)]
                if dst == new_version:
                    return new_path
                visited.add(dst)
                queue.append((dst, new_path))

    raise ValueError(
        f"No migration path from version '{old_version}' to '{new_version}'"
    )


def migrate_config(old_version: str, new_version: str, config: dict | None = None) -> dict:
    """Apply sequential schema upgrade steps to transform a config dict.

    Args:
        old_version: The current version of the config.
        new_version: The target version to migrate to.
        config: The config dict to migrate. If None, an empty dict is used.

    Returns:
        The upgraded config dict with an updated 'version' field.

    Raises:
        ValueError: When no migration path exists between the versions.
    """
    if config is None:
        config = {}

    result = dict(config)
    steps = _build_path(old_version, new_version)

    for src, dst in steps:
        func = _migrations[(src, dst)]
        result = func(result)

    result["version"] = new_version
    return result

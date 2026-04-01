import os
import copy
import json
from typing import Any

_MISSING = object()


def _coerce_value(value: str, existing: Any = _MISSING) -> Any:
    """Coerce a string env var value to the appropriate Python type.

    Schema-aware: if *existing* is provided (not _MISSING), the target type is
    inferred from the current config value so that ``"0"``/``"1"`` map to
    ``int`` when the field is an ``int`` and to ``bool`` only when the field is
    already a ``bool``.  When no existing value is available (new key),
    heuristic coercion is used but ``"0"``/``"1"`` are kept as integers to
    avoid silent data corruption.
    """
    # --- Schema-aware coercion when existing value is known ---
    if existing is not _MISSING:
        if isinstance(existing, bool):
            return value.lower() in ("true", "1")
        if isinstance(existing, int):
            try:
                return int(value)
            except ValueError:
                return value
        if isinstance(existing, float):
            try:
                return float(value)
            except ValueError:
                return value
        if isinstance(existing, list):
            return [item.strip() for item in value.split(",")]
        # Default: keep as string
        return value

    # --- Heuristic coercion for new / unknown keys ---
    if value.lower() == "true":
        return True
    if value.lower() == "false":
        return False
    # "0" and "1" stay as int when there is no schema hint
    try:
        return int(value)
    except ValueError:
        pass
    if "," in value:
        return [item.strip() for item in value.split(",")]
    return value


def _env_key_to_path(env_key: str, prefix: str) -> list[str] | None:
    """Convert CPOS_SECTION_KEY or CPOS_SECTION__NESTED_KEY to config path segments.

    Single underscores within a segment are treated as literal underscores in the
    config key (lowercased).  Double underscores delimit nesting levels.

    Returns None if the resulting path is invalid (empty segments).
    """
    remainder = env_key[len(prefix) + 1:]
    if not remainder:
        return None
    segments = remainder.split("__")
    result = [seg.lower() for seg in segments]
    if any(seg == "" for seg in result):
        return None
    return result


def _get_nested(d: dict, path: list[str]) -> Any:
    """Get a value from a nested dict.  Returns _MISSING when path doesn't exist."""
    for key in path:
        if not isinstance(d, dict) or key not in d:
            return _MISSING
        d = d[key]
    return d


def _set_nested(d: dict, path: list[str], value: Any) -> None:
    """Set a value in a nested dict, creating intermediate dicts as needed."""
    for key in path[:-1]:
        if key not in d or not isinstance(d[key], dict):
            d[key] = {}
        d = d[key]
    d[path[-1]] = value


def resolve_env_overrides(config: dict[str, Any], prefix: str = "CPOS") -> dict[str, Any]:
    """Return a new config dict with values overridden by matching env vars.

    Convention: CPOS_SECTION_KEY=value overrides config['section']['key'].
    Nested keys use double underscore: CPOS_LLM__DEFAULT_PROVIDER=openai
    overrides config['llm']['default_provider'].

    Type coercion is schema-aware: the type of the existing config value
    determines how the env var string is converted.  When no existing value
    is present, heuristic coercion is applied (but "0"/"1" become int, not
    bool, to prevent silent data corruption).
    """
    result = copy.deepcopy(config)
    env_prefix = prefix + "_"

    for key, value in os.environ.items():
        if key.startswith(env_prefix):
            path = _env_key_to_path(key, prefix)
            if path is None:
                continue
            existing = _get_nested(config, path)
            coerced = _coerce_value(value, existing)
            _set_nested(result, path, coerced)

    return result


def list_active_overrides(config: dict[str, Any], prefix: str = "CPOS") -> list[tuple[str, str, Any]]:
    """Return list of (env_var_name, config_path, value) for all active env overrides."""
    overrides = []
    env_prefix = prefix + "_"

    for key, value in sorted(os.environ.items()):
        if key.startswith(env_prefix):
            path = _env_key_to_path(key, prefix)
            if path is None:
                continue
            config_path = ".".join(path)
            existing = _get_nested(config, path)
            coerced = _coerce_value(value, existing)
            overrides.append((key, config_path, coerced))

    return overrides

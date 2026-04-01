"""Environment variable override resolution for configuration."""

from __future__ import annotations

import copy
import os
from typing import Any


def env_key_for_path(dotted_path: str, prefix: str = "CPOS") -> str:
    """Convert a dotted config path to an environment variable name.

    Example: 'pipeline.max_retries' -> 'CPOS_PIPELINE_MAX_RETRIES'
    """
    return f"{prefix}_{dotted_path.replace('.', '_').upper()}"


def _coerce(value: str, existing: Any) -> Any:
    """Coerce a string env var value to match the type of *existing*."""
    if isinstance(existing, bool):
        return value.lower() in ("true", "1", "yes")
    if isinstance(existing, int):
        return int(value)
    if isinstance(existing, float):
        return float(value)
    return value


def _walk(
    config: dict[str, Any],
    result: dict[str, Any],
    path_parts: list[str],
    prefix: str,
) -> None:
    """Recursively walk config, applying env overrides into *result*."""
    for key, value in config.items():
        current_parts = path_parts + [key]
        if isinstance(value, dict):
            result[key] = dict(value)
            _walk(config[key], result[key], current_parts, prefix)
        else:
            env_name = env_key_for_path(".".join(current_parts), prefix)
            env_val = os.environ.get(env_name)
            if env_val is not None:
                result[key] = _coerce(env_val, value)
            else:
                result[key] = value


def apply_env_overrides(
    config: dict[str, Any], prefix: str = "CPOS"
) -> dict[str, Any]:
    """Return a new config dict with values overridden by matching env vars.

    Walks the config recursively. For each leaf value, checks for an env var
    named ``{prefix}_{DOTTED_PATH_UPPER}`` and, if set, replaces the value
    after coercing it to match the original type (int, float, bool, str).

    The input *config* is not mutated.
    """
    result: dict[str, Any] = {}
    _walk(config, result, [], prefix)
    return result

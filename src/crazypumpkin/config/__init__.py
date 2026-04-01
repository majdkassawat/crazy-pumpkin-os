"""Configuration utilities — default config template and validation."""

from __future__ import annotations

import copy
from typing import Any


class ConfigValidationError(Exception):
    """Raised when configuration validation fails.

    Attributes
    ----------
    errors:
        A list of human-readable error strings describing what is invalid.
    """

    def __init__(self, errors: list[str]) -> None:
        self.errors = list(errors)
        super().__init__("; ".join(errors))


# ---------------------------------------------------------------------------
# Default configuration
# ---------------------------------------------------------------------------

DEFAULT_CONFIG: dict[str, Any] = {
    "company": {
        "name": "My AI Company",
    },
    "products": [
        {
            "name": "Default Product",
            "workspace": "./products/default",
            "source_dir": "src",
            "test_dir": "tests",
            "test_command": "python -m pytest tests/ -v --tb=short",
            "git_branch": "main",
            "auto_pm": False,
        },
    ],
    "llm": {
        "default_provider": "anthropic_api",
        "providers": {
            "anthropic_api": {"api_key": "${ANTHROPIC_API_KEY}"},
        },
        "agent_models": {
            "developer": {"model": "opus"},
            "strategist": {"model": "sonnet"},
            "reviewer": {"model": "sonnet"},
        },
    },
    "agents": [
        {
            "name": "Strategist",
            "role": "strategy",
            "description": "Plans and decomposes goals into tasks",
        },
        {
            "name": "Developer",
            "role": "execution",
            "description": "Implements code changes",
        },
        {
            "name": "Reviewer",
            "role": "reviewer",
            "description": "Reviews submitted code for quality",
        },
    ],
    "triggers": [],
    "plugins": [],
    "observability": {
        "logging": {
            "level": "INFO",
        },
        "metrics": {
            "enabled": False,
        },
    },
    "scheduler": {
        "interval": 30,
        "enabled": True,
    },
    "pipeline": {
        "cycle_interval": 30,
    },
    "notifications": {
        "providers": [],
    },
    "dashboard": {
        "port": 8500,
        "host": "127.0.0.1",
    },
    "voice": {
        "enabled": False,
    },
}


def get_default_config() -> dict[str, Any]:
    """Return a default configuration dict suitable for a new project.

    The returned dict contains all required top-level keys with sensible
    defaults so that ``validate_config(get_default_config())`` returns
    no errors.
    """
    return copy.deepcopy(DEFAULT_CONFIG)


# ---------------------------------------------------------------------------
# Deep merge
# ---------------------------------------------------------------------------


def _deep_merge(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    """Recursively merge *override* into *base*, returning a new dict.

    - Dict values are deep-merged.
    - Non-dict values in *override* replace those in *base*.
    - Keys only in *base* are preserved.
    """
    result = dict(base)
    for key, value in override.items():
        if key in result and isinstance(result[key], dict) and isinstance(value, dict):
            result[key] = _deep_merge(result[key], value)
        else:
            result[key] = value
    return result


def merge_with_defaults(user_config: dict[str, Any]) -> dict[str, Any]:
    """Merge a partial user config with :data:`DEFAULT_CONFIG`.

    Missing sections are filled from the defaults.  Nested dicts are
    deep-merged so that the user only needs to specify the keys they
    want to override.

    Parameters
    ----------
    user_config:
        A (possibly sparse) configuration dict.

    Returns
    -------
    A new dict with all default keys present and user overrides applied.
    """
    defaults = get_default_config()
    return _deep_merge(defaults, user_config)


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------


def validate_config(config: dict[str, Any]) -> list[str]:
    """Validate a configuration dict and return a list of error strings.

    Returns an empty list when the configuration is valid.
    """
    errors: list[str] = []

    if not isinstance(config, dict):
        return ["Config must be a dict"]

    # company
    company = config.get("company")
    if not company or not isinstance(company, dict):
        errors.append("Missing required section: company")
    elif not company.get("name"):
        errors.append("Missing required field: company.name")

    # agents
    agents = config.get("agents")
    if not agents or not isinstance(agents, list):
        errors.append("Missing required section: agents")
    else:
        for i, a in enumerate(agents):
            if not isinstance(a, dict):
                errors.append(f"agents[{i}] must be a dict")
                continue
            if not a.get("name") or not isinstance(a.get("name"), str):
                errors.append(f"Missing required field: agents[{i}].name")
            if not a.get("role"):
                errors.append(f"Missing required field: agents[{i}].role")

    # triggers
    if "triggers" not in config:
        errors.append("Missing required section: triggers")
    else:
        triggers = config["triggers"]
        if not isinstance(triggers, list):
            errors.append("triggers must be a list")
        else:
            for i, t in enumerate(triggers):
                if isinstance(t, dict):
                    expr = t.get("expression")
                    if expr is not None and not isinstance(expr, str):
                        errors.append(f"triggers[{i}].expression must be a string")

    # plugins
    if "plugins" not in config:
        errors.append("Missing required section: plugins")
    else:
        plugins = config["plugins"]
        if not isinstance(plugins, list):
            errors.append("plugins must be a list")
        else:
            for i, p in enumerate(plugins):
                if isinstance(p, dict):
                    path = p.get("path")
                    if path is not None and not isinstance(path, str):
                        errors.append(f"plugins[{i}].path must be a string")

    # observability
    if "observability" not in config:
        errors.append("Missing required section: observability")

    # scheduler
    if "scheduler" not in config:
        errors.append("Missing required section: scheduler")

    return errors

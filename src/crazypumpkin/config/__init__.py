"""Configuration utilities — default config template and validation."""

from __future__ import annotations

from typing import Any


def get_default_config() -> dict[str, Any]:
    """Return a default configuration dict suitable for a new project.

    The returned dict contains all required top-level keys with sensible
    defaults so that ``validate_config(get_default_config())`` returns
    no errors.
    """
    return {
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
            if not a.get("name"):
                errors.append(f"Missing required field: agents[{i}].name")
            if not a.get("role"):
                errors.append(f"Missing required field: agents[{i}].role")

    return errors

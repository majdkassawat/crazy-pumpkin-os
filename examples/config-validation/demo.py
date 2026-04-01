#!/usr/bin/env python3
"""Demo: Config validation and environment variable overrides.

Run this script to see the validation system in action:

    python examples/config-validation/demo.py
"""

from __future__ import annotations

import os
import sys

# Ensure the package is importable when running from the repo root
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "src"))

from crazypumpkin.config.validation import validate_config, get_default_schema
from crazypumpkin.config.env_override import resolve_env_overrides, list_active_overrides


def print_section(title: str) -> None:
    print(f"\n{'=' * 60}")
    print(f"  {title}")
    print(f"{'=' * 60}\n")


def main() -> None:
    # ----------------------------------------------------------------
    # 1. Validate a correct config
    # ----------------------------------------------------------------
    print_section("1. Validate a correct config")

    good_config = {
        "company": {"name": "Acme Corp"},
        "agents": [
            {"name": "developer", "role": "execution"},
            {"name": "reviewer", "role": "reviewer"},
        ],
        "dashboard": {"port": 8500, "host": "127.0.0.1"},
        "pipeline": {"cycle_interval": 30},
        "voice": {"enabled": False},
    }

    result = validate_config(good_config)
    print(f"Config valid: {result.valid}")
    print(f"Errors:       {len(result.errors)}")
    print(f"Warnings:     {len(result.warnings)}")

    # ----------------------------------------------------------------
    # 2. Validate a config with errors
    # ----------------------------------------------------------------
    print_section("2. Validate a config with errors")

    bad_config = {
        "company": {"name": "Acme Corp"},
        # "agents" is missing (required)
        "dashboard": {
            "port": "not-a-number",  # wrong type: should be int
            "pasword": "secret",     # typo: should be "password"
        },
    }

    result = validate_config(bad_config)
    print(f"Config valid: {result.valid}")

    if result.errors:
        print("\nErrors:")
        for err in result.errors:
            print(f"  [{err.path}] {err.message}")
            if err.suggestion:
                print(f"    Suggestion: {err.suggestion}")

    if result.warnings:
        print("\nWarnings:")
        for warn in result.warnings:
            print(f"  [{warn.path}] {warn.message}")
            if warn.suggestion:
                print(f"    Suggestion: {warn.suggestion}")

    # ----------------------------------------------------------------
    # 3. Environment variable overrides
    # ----------------------------------------------------------------
    print_section("3. Environment variable overrides")

    # Set some demo env vars
    os.environ["CPOS_DASHBOARD__PORT"] = "9000"
    os.environ["CPOS_VOICE__ENABLED"] = "true"
    os.environ["CPOS_LLM__DEFAULT_PROVIDER"] = "openai"

    base_config = {
        "company": {"name": "Acme Corp"},
        "agents": [{"name": "dev", "role": "execution"}],
        "dashboard": {"port": 8500, "host": "127.0.0.1"},
        "voice": {"enabled": False},
        "llm": {"default_provider": "anthropic_api"},
    }

    print("Before overrides:")
    print(f"  dashboard.port          = {base_config['dashboard']['port']!r}")
    print(f"  voice.enabled           = {base_config['voice']['enabled']!r}")
    print(f"  llm.default_provider    = {base_config['llm']['default_provider']!r}")

    overridden = resolve_env_overrides(base_config)

    print("\nAfter overrides:")
    print(f"  dashboard.port          = {overridden['dashboard']['port']!r}")
    print(f"  voice.enabled           = {overridden['voice']['enabled']!r}")
    print(f"  llm.default_provider    = {overridden['llm']['default_provider']!r}")

    # ----------------------------------------------------------------
    # 4. List active overrides
    # ----------------------------------------------------------------
    print_section("4. List active overrides")

    active = list_active_overrides(base_config)
    if active:
        for env_var, config_path, value in active:
            print(f"  {env_var} -> {config_path} = {value!r}")
    else:
        print("  No active CPOS_ overrides found.")

    # ----------------------------------------------------------------
    # 5. Validate the overridden config
    # ----------------------------------------------------------------
    print_section("5. Validate overridden config")

    result = validate_config(overridden)
    print(f"Config valid: {result.valid}")
    print(f"Errors:       {len(result.errors)}")
    print(f"Warnings:     {len(result.warnings)}")

    # ----------------------------------------------------------------
    # 6. Custom schema extension
    # ----------------------------------------------------------------
    print_section("6. Custom schema extension")

    schema = get_default_schema()
    schema["fields"]["my_plugin"] = {
        "type": "dict",
        "required_fields": ["api_url"],
        "fields": {
            "api_url": {"type": "str"},
            "timeout": {"type": "int"},
        },
    }

    config_with_plugin = {
        "company": {"name": "Acme Corp"},
        "agents": [{"name": "dev", "role": "execution"}],
        "my_plugin": {"api_url": "https://api.example.com", "timeout": 30},
    }

    result = validate_config(config_with_plugin, schema=schema)
    print(f"Config valid (with plugin schema): {result.valid}")
    print(f"Errors:   {len(result.errors)}")
    print(f"Warnings: {len(result.warnings)}")

    # Clean up demo env vars
    del os.environ["CPOS_DASHBOARD__PORT"]
    del os.environ["CPOS_VOICE__ENABLED"]
    del os.environ["CPOS_LLM__DEFAULT_PROVIDER"]

    print("\nDemo complete.")


if __name__ == "__main__":
    main()

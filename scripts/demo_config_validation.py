#!/usr/bin/env python3
"""Demo script: config validation and environment variable overrides."""
import os
import sys
from pathlib import Path

# Ensure the src directory is on the import path when run standalone.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from crazypumpkin.config import validate_config, get_default_config
from crazypumpkin.config.env_override import resolve_env_overrides, list_active_overrides


def demo_validation() -> None:
    """Demonstrate config validation with three different configs."""
    # 1. Empty dict — should fail validation
    print("--- Config 1: empty dict ---")
    errors = validate_config({})
    if errors:
        for err in errors:
            print(f"  ERROR: {err}")
    else:
        print("  Valid!")

    # 2. Partial config — has company but missing agents
    print("\n--- Config 2: partial (missing agents) ---")
    partial = {"company": {"name": "TestCo"}}
    errors = validate_config(partial)
    if errors:
        for err in errors:
            print(f"  ERROR: {err}")
    else:
        print("  Valid!")

    # 3. Full valid config from get_default_config()
    print("\n--- Config 3: get_default_config() ---")
    errors = validate_config(get_default_config())
    if errors:
        for err in errors:
            print(f"  ERROR: {err}")
    else:
        print("  Valid!")


def demo_env_overrides() -> None:
    """Demonstrate environment variable overrides with type coercion."""
    env_vars = {
        "CPOS_DASHBOARD__PORT": "9000",
        "CPOS_VOICE__ENABLED": "true",
    }

    # Set env vars
    for key, value in env_vars.items():
        os.environ[key] = value

    try:
        config = get_default_config()

        # Apply overrides
        overridden = resolve_env_overrides(config)
        print("--- Overridden values ---")
        print(f"  dashboard.port = {overridden['dashboard']['port']!r}  (type: {type(overridden['dashboard']['port']).__name__})")
        print(f"  voice.enabled  = {overridden['voice']['enabled']!r}  (type: {type(overridden['voice']['enabled']).__name__})")

        # List active overrides
        print("\n--- Active overrides (on empty config) ---")
        active = list_active_overrides({})
        for env_name, config_path, value in active:
            print(f"  {env_name} -> {config_path} = {value!r}")
    finally:
        # Clean up env vars
        for key in env_vars:
            os.environ.pop(key, None)


def main() -> None:
    """Run all demos."""
    print("=" * 50)
    print("  Config Validation Demo")
    print("=" * 50)
    demo_validation()

    print()
    print("=" * 50)
    print("  Environment Variable Overrides Demo")
    print("=" * 50)
    demo_env_overrides()


if __name__ == "__main__":
    main()

"""Doctor command — checks environment health.

Verifies Python version, required dependencies, and config validity.
"""

from __future__ import annotations

import importlib
import sys

from crazypumpkin.cli.errors import friendly_errors
from crazypumpkin.config.validation import validate_config
from crazypumpkin.config.env_override import resolve_env_overrides, list_active_overrides

# Required packages mapped to their import names
REQUIRED_DEPS: list[tuple[str, str]] = [
    ("pyyaml", "yaml"),
    ("fastapi", "fastapi"),
    ("uvicorn", "uvicorn"),
    ("httpx", "httpx"),
    ("anthropic", "anthropic"),
    ("jinja2", "jinja2"),
]

MIN_PYTHON = (3, 11)


def _check_python_version() -> tuple[bool, str]:
    """Check that the Python version meets the minimum requirement."""
    current = sys.version_info[:2]
    ok = current >= MIN_PYTHON
    label = f"{current[0]}.{current[1]}"
    if ok:
        return True, f"Python {label} >= {MIN_PYTHON[0]}.{MIN_PYTHON[1]}"
    return False, f"Python {label} < {MIN_PYTHON[0]}.{MIN_PYTHON[1]} (requires >={MIN_PYTHON[0]}.{MIN_PYTHON[1]})"


def _check_dependencies() -> list[tuple[bool, str]]:
    """Check that each required dependency can be imported."""
    results: list[tuple[bool, str]] = []
    for pkg_name, import_name in REQUIRED_DEPS:
        try:
            importlib.import_module(import_name)
            results.append((True, f"{pkg_name} installed"))
        except ImportError:
            results.append((False, f"{pkg_name} not installed"))
    return results


def _check_config() -> tuple[bool, str]:
    """Validate that the config file loads without errors."""
    try:
        from crazypumpkin.framework.config import load_config
        load_config()
        return True, "config file is valid"
    except FileNotFoundError:
        return False, "no config file found (run 'crazypumpkin init')"
    except (ValueError, KeyError) as exc:
        return False, f"config invalid: {exc}"


def check_config_valid(config: dict) -> tuple[str, bool, str]:
    """Doctor check: validate config schema. Returns (check_name, passed, detail)."""
    result = validate_config(config)
    if result.valid:
        return ("Config schema", True, "OK")
    details = "; ".join(f"{e.path}: {e.message}" for e in result.errors)
    return ("Config schema", False, f"FAIL — {details}")


def check_env_overrides(config: dict) -> tuple[str, bool, str]:
    """Doctor check: report active env var overrides. Always passes, informational."""
    active = list_active_overrides(config)
    if not active:
        return ("Env overrides", True, "none active")
    lines = [f"{name}={value!r} -> {path}" for name, path, value in active]
    return ("Env overrides", True, "; ".join(lines))


def _check_validation() -> tuple[bool, str]:
    """Run schema validation and env-override checks on the loaded config."""
    try:
        from crazypumpkin.framework.config import load_config
        from crazypumpkin.config.validation import validate_config
        from crazypumpkin.config.env_override import resolve_env_overrides, list_active_overrides

        raw_config = load_config()
        config_dict = raw_config if isinstance(raw_config, dict) else raw_config.__dict__
        config_dict = resolve_env_overrides(config_dict)

        result = validate_config(config_dict)
        active = list_active_overrides(config_dict)

        if not result.valid:
            first_error = result.errors[0].message if result.errors else "unknown error"
            return False, f"config schema invalid: {first_error}"

        override_note = f" ({len(active)} env override(s) active)" if active else ""
        return True, f"config schema valid{override_note}"
    except FileNotFoundError:
        return True, "config schema check skipped (no config file)"
    except Exception as exc:
        return False, f"config validation error: {exc}"


@friendly_errors
def cmd_doctor(args) -> None:
    """Run environment health checks and print results."""
    all_passed = True

    # Python version
    ok, msg = _check_python_version()
    _print_check(ok, msg)
    if not ok:
        all_passed = False

    # Dependencies
    for ok, msg in _check_dependencies():
        _print_check(ok, msg)
        if not ok:
            all_passed = False

    # Config
    ok, msg = _check_config()
    _print_check(ok, msg)
    if not ok:
        all_passed = False

    # Config schema validation + env overrides
    ok, msg = _check_validation()
    _print_check(ok, msg)
    if not ok:
        all_passed = False

    # Structured schema + env-override checks (using loaded config dict)
    try:
        from crazypumpkin.framework.config import load_config
        raw_config = load_config()
        config_dict = raw_config if isinstance(raw_config, dict) else raw_config.__dict__

        name, passed, detail = check_config_valid(config_dict)
        status_label = "OK" if passed else "FAIL"
        print(f"  Config schema: {status_label}" + (f" — {detail}" if not passed else ""))
        if not passed:
            all_passed = False

        name, passed, detail = check_env_overrides(config_dict)
        print(f"  Env overrides: {detail}")
    except FileNotFoundError:
        print("  Config schema: SKIP (no config file)")
        print("  Env overrides: SKIP (no config file)")
    except Exception:
        pass

    # Summary
    if all_passed:
        print("\nAll checks passed.")
    else:
        print("\nSome checks failed. See above for details.")
        sys.exit(1)


def _print_check(ok: bool, message: str) -> None:
    """Print a single check result line."""
    status = "PASS" if ok else "FAIL"
    print(f"  [{status}] {message}")

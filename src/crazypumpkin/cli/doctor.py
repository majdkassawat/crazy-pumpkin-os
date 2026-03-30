"""Doctor command — checks environment health.

Verifies Python version, required dependencies, and config validity.
"""

from __future__ import annotations

import importlib
import sys

from crazypumpkin.cli.errors import friendly_errors

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

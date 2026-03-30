"""CLI error handling wrapper.

Provides a decorator that catches common exceptions and prints
user-friendly messages with suggested fixes and appropriate exit codes.
"""

from __future__ import annotations

import functools
import sys


# Maps exception types to (exit_code, friendly_message_factory).
# The factory receives the exception and returns (message, suggestion).
_ERROR_HANDLERS: list[tuple[type, int, callable]] = [
    (
        FileNotFoundError,
        2,
        lambda e: (
            f"File not found: {e}",
            "Check the path exists, or run 'crazypumpkin init' to set up a project.",
        ),
    ),
    (
        KeyError,
        3,
        lambda e: (
            f"Missing configuration key: {e}",
            "Verify your config.yaml has all required fields. "
            "See examples/default.json for reference.",
        ),
    ),
    (
        ValueError,
        4,
        lambda e: (
            f"Invalid value: {e}",
            "Check your configuration for typos or missing required fields.",
        ),
    ),
    (
        PermissionError,
        5,
        lambda e: (
            f"Permission denied: {e}",
            "Check file permissions or run with appropriate privileges.",
        ),
    ),
    (
        ConnectionError,
        6,
        lambda e: (
            f"Connection error: {e}",
            "Check your network connection and API endpoint settings.",
        ),
    ),
    (
        ImportError,
        7,
        lambda e: (
            f"Missing dependency: {e}",
            "Install missing packages with 'pip install crazypumpkin[all]'.",
        ),
    ),
]

_HANDLED_EXCEPTIONS = tuple(exc_type for exc_type, _, _ in _ERROR_HANDLERS)


def friendly_errors(func):
    """Decorator that catches common exceptions and prints user-friendly messages.

    Wraps a CLI command function so that expected exceptions are caught,
    a helpful error message and suggestion are printed to stderr, and the
    process exits with a non-zero exit code.

    Keyboard interrupts are handled gracefully with exit code 130.
    Unexpected exceptions are re-raised.
    """

    @functools.wraps(func)
    def wrapper(*args, **kwargs):
        try:
            return func(*args, **kwargs)
        except KeyboardInterrupt:
            print("\nInterrupted.", file=sys.stderr)
            sys.exit(130)
        except SystemExit:
            raise
        except _HANDLED_EXCEPTIONS as exc:
            for exc_type, exit_code, factory in _ERROR_HANDLERS:
                if isinstance(exc, exc_type):
                    message, suggestion = factory(exc)
                    print(f"Error: {message}", file=sys.stderr)
                    print(f"Hint: {suggestion}", file=sys.stderr)
                    sys.exit(exit_code)

    return wrapper

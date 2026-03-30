"""Plugin sandboxing with resource limits for the Crazy Pumpkin framework.

Wraps plugin execution with configurable timeout and memory caps.
Prevents plugins from importing framework internal modules.
"""

from __future__ import annotations

import builtins
import logging
import sys
import threading
import traceback
from dataclasses import dataclass, field
from typing import Any, Callable

logger = logging.getLogger("crazypumpkin.plugins.sandbox")

# Modules that plugins are allowed to import from the framework.
# Everything else under ``crazypumpkin`` is considered internal.
PUBLIC_API_MODULES = frozenset({
    "crazypumpkin",
    "crazypumpkin.framework",
    "crazypumpkin.framework.models",
    "crazypumpkin.framework.events",
    "crazypumpkin.framework.registry",
})

# Prefixes that are considered internal when not in the public list.
_INTERNAL_PREFIX = "crazypumpkin."

DEFAULT_TIMEOUT_SEC = 60
DEFAULT_MEMORY_LIMIT_MB = 256


@dataclass
class SandboxConfig:
    """Configuration for the plugin sandbox."""

    timeout_sec: float = DEFAULT_TIMEOUT_SEC
    memory_limit_mb: int = DEFAULT_MEMORY_LIMIT_MB
    allowed_modules: frozenset[str] = field(default_factory=lambda: PUBLIC_API_MODULES)


class PluginTimeoutError(Exception):
    """Raised when a plugin exceeds its execution timeout."""

    def __init__(self, plugin_name: str, timeout: float) -> None:
        self.plugin_name = plugin_name
        self.timeout = timeout
        super().__init__(
            f"Plugin '{plugin_name}' exceeded timeout of {timeout}s"
        )


class PluginMemoryError(Exception):
    """Raised when a plugin exceeds its memory limit."""

    def __init__(self, plugin_name: str, usage_mb: float, limit_mb: int) -> None:
        self.plugin_name = plugin_name
        self.usage_mb = usage_mb
        self.limit_mb = limit_mb
        super().__init__(
            f"Plugin '{plugin_name}' exceeded memory limit: "
            f"{usage_mb:.1f}MB used, {limit_mb}MB allowed"
        )


class PluginImportError(Exception):
    """Raised when a plugin tries to import a restricted module."""

    def __init__(self, plugin_name: str, module_name: str) -> None:
        self.plugin_name = plugin_name
        self.module_name = module_name
        super().__init__(
            f"Plugin '{plugin_name}' attempted to import restricted module '{module_name}'"
        )


def _get_memory_usage_mb() -> float:
    """Return the current process memory usage in MB.

    Uses ``psutil`` if available, otherwise falls back to a
    platform-specific approach.  Returns 0.0 when measurement is not
    possible.
    """
    try:
        import psutil  # type: ignore[import-untyped]
        process = psutil.Process()
        return process.memory_info().rss / (1024 * 1024)
    except ImportError:
        pass

    # Fallback: try resource module (Unix only)
    try:
        import resource
        usage = resource.getrusage(resource.RUSAGE_SELF)
        # ru_maxrss is in KB on Linux, bytes on macOS
        if sys.platform == "darwin":
            return usage.ru_maxrss / (1024 * 1024)
        return usage.ru_maxrss / 1024
    except (ImportError, AttributeError):
        pass

    return 0.0


def create_import_guard(
    plugin_name: str,
    allowed_modules: frozenset[str] = PUBLIC_API_MODULES,
) -> Callable[..., Any]:
    """Create a guarded ``__import__`` that blocks internal framework modules.

    Returns a replacement for ``builtins.__import__`` that raises
    :class:`PluginImportError` when the plugin tries to import a
    ``crazypumpkin.*`` module not in *allowed_modules*.

    Transitive imports triggered by allowed modules are permitted so
    that e.g. ``crazypumpkin.framework.__init__`` can import its own
    submodules without being blocked.
    """
    original_import = builtins.__import__
    _depth = threading.local()

    def _guarded_import(name: str, *args: Any, **kwargs: Any) -> Any:
        depth = getattr(_depth, "value", 0)
        if depth == 0 and (name.startswith(_INTERNAL_PREFIX) or name == "crazypumpkin"):
            if name not in allowed_modules:
                raise PluginImportError(plugin_name, name)
        _depth.value = depth + 1
        try:
            return original_import(name, *args, **kwargs)
        finally:
            _depth.value = depth

    return _guarded_import


def check_memory(plugin_name: str, limit_mb: int) -> None:
    """Check current process memory and raise if over *limit_mb*."""
    usage = _get_memory_usage_mb()
    if usage > 0 and usage > limit_mb:
        raise PluginMemoryError(plugin_name, usage, limit_mb)


def run_sandboxed(
    plugin_name: str,
    func: Callable[..., Any],
    args: tuple[Any, ...] = (),
    kwargs: dict[str, Any] | None = None,
    config: SandboxConfig | None = None,
) -> Any:
    """Execute *func* inside a sandbox with resource limits.

    Args:
        plugin_name: Human-readable name of the plugin (for logging/errors).
        func: The callable to execute.
        args: Positional arguments for *func*.
        kwargs: Keyword arguments for *func*.
        config: Sandbox configuration.  Uses defaults when ``None``.

    Returns:
        The return value of *func*.

    Raises:
        PluginTimeoutError: If execution exceeds the configured timeout.
        PluginMemoryError: If memory usage exceeds the configured cap.
        PluginImportError: If the plugin tries to import restricted modules.
    """
    if kwargs is None:
        kwargs = {}
    if config is None:
        config = SandboxConfig()

    result: Any = None
    exception: BaseException | None = None

    # Capture the real import before any guard is installed.
    saved_import = builtins.__import__
    guarded_import = create_import_guard(plugin_name, config.allowed_modules)

    def _target() -> None:
        nonlocal result, exception
        try:
            builtins.__import__ = guarded_import  # type: ignore[assignment]

            # Pre-flight memory check
            check_memory(plugin_name, config.memory_limit_mb)

            result = func(*args, **kwargs)

            # Post-flight memory check
            check_memory(plugin_name, config.memory_limit_mb)
        except BaseException as exc:
            exception = exc
        finally:
            builtins.__import__ = saved_import  # type: ignore[assignment]

    thread = threading.Thread(target=_target, daemon=True)
    thread.start()
    thread.join(timeout=config.timeout_sec)

    # Always restore import on the main thread in case the worker
    # thread timed out and hasn't reached its finally block yet.
    builtins.__import__ = saved_import  # type: ignore[assignment]

    if thread.is_alive():
        logger.error(
            "Plugin '%s' timed out after %ss", plugin_name, config.timeout_sec
        )
        raise PluginTimeoutError(plugin_name, config.timeout_sec)

    if exception is not None:
        logger.error(
            "Plugin '%s' raised an exception: %s",
            plugin_name,
            exception,
        )
        raise exception

    return result

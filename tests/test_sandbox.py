"""Unit tests for crazypumpkin.plugins.sandbox.

Tests cover:
- SandboxConfig defaults and customisation
- Timeout enforcement via run_sandboxed
- Memory limit checking
- Import guard blocking internal framework modules
- Import guard allowing public API modules
- run_sandboxed propagating plugin exceptions
"""

import importlib
import sys
import time
from pathlib import Path
from unittest.mock import patch

import pytest

_src = str(Path(__file__).resolve().parent.parent / "src")
if _src not in sys.path:
    sys.path.insert(0, _src)

_sandbox_mod = importlib.import_module("crazypumpkin.plugins.sandbox")

SandboxConfig = _sandbox_mod.SandboxConfig
PluginTimeoutError = _sandbox_mod.PluginTimeoutError
PluginMemoryError = _sandbox_mod.PluginMemoryError
PluginImportError = _sandbox_mod.PluginImportError
run_sandboxed = _sandbox_mod.run_sandboxed
create_import_guard = _sandbox_mod.create_import_guard
check_memory = _sandbox_mod.check_memory
PUBLIC_API_MODULES = _sandbox_mod.PUBLIC_API_MODULES
DEFAULT_TIMEOUT_SEC = _sandbox_mod.DEFAULT_TIMEOUT_SEC
DEFAULT_MEMORY_LIMIT_MB = _sandbox_mod.DEFAULT_MEMORY_LIMIT_MB


# -- SandboxConfig ------------------------------------------------------------


class TestSandboxConfig:
    """SandboxConfig dataclass defaults and customisation."""

    def test_defaults(self):
        cfg = SandboxConfig()
        assert cfg.timeout_sec == DEFAULT_TIMEOUT_SEC
        assert cfg.memory_limit_mb == DEFAULT_MEMORY_LIMIT_MB
        assert cfg.allowed_modules == PUBLIC_API_MODULES

    def test_custom_values(self):
        cfg = SandboxConfig(timeout_sec=10, memory_limit_mb=128)
        assert cfg.timeout_sec == 10
        assert cfg.memory_limit_mb == 128

    def test_custom_allowed_modules(self):
        custom = frozenset({"crazypumpkin.framework.models"})
        cfg = SandboxConfig(allowed_modules=custom)
        assert cfg.allowed_modules == custom


# -- Timeout enforcement -------------------------------------------------------


class TestTimeoutEnforcement:
    """run_sandboxed enforces timeout on plugin execution."""

    def test_fast_function_succeeds(self):
        result = run_sandboxed(
            "fast-plugin",
            lambda: 42,
            config=SandboxConfig(timeout_sec=5),
        )
        assert result == 42

    def test_slow_function_times_out(self):
        def slow():
            time.sleep(10)
            return "done"

        with pytest.raises(PluginTimeoutError) as exc_info:
            run_sandboxed(
                "slow-plugin",
                slow,
                config=SandboxConfig(timeout_sec=0.5),
            )
        assert "slow-plugin" in str(exc_info.value)
        assert exc_info.value.plugin_name == "slow-plugin"
        assert exc_info.value.timeout == 0.5

    def test_timeout_default_is_60(self):
        cfg = SandboxConfig()
        assert cfg.timeout_sec == 60

    def test_function_with_args(self):
        def add(a, b):
            return a + b

        result = run_sandboxed(
            "adder",
            add,
            args=(3, 4),
            config=SandboxConfig(timeout_sec=5),
        )
        assert result == 7

    def test_function_with_kwargs(self):
        def greet(name="world"):
            return f"hello {name}"

        result = run_sandboxed(
            "greeter",
            greet,
            kwargs={"name": "plugin"},
            config=SandboxConfig(timeout_sec=5),
        )
        assert result == "hello plugin"


# -- Memory limit checking ----------------------------------------------------


class TestMemoryLimits:
    """check_memory and run_sandboxed enforce memory caps."""

    def test_check_memory_under_limit(self):
        # Should not raise with a very high limit
        check_memory("test-plugin", 999999)

    def test_check_memory_over_limit_raises(self):
        with patch(
            "crazypumpkin.plugins.sandbox._get_memory_usage_mb",
            return_value=512.0,
        ):
            with pytest.raises(PluginMemoryError) as exc_info:
                check_memory("big-plugin", 256)
            assert exc_info.value.plugin_name == "big-plugin"
            assert exc_info.value.usage_mb == 512.0
            assert exc_info.value.limit_mb == 256

    def test_run_sandboxed_pre_flight_memory_check(self):
        with patch(
            "crazypumpkin.plugins.sandbox._get_memory_usage_mb",
            return_value=600.0,
        ):
            with pytest.raises(PluginMemoryError):
                run_sandboxed(
                    "mem-hog",
                    lambda: "ok",
                    config=SandboxConfig(memory_limit_mb=256),
                )

    def test_run_sandboxed_post_flight_memory_check(self):
        call_count = 0

        def _mock_memory():
            nonlocal call_count
            call_count += 1
            if call_count <= 1:
                return 100.0  # pre-flight OK
            return 600.0  # post-flight exceeds

        with patch(
            "crazypumpkin.plugins.sandbox._get_memory_usage_mb",
            side_effect=_mock_memory,
        ):
            with pytest.raises(PluginMemoryError):
                run_sandboxed(
                    "leak-plugin",
                    lambda: "allocated lots of memory",
                    config=SandboxConfig(memory_limit_mb=256),
                )

    def test_zero_memory_reading_skips_check(self):
        # When _get_memory_usage_mb returns 0, check should not raise
        with patch(
            "crazypumpkin.plugins.sandbox._get_memory_usage_mb",
            return_value=0.0,
        ):
            check_memory("test-plugin", 1)  # Should not raise


# -- Import guard --------------------------------------------------------------


class TestImportGuard:
    """create_import_guard blocks internal framework imports."""

    def test_blocks_internal_module(self):
        guard = create_import_guard("evil-plugin")
        with pytest.raises(PluginImportError) as exc_info:
            guard("crazypumpkin.framework.store")
        assert exc_info.value.plugin_name == "evil-plugin"
        assert exc_info.value.module_name == "crazypumpkin.framework.store"

    def test_blocks_deep_internal_module(self):
        guard = create_import_guard("evil-plugin")
        with pytest.raises(PluginImportError):
            guard("crazypumpkin.framework.config")

    def test_allows_public_api_module(self):
        guard = create_import_guard("good-plugin")
        # Should not raise for public modules — we patch builtins.__import__
        # to prevent actual import side effects
        import builtins
        original = builtins.__import__
        try:
            builtins.__import__ = guard  # type: ignore[assignment]
            # Importing a module already in sys.modules is safe
            import crazypumpkin.framework.models  # noqa: F401
        finally:
            builtins.__import__ = original  # type: ignore[assignment]

    def test_allows_non_framework_modules(self):
        guard = create_import_guard("good-plugin")
        # Standard library imports should pass through
        result = guard("json")
        import json
        assert result is json

    def test_blocks_plugin_loader_import(self):
        guard = create_import_guard("nosy-plugin")
        with pytest.raises(PluginImportError):
            guard("crazypumpkin.framework.plugin_loader")

    def test_blocks_cli_import(self):
        guard = create_import_guard("nosy-plugin")
        with pytest.raises(PluginImportError):
            guard("crazypumpkin.cli")

    def test_custom_allowed_modules(self):
        custom = frozenset({"crazypumpkin.framework.store"})
        guard = create_import_guard("custom-plugin", allowed_modules=custom)
        # Should block what's not in custom set
        with pytest.raises(PluginImportError):
            guard("crazypumpkin.framework.models")
        # store is allowed — should call through to real import
        # (store is already imported so this is safe)
        result = guard("crazypumpkin.framework.store")
        assert result is not None


# -- run_sandboxed exception propagation ---------------------------------------


class TestRunSandboxedExceptions:
    """run_sandboxed propagates exceptions from plugin code."""

    def test_propagates_value_error(self):
        def bad():
            raise ValueError("plugin error")

        with pytest.raises(ValueError, match="plugin error"):
            run_sandboxed(
                "bad-plugin",
                bad,
                config=SandboxConfig(timeout_sec=5),
            )

    def test_propagates_runtime_error(self):
        def crash():
            raise RuntimeError("boom")

        with pytest.raises(RuntimeError, match="boom"):
            run_sandboxed(
                "crash-plugin",
                crash,
                config=SandboxConfig(timeout_sec=5),
            )

    def test_returns_none_from_void_function(self):
        def void():
            pass

        result = run_sandboxed(
            "void-plugin",
            void,
            config=SandboxConfig(timeout_sec=5),
        )
        assert result is None

    def test_import_error_in_sandboxed(self):
        def imports_internal():
            import crazypumpkin.framework.store  # noqa: F401

        with pytest.raises(PluginImportError):
            run_sandboxed(
                "import-plugin",
                imports_internal,
                config=SandboxConfig(timeout_sec=5),
            )


# -- Integration: run_sandboxed with all limits --------------------------------


class TestSandboxIntegration:
    """Integration tests combining timeout, memory, and import restrictions."""

    def test_successful_execution_returns_value(self):
        def compute():
            return sum(range(100))

        result = run_sandboxed(
            "compute-plugin",
            compute,
            config=SandboxConfig(timeout_sec=10, memory_limit_mb=999999),
        )
        assert result == 4950

    def test_default_config_used_when_none(self):
        result = run_sandboxed("simple", lambda: "ok")
        assert result == "ok"

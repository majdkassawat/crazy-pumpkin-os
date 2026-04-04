"""Tests for crazypumpkin.plugins public API exports."""

import importlib


def test_import_core_names():
    """Core names import without ImportError."""
    from crazypumpkin.plugins import discover_plugins, load_plugin, PluginLifecycleManager

    assert callable(discover_plugins)
    assert callable(load_plugin)
    assert PluginLifecycleManager is not None


def test_import_validation_and_sandbox():
    """validate_plugin, run_sandboxed, SandboxConfig import correctly."""
    from crazypumpkin.plugins import validate_plugin, run_sandboxed, SandboxConfig

    assert callable(validate_plugin)
    assert callable(run_sandboxed)
    assert SandboxConfig is not None


def test_all_has_at_least_four_symbols():
    """__all__ contains at least 4 symbols."""
    import crazypumpkin.plugins as pkg

    assert hasattr(pkg, "__all__")
    assert len(pkg.__all__) >= 4


def test_init_is_not_empty():
    """plugins/__init__.py is no longer empty."""
    import crazypumpkin.plugins as pkg
    import pathlib

    init_path = pathlib.Path(pkg.__file__)
    assert init_path.stat().st_size > 0


def test_all_entries_are_importable():
    """Every name listed in __all__ is accessible on the module."""
    import crazypumpkin.plugins as pkg

    for name in pkg.__all__:
        assert hasattr(pkg, name), f"{name} listed in __all__ but not importable"

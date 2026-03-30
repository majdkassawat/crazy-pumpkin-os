"""Tests for crazypumpkin.config.migration."""

import importlib
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

_mig = importlib.import_module("crazypumpkin.config.migration")
migrate_config = _mig.migrate_config
register_migration = _mig.register_migration
clear_migrations = _mig.clear_migrations


@pytest.fixture(autouse=True)
def _clean_registry():
    """Ensure each test starts with a clean migration registry."""
    clear_migrations()
    yield
    clear_migrations()


def test_single_step_migration():
    """migrate_config applies a single registered transform."""
    @register_migration("1.0", "2.0")
    def _v1_to_v2(cfg):
        cfg["new_field"] = True
        return cfg

    result = migrate_config("1.0", "2.0", {"old_field": 1})
    assert result["version"] == "2.0"
    assert result["new_field"] is True
    assert result["old_field"] == 1


def test_multi_step_migration():
    """migrate_config('1.0', '3.0') chains through 1.0 -> 2.0 -> 3.0."""
    @register_migration("1.0", "2.0")
    def _v1_to_v2(cfg):
        cfg["step1"] = True
        return cfg

    @register_migration("2.0", "3.0")
    def _v2_to_v3(cfg):
        cfg["step2"] = True
        return cfg

    result = migrate_config("1.0", "3.0", {"data": "hello"})
    assert result["version"] == "3.0"
    assert result["step1"] is True
    assert result["step2"] is True
    assert result["data"] == "hello"


def test_no_migration_path_raises():
    """ValueError is raised when no path exists between versions."""
    @register_migration("1.0", "2.0")
    def _v1_to_v2(cfg):
        return cfg

    with pytest.raises(ValueError, match="No migration path"):
        migrate_config("1.0", "5.0")


def test_same_version_noop():
    """Migrating from a version to itself returns the config unchanged."""
    config = {"key": "value"}
    result = migrate_config("1.0", "1.0", config)
    assert result["version"] == "1.0"
    assert result["key"] == "value"


def test_no_config_defaults_to_empty():
    """When config is None, starts with an empty dict."""
    @register_migration("1.0", "2.0")
    def _v1_to_v2(cfg):
        cfg["added"] = 42
        return cfg

    result = migrate_config("1.0", "2.0")
    assert result["version"] == "2.0"
    assert result["added"] == 42


def test_version_field_updated():
    """The version field reflects the target version after migration."""
    @register_migration("1.0", "2.0")
    def _v1_to_v2(cfg):
        return cfg

    result = migrate_config("1.0", "2.0", {"version": "1.0"})
    assert result["version"] == "2.0"


def test_unregistered_source_version_raises():
    """ValueError when source version has no outgoing migrations."""
    with pytest.raises(ValueError, match="No migration path"):
        migrate_config("0.1", "1.0")


def test_long_chain_migration():
    """migrate_config chains through 4 sequential steps."""
    @register_migration("1.0", "2.0")
    def _v1_to_v2(cfg):
        cfg["steps"] = [1]
        return cfg

    @register_migration("2.0", "3.0")
    def _v2_to_v3(cfg):
        cfg["steps"].append(2)
        return cfg

    @register_migration("3.0", "4.0")
    def _v3_to_v4(cfg):
        cfg["steps"].append(3)
        return cfg

    @register_migration("4.0", "5.0")
    def _v4_to_v5(cfg):
        cfg["steps"].append(4)
        return cfg

    result = migrate_config("1.0", "5.0")
    assert result["version"] == "5.0"
    assert result["steps"] == [1, 2, 3, 4]


def test_skip_version_no_shortcut_raises():
    """Skipping versions without a direct migration path raises ValueError."""
    @register_migration("1.0", "2.0")
    def _v1_to_v2(cfg):
        return cfg

    @register_migration("3.0", "4.0")
    def _v3_to_v4(cfg):
        return cfg

    with pytest.raises(ValueError, match="No migration path"):
        migrate_config("1.0", "4.0")


def test_original_config_not_mutated():
    """The original config dict is not mutated by migration."""
    @register_migration("1.0", "2.0")
    def _v1_to_v2(cfg):
        cfg["added"] = True
        return cfg

    original = {"key": "value"}
    result = migrate_config("1.0", "2.0", original)
    assert "added" in result
    assert "added" not in original


def test_same_version_noop_preserves_all_keys():
    """Idempotent migration preserves all existing config keys."""
    config = {"a": 1, "b": [2, 3], "nested": {"c": 4}}
    result = migrate_config("2.0", "2.0", config)
    assert result["a"] == 1
    assert result["b"] == [2, 3]
    assert result["nested"] == {"c": 4}
    assert result["version"] == "2.0"


def test_clear_migrations_resets_registry():
    """After clear_migrations, previously registered paths are gone."""
    @register_migration("1.0", "2.0")
    def _v1_to_v2(cfg):
        return cfg

    # Works before clear
    migrate_config("1.0", "2.0")

    clear_migrations()

    with pytest.raises(ValueError, match="No migration path"):
        migrate_config("1.0", "2.0")


def test_unknown_target_version_raises():
    """ValueError when target version is not reachable from any registered migration."""
    @register_migration("1.0", "2.0")
    def _v1_to_v2(cfg):
        return cfg

    with pytest.raises(ValueError, match="No migration path"):
        migrate_config("1.0", "99.0")


def test_unknown_source_and_target_raises():
    """ValueError when both source and target are completely unknown."""
    @register_migration("1.0", "2.0")
    def _v1_to_v2(cfg):
        return cfg

    with pytest.raises(ValueError, match="No migration path"):
        migrate_config("X.0", "Y.0")


def test_reverse_migration_not_supported():
    """Migrations are one-directional; reverse path raises ValueError."""
    @register_migration("1.0", "2.0")
    def _v1_to_v2(cfg):
        return cfg

    with pytest.raises(ValueError, match="No migration path"):
        migrate_config("2.0", "1.0")


def test_migration_transforms_data_cumulatively():
    """Each step builds on the result of the previous step."""
    @register_migration("1.0", "2.0")
    def _v1_to_v2(cfg):
        cfg["counter"] = cfg.get("counter", 0) + 10
        return cfg

    @register_migration("2.0", "3.0")
    def _v2_to_v3(cfg):
        cfg["counter"] = cfg["counter"] * 2
        return cfg

    result = migrate_config("1.0", "3.0", {"counter": 5})
    # step1: 5 + 10 = 15, step2: 15 * 2 = 30
    assert result["counter"] == 30
    assert result["version"] == "3.0"


def test_migration_with_key_rename():
    """Migration can rename keys between versions."""
    @register_migration("1.0", "2.0")
    def _v1_to_v2(cfg):
        if "old_name" in cfg:
            cfg["new_name"] = cfg.pop("old_name")
        return cfg

    result = migrate_config("1.0", "2.0", {"old_name": "hello"})
    assert "old_name" not in result
    assert result["new_name"] == "hello"


def test_migration_partial_chain_start_mid():
    """Migrating from a middle version to the end works."""
    @register_migration("1.0", "2.0")
    def _v1_to_v2(cfg):
        cfg["s1"] = True
        return cfg

    @register_migration("2.0", "3.0")
    def _v2_to_v3(cfg):
        cfg["s2"] = True
        return cfg

    @register_migration("3.0", "4.0")
    def _v3_to_v4(cfg):
        cfg["s3"] = True
        return cfg

    result = migrate_config("2.0", "4.0")
    assert result["version"] == "4.0"
    assert "s1" not in result
    assert result["s2"] is True
    assert result["s3"] is True


def test_empty_registry_same_version_ok():
    """Same-version migration works even with no registered migrations."""
    result = migrate_config("1.0", "1.0", {"x": 1})
    assert result["version"] == "1.0"
    assert result["x"] == 1


def test_empty_registry_different_versions_raises():
    """Different versions with no registered migrations raises ValueError."""
    with pytest.raises(ValueError, match="No migration path"):
        migrate_config("1.0", "2.0")


def test_register_migration_stores_in_registry():
    """register_migration decorator registers a step in _migrations."""
    @register_migration("1.0", "2.0")
    def _v1_to_v2(cfg):
        return cfg

    assert ("1.0", "2.0") in _mig._migrations
    assert _mig._migrations[("1.0", "2.0")] is _v1_to_v2


def test_clear_migrations_empties_both_internals():
    """clear_migrations() empties both _migrations and _version_order."""
    @register_migration("1.0", "2.0")
    def _v1_to_v2(cfg):
        return cfg

    assert len(_mig._migrations) > 0
    assert len(_mig._version_order) > 0

    clear_migrations()

    assert _mig._migrations == {}
    assert _mig._version_order == []

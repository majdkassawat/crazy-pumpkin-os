"""Tests for PipelineConfig.apply_reload — field-level diff and event dispatch."""

import importlib
import sys
from pathlib import Path
from unittest.mock import MagicMock, call

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

_config_mod = importlib.import_module("crazypumpkin.framework.config")
_events_mod = importlib.import_module("crazypumpkin.framework.events")

PipelineConfig = _config_mod.PipelineConfig
ConfigChange = _config_mod.ConfigChange
CONFIG_RELOADED = _events_mod.CONFIG_RELOADED
EventBus = _events_mod.EventBus


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _base_config() -> dict:
    """Return a minimal valid config dict."""
    return {
        "company": {"name": "TestCo"},
        "products": [{"name": "app", "workspace": "./products/app"}],
        "agents": [{"name": "Dev", "role": "execution"}],
        "pipeline": {"cycle_interval": 30},
    }


# ---------------------------------------------------------------------------
# apply_reload — basic diff
# ---------------------------------------------------------------------------


class TestApplyReloadDiff:
    """apply_reload returns correct ConfigChange list for modified fields."""

    def test_returns_changes_for_modified_fields(self):
        cfg = PipelineConfig(**_base_config())
        new_raw = _base_config()
        new_raw["company"] = {"name": "UpdatedCo"}
        new_raw["pipeline"] = {"cycle_interval": 60}

        changes = cfg.apply_reload(new_raw)

        changed_fields = {c.field for c in changes}
        assert "company" in changed_fields
        assert "pipeline" in changed_fields

    def test_old_and_new_values_correct(self):
        cfg = PipelineConfig(**_base_config())
        old_company = cfg.company.copy()
        new_raw = _base_config()
        new_raw["company"] = {"name": "NewCo"}

        changes = cfg.apply_reload(new_raw)

        company_change = next(c for c in changes if c.field == "company")
        assert company_change.old_value == old_company
        assert company_change.new_value == {"name": "NewCo"}

    def test_config_updated_after_reload(self):
        cfg = PipelineConfig(**_base_config())
        new_raw = _base_config()
        new_raw["company"] = {"name": "NewCo"}

        cfg.apply_reload(new_raw)

        assert cfg.company == {"name": "NewCo"}

    def test_multiple_fields_changed(self):
        cfg = PipelineConfig(**_base_config())
        new_raw = _base_config()
        new_raw["company"] = {"name": "X"}
        new_raw["dashboard"] = {"port": 9000}
        new_raw["voice"] = {"enabled": True}

        changes = cfg.apply_reload(new_raw)

        changed_fields = {c.field for c in changes}
        assert "company" in changed_fields
        assert "dashboard" in changed_fields
        assert "voice" in changed_fields


# ---------------------------------------------------------------------------
# apply_reload — unchanged fields excluded
# ---------------------------------------------------------------------------


class TestApplyReloadUnchanged:
    """Unchanged fields are not included in the changes list."""

    def test_unchanged_fields_not_in_changes(self):
        cfg = PipelineConfig(**_base_config())
        new_raw = _base_config()
        # Only change company
        new_raw["company"] = {"name": "ChangedCo"}

        changes = cfg.apply_reload(new_raw)

        changed_fields = {c.field for c in changes}
        assert "products" not in changed_fields
        assert "agents" not in changed_fields

    def test_identical_config_returns_empty_list(self):
        base = _base_config()
        cfg = PipelineConfig(**base)

        changes = cfg.apply_reload(base)

        assert changes == []

    def test_identical_config_does_not_modify_state(self):
        base = _base_config()
        cfg = PipelineConfig(**base)
        original_company = cfg.company.copy()

        cfg.apply_reload(base)

        assert cfg.company == original_company


# ---------------------------------------------------------------------------
# apply_reload — validation
# ---------------------------------------------------------------------------


class TestApplyReloadValidation:
    """Invalid new config raises ValidationError without modifying current config."""

    def test_invalid_config_raises_validation_error(self):
        from pydantic import ValidationError

        cfg = PipelineConfig(**_base_config())
        # company should be a dict, not an int
        bad_raw = _base_config()
        bad_raw["company"] = "not-a-dict"

        with pytest.raises(ValidationError):
            cfg.apply_reload(bad_raw)

    def test_invalid_config_leaves_state_untouched(self):
        from pydantic import ValidationError

        base = _base_config()
        cfg = PipelineConfig(**base)
        original_company = cfg.company.copy()

        bad_raw = _base_config()
        bad_raw["company"] = 12345  # wrong type

        with pytest.raises(ValidationError):
            cfg.apply_reload(bad_raw)

        assert cfg.company == original_company

    def test_invalid_agents_type_raises(self):
        from pydantic import ValidationError

        cfg = PipelineConfig(**_base_config())
        bad_raw = _base_config()
        bad_raw["agents"] = "not-a-list"

        with pytest.raises(ValidationError):
            cfg.apply_reload(bad_raw)


# ---------------------------------------------------------------------------
# apply_reload — event bus emission
# ---------------------------------------------------------------------------


class TestApplyReloadEventBus:
    """config.reloaded event is emitted on the event bus with changes payload."""

    def test_event_emitted_on_changes(self):
        cfg = PipelineConfig(**_base_config())
        bus = MagicMock(spec=EventBus)
        new_raw = _base_config()
        new_raw["company"] = {"name": "EventCo"}

        cfg.apply_reload(new_raw, event_bus=bus)

        bus.emit.assert_called_once()
        call_kwargs = bus.emit.call_args
        assert call_kwargs.kwargs.get("action") or call_kwargs[1].get("action") == CONFIG_RELOADED

    def test_event_contains_changes_metadata(self):
        cfg = PipelineConfig(**_base_config())
        bus = MagicMock(spec=EventBus)
        new_raw = _base_config()
        new_raw["company"] = {"name": "MetaCo"}

        cfg.apply_reload(new_raw, event_bus=bus)

        call_kwargs = bus.emit.call_args
        # Get metadata from kwargs or positional
        metadata = call_kwargs.kwargs.get("metadata") or call_kwargs[1].get("metadata")
        assert "changes" in metadata
        assert len(metadata["changes"]) >= 1
        assert metadata["changes"][0]["field"] == "company"

    def test_no_event_when_nothing_changed(self):
        cfg = PipelineConfig(**_base_config())
        bus = MagicMock(spec=EventBus)

        cfg.apply_reload(_base_config(), event_bus=bus)

        bus.emit.assert_not_called()

    def test_no_event_when_no_bus_provided(self):
        cfg = PipelineConfig(**_base_config())
        new_raw = _base_config()
        new_raw["company"] = {"name": "NoBusCo"}

        # Should not raise even without event_bus
        changes = cfg.apply_reload(new_raw)
        assert len(changes) >= 1

    def test_event_action_is_config_reloaded_constant(self):
        assert CONFIG_RELOADED == "config.reloaded"

    def test_event_agent_id_is_system(self):
        cfg = PipelineConfig(**_base_config())
        bus = MagicMock(spec=EventBus)
        new_raw = _base_config()
        new_raw["pipeline"] = {"cycle_interval": 99}

        cfg.apply_reload(new_raw, event_bus=bus)

        call_kwargs = bus.emit.call_args
        agent_id = call_kwargs.kwargs.get("agent_id") or call_kwargs[1].get("agent_id")
        assert agent_id == "system"

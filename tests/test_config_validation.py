"""Tests for crazypumpkin.config.validation — ConfigSchema validator."""

import importlib
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

_val = importlib.import_module("crazypumpkin.config.validation")
validate_config = _val.validate_config
get_default_schema = _val.get_default_schema
ValidationResult = _val.ValidationResult
ValidationError = _val.ValidationError


def _minimal_valid() -> dict:
    """Return a minimal config dict that passes validation."""
    return {
        "company": {"name": "TestCo"},
        "agents": [{"name": "Dev", "role": "execution"}],
    }


# -- valid config ---------------------------------------------------------------


def test_valid_config_returns_valid_true():
    """validate_config returns ValidationResult with valid=True for a correct config."""
    result = validate_config(_minimal_valid())
    assert isinstance(result, ValidationResult)
    assert result.valid is True
    assert result.errors == []


def test_valid_full_config():
    """A complete config matching all PipelineConfig sections validates cleanly."""
    config = {
        "company": {"name": "TestCo"},
        "products": [{"name": "App", "workspace": "./products/app"}],
        "agents": [{"name": "Dev", "role": "execution"}],
        "triggers": [{"name": "daily", "type": "cron", "schedule": "0 9 * * *"}],
        "notifications": {"providers": [], "enabled": True},
        "llm": {"default_provider": "anthropic_api", "providers": {}, "agent_models": {}},
        "observability": {"enabled": True, "exporters": []},
        "scheduler": {"enabled": True, "interval": 60},
        "plugins": [{"name": "myplugin", "enabled": True}],
        "dashboard": {"port": 8500, "host": "127.0.0.1"},
        "pipeline": {"cycle_interval": 30},
        "voice": {"enabled": False},
    }
    result = validate_config(config)
    assert result.valid is True
    assert result.errors == []


# -- required field enforcement -------------------------------------------------


def test_missing_agents_returns_invalid():
    """validate_config returns valid=False when required 'agents' is missing."""
    config = {"company": {"name": "TestCo"}}
    result = validate_config(config)
    assert result.valid is False
    assert len(result.errors) >= 1
    agent_errors = [e for e in result.errors if "agents" in e.path]
    assert len(agent_errors) >= 1


def test_missing_company_returns_invalid():
    """validate_config returns valid=False when required 'company' is missing."""
    config = {"agents": [{"name": "Dev", "role": "execution"}]}
    result = validate_config(config)
    assert result.valid is False
    company_errors = [e for e in result.errors if "company" in e.path]
    assert len(company_errors) >= 1


def test_missing_company_name_returns_invalid():
    """validate_config catches missing required nested field company.name."""
    config = {
        "company": {},
        "agents": [{"name": "Dev", "role": "execution"}],
    }
    result = validate_config(config)
    assert result.valid is False
    name_errors = [e for e in result.errors if e.path == "company.name"]
    assert len(name_errors) >= 1


def test_missing_agent_name_returns_error():
    """An agent dict without 'name' produces an error at the correct path."""
    config = {
        "company": {"name": "TestCo"},
        "agents": [{"role": "execution"}],
    }
    result = validate_config(config)
    assert result.valid is False
    name_errors = [e for e in result.errors if e.path == "agents.0.name"]
    assert len(name_errors) >= 1


def test_missing_agent_role_returns_error():
    """An agent dict without 'role' produces an error at the correct path."""
    config = {
        "company": {"name": "TestCo"},
        "agents": [{"name": "Dev"}],
    }
    result = validate_config(config)
    assert result.valid is False
    role_errors = [e for e in result.errors if e.path == "agents.0.role"]
    assert len(role_errors) >= 1


# -- dotted path for nested field errors ----------------------------------------


def test_dotted_path_for_nested_agent_field():
    """ValidationError.path shows dotted path like 'agents.0.schedule' for nested errors."""
    config = {
        "company": {"name": "TestCo"},
        "agents": [
            {"name": "Dev", "role": "execution", "schedule": 123},  # wrong type
        ],
    }
    result = validate_config(config)
    # schedule should have type str but got int — this is a type error
    schedule_errors = [e for e in result.errors if e.path == "agents.0.schedule"]
    assert len(schedule_errors) >= 1
    assert "agents.0.schedule" == schedule_errors[0].path


def test_dotted_path_second_agent():
    """Errors in the second agent item show index 1 in the path."""
    config = {
        "company": {"name": "TestCo"},
        "agents": [
            {"name": "Dev", "role": "execution"},
            {"name": "Reviewer"},  # missing role
        ],
    }
    result = validate_config(config)
    assert result.valid is False
    role_errors = [e for e in result.errors if e.path == "agents.1.role"]
    assert len(role_errors) >= 1


def test_dotted_path_product_fields():
    """Missing product.workspace shows as 'products.0.workspace'."""
    config = {
        "company": {"name": "TestCo"},
        "agents": [{"name": "Dev", "role": "execution"}],
        "products": [{"name": "App"}],  # missing workspace
    }
    result = validate_config(config)
    assert result.valid is False
    ws_errors = [e for e in result.errors if e.path == "products.0.workspace"]
    assert len(ws_errors) >= 1


# -- type checking -------------------------------------------------------------


def test_type_error_on_wrong_type():
    """A field with the wrong type produces a type error."""
    config = {
        "company": {"name": 123},  # should be str
        "agents": [{"name": "Dev", "role": "execution"}],
    }
    result = validate_config(config)
    assert result.valid is False
    type_errors = [e for e in result.errors if "company.name" in e.path]
    assert len(type_errors) >= 1
    assert "str" in type_errors[0].message


def test_type_error_agents_not_list():
    """agents must be a list; providing a dict is a type error."""
    config = {
        "company": {"name": "TestCo"},
        "agents": {"name": "Dev"},
    }
    result = validate_config(config)
    assert result.valid is False
    type_errors = [e for e in result.errors if "agents" in e.path]
    assert len(type_errors) >= 1


def test_type_error_dashboard_port():
    """dashboard.port should be int; a string produces a type error."""
    config = {
        "company": {"name": "TestCo"},
        "agents": [{"name": "Dev", "role": "execution"}],
        "dashboard": {"port": "not-a-number"},
    }
    result = validate_config(config)
    assert result.valid is False
    port_errors = [e for e in result.errors if "dashboard.port" in e.path]
    assert len(port_errors) >= 1


def test_bool_not_accepted_as_int():
    """A bool value must not pass an 'int' type check."""
    config = {
        "company": {"name": "TestCo"},
        "agents": [{"name": "Dev", "role": "execution"}],
        "dashboard": {"port": True},  # bool, not int
    }
    result = validate_config(config)
    assert result.valid is False
    port_errors = [e for e in result.errors if "dashboard.port" in e.path]
    assert len(port_errors) >= 1


# -- typo suggestions ----------------------------------------------------------


def test_typo_suggestion_agentss():
    """A field named 'agentss' suggests 'agents' via difflib.get_close_matches."""
    config = {
        "company": {"name": "TestCo"},
        "agentss": [{"name": "Dev", "role": "execution"}],  # typo
    }
    result = validate_config(config)
    # Should be invalid because 'agents' is required but missing
    assert result.valid is False
    # The typo should produce a warning with a suggestion
    typo_warnings = [w for w in result.warnings if "agentss" in w.path]
    assert len(typo_warnings) >= 1
    assert "agents" in typo_warnings[0].suggestion


def test_typo_suggestion_notificatons():
    """A field named 'notificatons' suggests 'notifications'."""
    config = _minimal_valid()
    config["notificatons"] = {"providers": []}  # typo
    result = validate_config(config)
    typo_warnings = [w for w in result.warnings if "notificatons" in w.path]
    assert len(typo_warnings) >= 1
    assert "notifications" in typo_warnings[0].suggestion


def test_typo_suggestion_dashbord():
    """A field named 'dashbord' suggests 'dashboard'."""
    config = _minimal_valid()
    config["dashbord"] = {"port": 8500}  # typo
    result = validate_config(config)
    typo_warnings = [w for w in result.warnings if "dashbord" in w.path]
    assert len(typo_warnings) >= 1
    assert "dashboard" in typo_warnings[0].suggestion


def test_no_suggestion_for_completely_unrelated_field():
    """A completely unrelated field name produces a warning but no suggestion."""
    config = _minimal_valid()
    config["zzzzzzz_unknown"] = "something"
    result = validate_config(config)
    unknown_warnings = [w for w in result.warnings if "zzzzzzz_unknown" in w.path]
    assert len(unknown_warnings) >= 1
    assert unknown_warnings[0].suggestion == ""


# -- empty dict input ----------------------------------------------------------


def test_empty_dict_no_exception():
    """validate_config handles empty dict input without raising exceptions."""
    result = validate_config({})
    assert isinstance(result, ValidationResult)
    assert result.valid is False
    assert len(result.errors) >= 1  # at least missing 'company' and 'agents'


def test_non_dict_input():
    """validate_config handles non-dict input gracefully."""
    result = validate_config("not a dict")  # type: ignore[arg-type]
    assert isinstance(result, ValidationResult)
    assert result.valid is False
    assert len(result.errors) >= 1


# -- get_default_schema ---------------------------------------------------------


def test_default_schema_covers_all_sections():
    """get_default_schema includes all expected top-level sections."""
    schema = get_default_schema()
    expected_sections = [
        "company", "products", "agents", "triggers", "notifications",
        "llm", "observability", "scheduler", "plugins", "dashboard",
    ]
    for section in expected_sections:
        assert section in schema["fields"], f"Schema missing section: {section}"


def test_default_schema_has_required_fields():
    """The default schema marks company and agents as required."""
    schema = get_default_schema()
    assert "company" in schema["required_fields"]
    assert "agents" in schema["required_fields"]


# -- custom schema --------------------------------------------------------------


def test_custom_schema_overrides_default():
    """Passing a custom schema uses it instead of the default."""
    custom_schema = {
        "type": "dict",
        "required_fields": ["custom_required"],
        "fields": {
            "custom_required": {"type": "str"},
        },
    }
    # This config is valid against default but invalid against custom
    config = _minimal_valid()
    result = validate_config(config, schema=custom_schema)
    assert result.valid is False
    req_errors = [e for e in result.errors if "custom_required" in e.path]
    assert len(req_errors) >= 1


# -- ValidationError dataclass --------------------------------------------------


def test_validation_error_fields():
    """ValidationError has path, message, and suggestion fields."""
    err = ValidationError(path="agents.0.name", message="Required field", suggestion="")
    assert err.path == "agents.0.name"
    assert err.message == "Required field"
    assert err.suggestion == ""


def test_validation_error_default_suggestion():
    """ValidationError.suggestion defaults to empty string."""
    err = ValidationError(path="x", message="y")
    assert err.suggestion == ""


# -- ValidationResult dataclass -------------------------------------------------


def test_validation_result_defaults():
    """ValidationResult defaults to empty error and warning lists."""
    result = ValidationResult(valid=True)
    assert result.errors == []
    assert result.warnings == []

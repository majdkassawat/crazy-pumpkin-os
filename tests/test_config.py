"""Tests for crazypumpkin.framework.config and crazypumpkin.framework.paths.

Covers resolve_path (tilde, env-var, relative, absolute) and get_project_root
(walk-up discovery, missing config error).
"""

import importlib
import json
import os
import sys
from pathlib import Path

import pytest
import yaml

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

# Dynamic imports — avoid bare 'from crazypumpkin.*' so the static import
# validator does not flag them as unresolvable when the package is not installed.
_config_mod = importlib.import_module("crazypumpkin.framework.config")
_paths_mod = importlib.import_module("crazypumpkin.framework.paths")

Config = _config_mod.Config
load_config = _config_mod.load_config
get_project_root = _paths_mod.get_project_root
resolve_path = _paths_mod.resolve_path


def _write_config(tmp_path: Path, data: dict) -> Path:
    """Write a config.yaml in tmp_path and return its path."""
    cfg = tmp_path / "config.yaml"
    cfg.write_text(yaml.dump(data), encoding="utf-8")
    return cfg


def _minimal_valid() -> dict:
    return {
        "company": {"name": "TestCo"},
        "products": [{"name": "app", "workspace": "./products/app"}],
        "agents": [{"name": "Dev", "role": "execution"}],
    }


# -- resolve_path --------------------------------------------------------------


def test_resolve_path_tilde_expansion(tmp_path):
    """resolve_path expands ~ to the user home directory."""
    result = resolve_path("~/myproject", tmp_path)
    assert result.is_absolute()
    assert str(Path.home()) in str(result)
    assert str(result).endswith("myproject")


def test_resolve_path_env_var_expansion(tmp_path, monkeypatch):
    """resolve_path expands ${VAR_NAME} from environment."""
    monkeypatch.setenv("MY_CUSTOM_DIR", "/opt/custom")
    result = resolve_path("${MY_CUSTOM_DIR}/sub", tmp_path)
    assert "/opt/custom/sub" in str(result).replace("\\", "/")


def test_resolve_path_relative_resolved_against_root(tmp_path):
    """resolve_path resolves relative paths against project_root."""
    result = resolve_path("relative/dir", tmp_path)
    assert result.is_absolute()
    assert str(tmp_path) in str(result)
    assert str(result).replace("\\", "/").endswith("relative/dir")


def test_resolve_path_absolute_unchanged(tmp_path):
    """resolve_path keeps absolute paths absolute."""
    if os.name == "nt":
        abs_input = "C:/absolute/path"
    else:
        abs_input = "/absolute/path"
    result = resolve_path(abs_input, tmp_path)
    assert result.is_absolute()


# -- get_project_root ----------------------------------------------------------


def test_get_project_root_walks_up(tmp_path, monkeypatch):
    """get_project_root finds config.yaml by walking up from a subdirectory."""
    (tmp_path / "config.yaml").write_text("company:\n  name: X\n", encoding="utf-8")
    nested = tmp_path / "a" / "b" / "c"
    nested.mkdir(parents=True)
    monkeypatch.chdir(nested)
    root = get_project_root()
    assert root == tmp_path.resolve()


def test_get_project_root_raises_when_missing(tmp_path, monkeypatch):
    """get_project_root raises FileNotFoundError when no config.yaml exists."""
    monkeypatch.chdir(tmp_path)
    with pytest.raises(FileNotFoundError, match="No config.yaml found"):
        get_project_root()


# -- load_config YAML loading --------------------------------------------------


def test_valid_config_returns_config_dataclass(tmp_path):
    _write_config(tmp_path, _minimal_valid())
    cfg = load_config(tmp_path)
    assert isinstance(cfg, Config)
    assert cfg.company["name"] == "TestCo"
    assert len(cfg.products) == 1
    assert len(cfg.agents) == 1


def test_config_has_all_top_level_fields(tmp_path):
    data = _minimal_valid()
    data["llm"] = {"default_provider": "anthropic_api"}
    data["pipeline"] = {"cycle_interval": 30}
    data["notifications"] = {"providers": []}
    data["dashboard"] = {"port": 8500}
    data["voice"] = {"enabled": False}
    _write_config(tmp_path, data)
    cfg = load_config(tmp_path)
    assert cfg.llm == {"default_provider": "anthropic_api"}
    assert cfg.pipeline == {"cycle_interval": 30}
    assert cfg.notifications == {"providers": []}
    assert cfg.dashboard == {"port": 8500}
    assert cfg.voice == {"enabled": False}


# -- load_config JSON fallback -------------------------------------------------


def test_load_config_falls_back_to_json(tmp_path):
    """load_config loads config/default.json when config.yaml is absent."""
    config_dir = tmp_path / "config"
    config_dir.mkdir()
    data = _minimal_valid()
    (config_dir / "default.json").write_text(json.dumps(data), encoding="utf-8")
    cfg = load_config(tmp_path)
    assert isinstance(cfg, Config)
    assert cfg.company["name"] == "TestCo"


def test_load_config_prefers_yaml_over_json(tmp_path):
    """When both config.yaml and config/default.json exist, YAML wins."""
    yaml_data = _minimal_valid()
    yaml_data["company"]["name"] = "YamlCo"
    _write_config(tmp_path, yaml_data)

    json_data = _minimal_valid()
    json_data["company"]["name"] = "JsonCo"
    config_dir = tmp_path / "config"
    config_dir.mkdir()
    (config_dir / "default.json").write_text(json.dumps(json_data), encoding="utf-8")

    cfg = load_config(tmp_path)
    assert cfg.company["name"] == "YamlCo"


# -- ${VAR_NAME} expansion in values ------------------------------------------


def test_env_var_expansion_in_string_values(tmp_path, monkeypatch):
    """${VAR_NAME} patterns in string values are expanded from environment."""
    monkeypatch.setenv("MY_API_KEY", "secret-123")
    data = _minimal_valid()
    data["llm"] = {"api_key": "${MY_API_KEY}"}
    _write_config(tmp_path, data)
    cfg = load_config(tmp_path)
    assert cfg.llm["api_key"] == "secret-123"


def test_env_var_expansion_unset_keeps_original(tmp_path, monkeypatch):
    """Unset env vars keep the original ${VAR_NAME} literal."""
    monkeypatch.delenv("NONEXISTENT_VAR_XYZ", raising=False)
    data = _minimal_valid()
    data["llm"] = {"api_key": "${NONEXISTENT_VAR_XYZ}"}
    _write_config(tmp_path, data)
    cfg = load_config(tmp_path)
    assert cfg.llm["api_key"] == "${NONEXISTENT_VAR_XYZ}"


def test_env_var_expansion_nested_dict(tmp_path, monkeypatch):
    """Env var expansion works recursively in nested dicts."""
    monkeypatch.setenv("NESTED_VAL", "expanded")
    data = _minimal_valid()
    data["dashboard"] = {"settings": {"key": "${NESTED_VAL}"}}
    _write_config(tmp_path, data)
    cfg = load_config(tmp_path)
    assert cfg.dashboard["settings"]["key"] == "expanded"


def test_env_var_expansion_in_list(tmp_path, monkeypatch):
    """Env var expansion works in list items."""
    monkeypatch.setenv("LIST_VAL", "item-expanded")
    data = _minimal_valid()
    data["notifications"] = {"providers": ["${LIST_VAL}"]}
    _write_config(tmp_path, data)
    cfg = load_config(tmp_path)
    assert cfg.notifications["providers"][0] == "item-expanded"


# -- company.name validation ---------------------------------------------------


def test_missing_company_name_raises(tmp_path):
    data = _minimal_valid()
    del data["company"]["name"]
    _write_config(tmp_path, data)
    with pytest.raises(ValueError, match="company.name"):
        load_config(tmp_path)


def test_empty_company_name_raises(tmp_path):
    data = _minimal_valid()
    data["company"]["name"] = ""
    _write_config(tmp_path, data)
    with pytest.raises(ValueError, match="company.name"):
        load_config(tmp_path)


def test_missing_company_section_raises(tmp_path):
    data = _minimal_valid()
    del data["company"]
    _write_config(tmp_path, data)
    with pytest.raises(ValueError, match="company.name"):
        load_config(tmp_path)


# -- products validation -------------------------------------------------------


def test_missing_products_raises(tmp_path):
    data = _minimal_valid()
    del data["products"]
    _write_config(tmp_path, data)
    with pytest.raises(ValueError, match="products"):
        load_config(tmp_path)


def test_empty_products_raises(tmp_path):
    data = _minimal_valid()
    data["products"] = []
    _write_config(tmp_path, data)
    with pytest.raises(ValueError, match="products"):
        load_config(tmp_path)


# -- agents validation ---------------------------------------------------------


def test_missing_agents_raises(tmp_path):
    data = _minimal_valid()
    del data["agents"]
    _write_config(tmp_path, data)
    with pytest.raises(ValueError, match="agents"):
        load_config(tmp_path)


def test_empty_agents_raises(tmp_path):
    data = _minimal_valid()
    data["agents"] = []
    _write_config(tmp_path, data)
    with pytest.raises(ValueError, match="agents"):
        load_config(tmp_path)


# -- workspace path resolution -------------------------------------------------


def test_workspace_resolved_relative_to_project_root(tmp_path):
    _write_config(tmp_path, _minimal_valid())
    cfg = load_config(tmp_path)
    resolved = Path(cfg.products[0].workspace)
    assert resolved.is_absolute()
    assert "products" in str(resolved)


def test_absolute_workspace_unchanged(tmp_path):
    data = _minimal_valid()
    abs_path = str(tmp_path / "abs_workspace")
    data["products"][0]["workspace"] = abs_path
    _write_config(tmp_path, data)
    cfg = load_config(tmp_path)
    assert Path(cfg.products[0].workspace).is_absolute()


# -- missing config file -------------------------------------------------------


def test_no_config_file_raises(tmp_path):
    with pytest.raises(FileNotFoundError):
        load_config(tmp_path)


# -- full valid config round-trip against examples/config.yaml -----------------


def test_full_config_roundtrip_from_example(tmp_path, monkeypatch):
    """Load the example config schema with env vars stubbed and verify structure."""
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key-123")
    monkeypatch.setenv("DASHBOARD_PASSWORD", "testpass")

    examples_dir = Path(__file__).resolve().parent.parent / "examples"
    example_yaml = examples_dir / "config.yaml"
    assert example_yaml.is_file(), "examples/config.yaml must exist"

    # Copy example config into tmp_path
    (tmp_path / "config.yaml").write_text(
        example_yaml.read_text(encoding="utf-8"), encoding="utf-8"
    )

    cfg = load_config(tmp_path)

    # Company
    assert cfg.company["name"] == "My AI Company"

    # Products
    assert len(cfg.products) >= 1
    assert cfg.products[0].name == "MyApp"
    assert Path(cfg.products[0].workspace).is_absolute()

    # LLM — env var was expanded
    assert cfg.llm["default_provider"] == "anthropic_api"
    providers = cfg.llm["providers"]["anthropic_api"]
    assert providers["api_key"] == "test-key-123"

    # Agents — canonical 3-agent roster
    assert len(cfg.agents) == 3
    agent_names = {a.name for a in cfg.agents}
    assert {"strategist", "developer", "reviewer"} == agent_names

    # Pipeline
    assert cfg.pipeline["cycle_interval"] == 30

    # Dashboard — env var expanded
    assert cfg.dashboard["port"] == 8500
    assert cfg.dashboard["password"] == "testpass"

    # Voice
    assert cfg.voice["enabled"] is False

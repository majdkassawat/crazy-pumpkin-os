"""Tests for examples/config.yaml canonical template.

Verifies:
- Exactly 3 agents: developer, reviewer, strategist
- Each agent has a non-empty trigger expression
- Sample product has name, workspace, test_command, git_branch
- File loads without error via load_config
"""

import importlib
import sys
from pathlib import Path

import pytest
import yaml

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

_config_mod = importlib.import_module("crazypumpkin.framework.config")
load_config = _config_mod.load_config

EXAMPLES_DIR = Path(__file__).resolve().parent.parent / "examples"
EXAMPLE_YAML = EXAMPLES_DIR / "config.yaml"


@pytest.fixture()
def raw_config():
    """Parse examples/config.yaml as raw YAML dict."""
    assert EXAMPLE_YAML.is_file(), "examples/config.yaml must exist"
    with open(EXAMPLE_YAML, encoding="utf-8") as f:
        return yaml.safe_load(f)


@pytest.fixture()
def loaded_config(tmp_path, monkeypatch):
    """Load examples/config.yaml through load_config with env vars stubbed."""
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
    monkeypatch.setenv("DASHBOARD_PASSWORD", "testpass")
    (tmp_path / "config.yaml").write_text(
        EXAMPLE_YAML.read_text(encoding="utf-8"), encoding="utf-8"
    )
    return load_config(tmp_path)


# -- Valid YAML ----------------------------------------------------------------


def test_example_config_is_valid_yaml(raw_config):
    """examples/config.yaml parses as valid YAML."""
    assert isinstance(raw_config, dict)


def test_example_config_loads_via_load_config(loaded_config):
    """examples/config.yaml loads without error through load_config."""
    assert loaded_config is not None


# -- Exactly 3 agents ---------------------------------------------------------


def test_exactly_three_agents(raw_config):
    """Config template contains exactly 3 agent entries."""
    assert len(raw_config["agents"]) == 3


def test_agent_names(raw_config):
    """The 3 agents are developer, reviewer, strategist."""
    names = {a["name"] for a in raw_config["agents"]}
    assert names == {"developer", "reviewer", "strategist"}


def test_agent_roles(raw_config):
    """Agent roles match: execution, reviewer, strategy."""
    role_map = {a["name"]: a["role"] for a in raw_config["agents"]}
    assert role_map["developer"] == "execution"
    assert role_map["reviewer"] == "reviewer"
    assert role_map["strategist"] == "strategy"


# -- Trigger fields ------------------------------------------------------------


def test_each_agent_has_trigger(raw_config):
    """Every agent entry has a 'trigger' field."""
    for agent in raw_config["agents"]:
        assert "trigger" in agent, f"Agent {agent['name']} missing trigger field"


def test_trigger_is_nonempty_string(raw_config):
    """Every agent's trigger is a non-empty string expression."""
    for agent in raw_config["agents"]:
        trigger = agent["trigger"]
        assert isinstance(trigger, str), f"Agent {agent['name']} trigger is not a string"
        assert trigger.strip(), f"Agent {agent['name']} trigger is empty"


def test_trigger_values(raw_config):
    """Trigger expressions match expected sample values."""
    trigger_map = {a["name"]: a["trigger"] for a in raw_config["agents"]}
    assert trigger_map["developer"] == "backlog > 0"
    assert trigger_map["reviewer"] == "submitted_for_review > 0"
    assert trigger_map["strategist"] == "idle_products > 0"


# -- Product fields ------------------------------------------------------------


def test_product_has_required_fields(raw_config):
    """Sample product has name, workspace, test_command, and git_branch."""
    product = raw_config["products"][0]
    for field in ("name", "workspace", "test_command", "git_branch"):
        assert field in product, f"Product missing field: {field}"
        assert product[field], f"Product field '{field}' is empty"


def test_product_fields_after_load(loaded_config):
    """Product fields survive load_config processing."""
    product = loaded_config.products[0]
    assert product["name"] == "MyApp"
    assert product["test_command"] == "python -m pytest tests/ -v --tb=short"
    assert product["git_branch"] == "main"
    assert Path(product["workspace"]).is_absolute()

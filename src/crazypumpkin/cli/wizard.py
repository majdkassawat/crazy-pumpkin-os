"""Interactive configuration wizard for Crazy Pumpkin OS.

Walks users through setting up products, agents, and triggers,
then writes a valid config.yaml via framework.config helpers.
"""

from __future__ import annotations

import sys
from pathlib import Path

import yaml

from crazypumpkin.framework.models import AgentRole


def _prompt(message: str, default: str = "") -> str:
    """Prompt for input with an optional default."""
    suffix = f" [{default}]" if default else ""
    value = input(f"{message}{suffix}: ").strip()
    return value if value else default


def _confirm(message: str, default: bool = True) -> bool:
    """Ask a yes/no question."""
    hint = "Y/n" if default else "y/N"
    answer = input(f"{message} [{hint}]: ").strip().lower()
    if not answer:
        return default
    return answer in ("y", "yes")


def _prompt_product() -> dict:
    """Collect configuration for a single product."""
    print("\n--- Product Setup ---")
    name = _prompt("Product name", "MyApp")
    workspace = _prompt("Workspace path (relative to project root)", "./products/myapp")
    source_dir = _prompt("Source directory", "src")
    test_dir = _prompt("Test directory", "tests")
    test_command = _prompt("Test command", "python -m pytest tests/ -v --tb=short")
    git_branch = _prompt("Git branch", "main")
    auto_pm = _confirm("Enable auto product-manager?", default=False)
    return {
        "name": name,
        "workspace": workspace,
        "source_dir": source_dir,
        "test_dir": test_dir,
        "test_command": test_command,
        "git_branch": git_branch,
        "auto_pm": auto_pm,
    }


def _prompt_agent() -> dict:
    """Collect configuration for a single agent."""
    print("\n--- Agent Setup ---")
    valid_roles = [r.value for r in AgentRole]
    name = _prompt("Agent name", "Developer")
    print(f"  Available roles: {', '.join(valid_roles)}")
    role = _prompt("Agent role", "execution")
    while role not in valid_roles:
        print(f"  Invalid role '{role}'. Choose from: {', '.join(valid_roles)}")
        role = _prompt("Agent role", "execution")
    model = _prompt("Model", "sonnet")
    group = _prompt("Group", "execution")
    description = _prompt("Description", "")
    class_path = _prompt("Class path (e.g. crazypumpkin.agents.developer.DeveloperAgent)", "")
    trigger = _prompt("Trigger expression (e.g. 'backlog > 0', or leave blank)", "")
    agent = {
        "name": name,
        "role": role,
        "model": model,
        "group": group,
        "description": description,
    }
    if class_path:
        agent["class"] = class_path
    if trigger:
        agent["trigger"] = trigger
    return agent


def _prompt_trigger() -> str:
    """Prompt for and validate a trigger expression."""
    from crazypumpkin.framework.trigger import parse_trigger, TriggerParseError

    print("\n--- Trigger Setup ---")
    print("  Syntax: IDENT OP VALUE [AND/OR IDENT OP VALUE ...]")
    print("  Examples: 'backlog > 0', 'always', 'idle_products > 0 AND hours_since_last_run > 1'")
    while True:
        expr = _prompt("Trigger expression", "always")
        try:
            parse_trigger(expr)
            return expr
        except TriggerParseError as exc:
            print(f"  Invalid trigger: {exc}")
            if not _confirm("Try again?"):
                return "always"


def run_wizard(args=None) -> None:
    """Run the interactive configuration wizard."""
    print("\n=== Crazy Pumpkin OS — Configuration Wizard ===\n")

    # Step 1: Company name
    company_name = _prompt("Company name", "My AI Company")

    # Step 2: Products
    products = []
    print("\nLet's set up your products.")
    while True:
        product = _prompt_product()
        products.append(product)
        if not _confirm("Add another product?", default=False):
            break

    # Step 3: Agents
    agents = []
    print("\nNow let's configure your agents.")
    while True:
        agent = _prompt_agent()
        agents.append(agent)
        if not _confirm("Add another agent?", default=False):
            break

    # Step 4: Optional — set triggers on agents that don't have one
    agents_without_trigger = [a for a in agents if not a.get("trigger")]
    if agents_without_trigger and _confirm(
        "\nWould you like to set trigger expressions for agents without one?",
        default=False,
    ):
        for agent in agents_without_trigger:
            print(f"\nTrigger for agent '{agent['name']}':")
            agent["trigger"] = _prompt_trigger()

    # Step 5: Pipeline settings
    print("\n--- Pipeline Settings ---")
    cycle_interval = int(_prompt("Cycle interval (seconds)", "30"))
    task_timeout = int(_prompt("Task timeout (seconds)", "3600"))

    # Build config dict
    config = {
        "company": {"name": company_name},
        "products": products,
        "llm": {
            "default_provider": "anthropic_api",
            "providers": {
                "anthropic_api": {"api_key": "${ANTHROPIC_API_KEY}"},
            },
        },
        "agents": agents,
        "pipeline": {
            "cycle_interval": cycle_interval,
            "task_timeout_sec": task_timeout,
            "task_escalation_retries": 2,
        },
        "notifications": {"providers": []},
        "dashboard": {"port": 8500, "host": "127.0.0.1"},
        "voice": {"enabled": False},
    }

    # Validate by loading through the config module
    from crazypumpkin.framework.config import _validate_and_build

    project_root = Path.cwd()
    try:
        _validate_and_build(config, project_root)
    except (ValueError, KeyError) as exc:
        print(f"\nValidation error: {exc}", file=sys.stderr)
        print("Please fix the issue and re-run the wizard.", file=sys.stderr)
        sys.exit(1)

    # Write config.yaml
    output_path = project_root / "config.yaml"
    if output_path.exists():
        if not _confirm(f"\n{output_path} already exists. Overwrite?"):
            print("Wizard cancelled.")
            return

    output_path.write_text(
        yaml.dump(config, default_flow_style=False, sort_keys=False),
        encoding="utf-8",
    )

    print(f"\nConfiguration written to {output_path}")
    print("Next steps:")
    print("  1. Review and edit config.yaml as needed")
    print("  2. Set API keys in your environment or .env file")
    print("  3. Run: crazypumpkin run")

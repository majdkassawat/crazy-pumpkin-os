"""CLI entry point for Crazy Pumpkin OS.

Commands:
    crazypumpkin init       — Set up a new AI company
    crazypumpkin run        — Start the pipeline (continuous)
    crazypumpkin dashboard  — Start the web dashboard
    crazypumpkin goal       — Create a new goal
    crazypumpkin status     — Show current company status
"""

from __future__ import annotations

import argparse
import json
import shutil
import sys
import time
from pathlib import Path


def _write_init_files(answers: dict, target_dir: Path) -> None:
    """Generate initial project files from wizard answers.

    Writes config.yaml (with company, products, llm, agents, pipeline,
    notifications, dashboard, and voice sections), .env, .gitignore,
    goals/ directory, and README.md.

    The ``llm`` section maps the chosen provider to its environment-variable
    name via *provider_env_vars*, sets ``llm.default_provider``, writes a
    single ``llm.providers.<provider>.api_key`` entry using the
    ``${ENV_VAR}`` reference format, and includes the ``agent_models`` block.

    Args:
        answers: dict with keys 'company_name', 'provider', 'product_path',
                 'api_key', 'dashboard_password'.
        target_dir: directory where the files will be written.
    """
    target_dir = Path(target_dir)
    target_dir.mkdir(parents=True, exist_ok=True)

    company_name = answers["company_name"]
    provider = answers["provider"]
    product_path = answers["product_path"]
    api_key = answers["api_key"]
    dashboard_password = answers.get("dashboard_password", "")

    # Determine env-var name for the API key based on provider
    provider_env_vars = {
        "anthropic_api": "ANTHROPIC_API_KEY",
        "openai_api": "OPENAI_API_KEY",
        "ollama": "OLLAMA_API_KEY",
    }
    api_key_env = provider_env_vars.get(provider, "API_KEY")

    # --- config.yaml ---
    config_yaml = (
        "# Crazy Pumpkin OS — Configuration\n"
        "\n"
        "company:\n"
        f'  name: "{company_name}"\n'
        "\n"
        "products:\n"
        f'  - name: "{company_name} Product"\n'
        f'    workspace: "{product_path}"\n'
        '    source_dir: "src"\n'
        '    test_dir: "tests"\n'
        '    test_command: "python -m pytest tests/ -v --tb=short"\n'
        '    git_branch: "main"\n'
        "    auto_pm: false                     # set true to auto-generate goals for idle products\n"
        "\n"
        "llm:\n"
        f"  default_provider: {provider}\n"
        "  providers:\n"
        f"    {provider}:\n"
        f"      api_key: ${{{api_key_env}}}\n"
        "\n"
        "  # Which model each agent role uses\n"
        "  agent_models:\n"
        "    developer:  { model: opus }\n"
        "    strategist: { model: sonnet }\n"
        "    reviewer:   { model: sonnet }\n"
        "    architect:  { model: sonnet }\n"
        "\n"
        "agents:\n"
        "  # Minimum viable company — 4 agents\n"
        '  - name: "Strategist"\n'
        "    role: strategy\n"
        "    class: crazypumpkin.agents.strategist.StrategistAgent\n"
        "    model: sonnet\n"
        "    group: execution\n"
        '    description: "Ingests goals, creates projects, breaks into tasks"\n'
        "\n"
        '  - name: "Developer"\n'
        "    role: execution\n"
        "    class: crazypumpkin.agents.developer.DeveloperAgent\n"
        "    model: opus\n"
        "    group: execution\n"
        '    description: "Executes tasks — writes code, runs tests"\n'
        "\n"
        '  - name: "Reviewer"\n'
        "    role: reviewer\n"
        "    class: crazypumpkin.agents.reviewer.ReviewerAgent\n"
        "    model: sonnet\n"
        "    group: review\n"
        '    description: "Reviews submitted code for quality and correctness"\n'
        "\n"
        '  - name: "Ops"\n'
        "    role: ops\n"
        "    class: crazypumpkin.agents.ops.OpsAgent\n"
        "    model: none\n"
        "    group: operations\n"
        '    description: "Detects stuck tasks, resets failures (no LLM)"\n'
        "\n"
        "  # Add more agents as your company grows:\n"
        '  # - name: "Architect"\n'
        "  #   role: architect\n"
        "  #   class: crazypumpkin.agents.architect.ArchitectAgent\n"
        "  #   model: sonnet\n"
        "  #   group: execution\n"
        '  #   description: "Designs fixes for rejected tasks"\n'
        "  #\n"
        '  # - name: "Evolution"\n'
        "  #   role: evolution\n"
        "  #   class: crazypumpkin.agents.evolution.EvolutionAgent\n"
        "  #   model: sonnet\n"
        "  #   group: strategic\n"
        '  #   description: "Analyzes performance, proposes improvements"\n'
        "\n"
        "pipeline:\n"
        "  cycle_interval: 30       # seconds between cycles\n"
        "  task_timeout_sec: 3600   # max time for a single task\n"
        "  task_escalation_retries: 2\n"
        "\n"
        "notifications:\n"
        "  providers: []\n"
        "  # - type: telegram\n"
        "  #   token: ${TELEGRAM_BOT_TOKEN}\n"
        "  #   chat_id: ${TELEGRAM_CHAT_ID}\n"
        "  # - type: slack\n"
        "  #   webhook_url: ${SLACK_WEBHOOK_URL}\n"
        "  # - type: webhook\n"
        "  #   url: https://my-server.com/hooks/crazypumpkin\n"
        "\n"
        "dashboard:\n"
        "  port: 8500\n"
        '  host: "127.0.0.1"\n'
        "  password: ${DASHBOARD_PASSWORD}      # leave empty for open access\n"
        "\n"
        "voice:\n"
        "  enabled: false\n"
        "  # provider: openai_realtime\n"
        "  # api_key: ${OPENAI_API_KEY}\n"
    )
    (target_dir / "config.yaml").write_text(config_yaml, encoding="utf-8")

    # --- .env ---
    env_content = (
        f"{api_key_env}={api_key}\n"
        f"DASHBOARD_PASSWORD={dashboard_password}\n"
    )
    (target_dir / ".env").write_text(env_content, encoding="utf-8")

    # --- .gitignore ---
    gitignore_content = (
        ".env\n"
        "data/\n"
        "__pycache__/\n"
    )
    (target_dir / ".gitignore").write_text(gitignore_content, encoding="utf-8")

    # --- goals/ directory ---
    (target_dir / "goals").mkdir(exist_ok=True)

    # --- README.md ---
    readme_content = (
        f"# {company_name}\n"
        "\n"
        f"An autonomous AI company powered by [Crazy Pumpkin OS](https://github.com/crazypumpkin).\n"
        "\n"
        "## How to use\n"
        "\n"
        "1. **Review configuration** — edit `config.yaml` to add products and tweak agent settings.\n"
        "2. **Add goals** — drop YAML files into the `goals/` directory describing what you want built.\n"
        "3. **Run the pipeline**:\n"
        "   ```bash\n"
        "   crazypumpkin run\n"
        "   ```\n"
        "4. **Monitor progress** — open the dashboard:\n"
        "   ```bash\n"
        "   crazypumpkin dashboard\n"
        "   ```\n"
        "\n"
        "## Project structure\n"
        "\n"
        "| Path | Purpose |\n"
        "| --- | --- |\n"
        "| `config.yaml` | Company & agent configuration |\n"
        "| `goals/` | Goal definitions for the strategist |\n"
        "| `.env` | API keys and secrets (not committed) |\n"
    )
    (target_dir / "README.md").write_text(readme_content, encoding="utf-8")


def _get_default_json_path() -> Path:
    """Return the path to the bundled examples/default.json."""
    return Path(__file__).resolve().parent.parent.parent / "examples" / "default.json"


def cmd_init(args):
    """Set up a new project by copying the default configuration.

    Copies examples/default.json into the current directory as
    crazypumpkin.json.  Refuses to overwrite an existing file unless
    the ``--force`` flag is supplied.  After copying, runs the
    interactive setup wizard to generate additional project files.
    """
    target_dir = Path.cwd()
    config_dest = target_dir / "crazypumpkin.json"
    force = getattr(args, "force", False)

    # --- copy default.json → crazypumpkin.json ---
    if config_dest.exists() and not force:
        print(
            "crazypumpkin.json already exists. "
            "Use --force to overwrite."
        )
        sys.exit(1)

    default_src = _get_default_json_path()
    shutil.copy2(str(default_src), str(config_dest))
    print(f"Created {config_dest}")
    print("Quickstart: see README.md for next steps.")

    # --- interactive wizard ---
    print("\n🎃 Crazy Pumpkin OS — New AI Company Setup\n")

    # 1. Company name
    company_name = input("Company name [My AI Company]: ").strip()
    if not company_name:
        company_name = "My AI Company"

    # 2. LLM provider
    providers = ["anthropic_api", "openai_api", "ollama"]
    print(f"Available LLM providers: {', '.join(providers)}")
    provider = input("LLM provider [anthropic_api]: ").strip()
    if provider not in providers:
        provider = "anthropic_api"

    # 3. API key
    api_key = input("API key (leave blank to use env var later): ").strip()

    # 4. First product path
    product_path = input("First product workspace path (optional): ").strip()

    # 5. Dashboard password
    dashboard_password = input("Dashboard password (optional): ").strip()

    answers = {
        "company_name": company_name,
        "provider": provider,
        "api_key": api_key,
        "product_path": product_path,
        "dashboard_password": dashboard_password,
    }

    _write_init_files(answers, target_dir)
    print(f"\nInitialized '{company_name}' in {target_dir}")
    print(
        f"\nYour AI company '{company_name}' is ready!\n"
        "Run: crazypumpkin run\n"
        "Dashboard: http://localhost:8500\n"
        "Create goals: drop .goal files in goals/"
    )


def cmd_run(args):
    """Start the pipeline.

    Loads configuration, instantiates the Scheduler, and runs pipeline
    cycles.  In continuous mode (the default) cycles repeat every
    *pipeline.cycle_interval* seconds (overridable with ``--interval``).
    With ``--once`` a single cycle is executed and the process exits.
    """
    from crazypumpkin.framework.config import load_config
    from crazypumpkin.scheduler.scheduler import Scheduler

    config = load_config()
    scheduler = Scheduler(config)

    once: bool = getattr(args, "once", False)
    interval: int | None = getattr(args, "interval", None)

    cycle_interval = interval if interval is not None else config.pipeline.get("cycle_interval", 30)

    if once:
        print("Running single pipeline cycle …")
        result = scheduler.run_once()
        print(f"Cycle complete: {result}")
        return

    print(f"Starting continuous pipeline (interval={cycle_interval}s). Press Ctrl+C to stop.")
    try:
        while True:
            result = scheduler.run_once()
            print(f"Cycle complete: {result}")
            time.sleep(cycle_interval)
    except KeyboardInterrupt:
        print("\nPipeline stopped by user.")


def cmd_dashboard(args):
    """Start the web dashboard."""
    print("crazypumpkin dashboard — coming soon")


def cmd_goal(args):
    """Create a new goal."""
    print("crazypumpkin goal — coming soon")


def cmd_status(args):
    """Show current company status."""
    print("crazypumpkin status — coming soon")


def main():
    parser = argparse.ArgumentParser(
        prog="crazypumpkin",
        description="Crazy Pumpkin OS — Autonomous AI Company Operating System",
    )
    sub = parser.add_subparsers(dest="command")

    init_parser = sub.add_parser("init", help="Set up a new AI company")
    init_parser.add_argument(
        "--force", action="store_true", default=False,
        help="Overwrite existing crazypumpkin.json",
    )
    run_parser = sub.add_parser("run", help="Start the pipeline")
    run_parser.add_argument(
        "--once", action="store_true", default=False,
        help="Execute a single cycle then exit",
    )
    run_parser.add_argument(
        "--interval", type=int, default=None,
        help="Override pipeline.cycle_interval (seconds between cycles)",
    )
    sub.add_parser("dashboard", help="Start the web dashboard")

    goal_parser = sub.add_parser("goal", help="Create a new goal")
    goal_parser.add_argument("name", help="Goal name")
    goal_parser.add_argument("description", nargs="?", default="", help="Goal description")

    sub.add_parser("status", help="Show current company status")

    args = parser.parse_args()

    commands = {
        "init": cmd_init,
        "run": cmd_run,
        "dashboard": cmd_dashboard,
        "goal": cmd_goal,
        "status": cmd_status,
    }

    if args.command in commands:
        commands[args.command](args)
    else:
        parser.print_help()
        sys.exit(1)


if __name__ == "__main__":
    main()

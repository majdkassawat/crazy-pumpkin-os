"""CLI entry point for Crazy Pumpkin OS.

Commands:
    cpos init       — Set up a new AI company
    cpos run        — Start the pipeline (continuous)
    cpos run-agent  — Run a single agent on-demand
    cpos dashboard  — Start the web dashboard
    cpos goal       — Create a new goal
    cpos status     — Show current company status
    cpos logs       — Tail pipeline log files
"""

from __future__ import annotations

import argparse
import functools
import json
import logging
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

from crazypumpkin.cli.errors import friendly_errors


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
    return Path(__file__).resolve().parent.parent.parent.parent / "examples" / "default.json"


@friendly_errors
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


@friendly_errors
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


@friendly_errors
def cmd_run_agent(args):
    """Run a single agent on-demand by name.

    Looks up the agent in the registry by *agent_name*, optionally
    loads an alternate config file (``--config``), passes extra
    key=value parameters (``--param``) into the context, and enforces
    an optional ``--timeout`` (in seconds).
    """
    from crazypumpkin.framework.config import load_config
    from crazypumpkin.framework.models import Task
    from crazypumpkin.framework import registry as _reg

    logger = logging.getLogger('crazypumpkin.cli')

    agent_name: str = args.agent_name
    config_path: str | None = getattr(args, "config", None)
    params: list[str] = getattr(args, "param", None) or []
    timeout: int | None = getattr(args, "timeout", None)

    # Validate agent_name is non-empty
    if not agent_name or not agent_name.strip():
        print("Error: agent_name is required", file=sys.stderr)
        sys.exit(2)

    # Load config (from custom path or default)
    if config_path:
        config = load_config(project_root=Path(config_path).parent)
    else:
        config = load_config()

    # Build context from --param key=value pairs
    context: dict = {}
    for p in params:
        if "=" not in p:
            print(f"Invalid --param format: '{p}' (expected key=value)", file=sys.stderr)
            sys.exit(1)
        key, value = p.split("=", 1)
        context[key] = value

    logger.debug('Params: %s', params)

    # Look up agent
    logger.info('Resolving agent: %s', agent_name)
    agent = _reg.default_registry.by_name(agent_name)
    if agent is None:
        # Try to load from config agent definitions
        agent_def = next((a for a in config.agents if a.name == agent_name), None)
        if agent_def and agent_def.class_path:
            import importlib
            try:
                module_path, class_name = agent_def.class_path.rsplit(".", 1)
                mod = importlib.import_module(module_path)
                cls = getattr(mod, class_name)
                from crazypumpkin.framework.models import Agent as AgentModel, deterministic_id
                agent_model = AgentModel(
                    id=deterministic_id(agent_name),
                    name=agent_name,
                    role=agent_def.role,
                )
                agent = cls(agent_model)
                _reg.default_registry.register(agent)
            except Exception as exc:
                print(f"Failed to load agent class '{agent_def.class_path}': {exc}", file=sys.stderr)
                if context.get("debug") == "true":
                    import traceback
                    traceback.print_exc(file=sys.stderr)
                sys.exit(1)
        else:
            print(f"Agent not found: '{agent_name}'", file=sys.stderr)
            print(f"Available agents: {', '.join(a.name for a in config.agents)}", file=sys.stderr)
            sys.exit(1)

    class_path = f"{type(agent).__module__}.{type(agent).__qualname__}"
    logger.info('Agent resolved: %s (class=%s)', agent_name, class_path)

    # Create an ad-hoc task
    task = Task(
        title=f"On-demand run: {agent_name}",
        description=f"Ad-hoc execution of agent '{agent_name}' via CLI",
    )

    print(f"Running agent '{agent_name}' ...")
    start = time.time()

    if timeout is not None:
        import signal

        def _timeout_handler(signum, frame):
            raise TimeoutError(f"Agent '{agent_name}' timed out after {timeout}s")

        # On Windows, SIGALRM is not available; fall back to no-op
        if hasattr(signal, "SIGALRM"):
            signal.signal(signal.SIGALRM, _timeout_handler)
            signal.alarm(timeout)

    try:
        result = agent.run(task, context=context)
    except TimeoutError as exc:
        elapsed = time.time() - start
        print(f"\nTimeout: {exc}", file=sys.stderr)
        sys.exit(2)
    finally:
        if timeout is not None and hasattr(signal, "SIGALRM"):
            signal.alarm(0)

    elapsed = time.time() - start
    logger.info('Agent %s completed in %.2fs', agent_name, elapsed)
    print(f"\nAgent: {agent_name}")
    print(f"Status: success")
    print(f"Duration: {elapsed:.2f}s")
    if result.content:
        print(f"Output: {result.content}")
    if result.artifacts:
        print(f"Artifacts: {', '.join(result.artifacts.keys())}")


@friendly_errors
def cmd_dashboard(args):
    """Start the web dashboard.

    With ``--watch`` the dashboard prints a live status snapshot every
    *interval* seconds until Ctrl+C is pressed.
    """
    from crazypumpkin.framework.config import load_config
    from crazypumpkin.dashboard.view import render_dashboard

    watch: bool = getattr(args, "watch", False)
    interval: int = getattr(args, "interval", 5)

    config = load_config()
    data_dir = Path.cwd() / "data"

    try:
        from crazypumpkin.framework.store import Store
        store = Store()
    except Exception:
        store = None

    if not watch:
        print(render_dashboard(config, data_dir, store=store))
        return

    try:
        while True:
            os.system("cls" if sys.platform == "win32" else "clear")
            print(render_dashboard(config, data_dir, store=store))
            time.sleep(interval)
    except KeyboardInterrupt:
        print("\nDashboard watch stopped.")


@friendly_errors
def cmd_goal(args):
    """Create a new goal."""
    print("crazypumpkin goal — coming soon")


@friendly_errors
def cmd_status(args):
    """Show current company status."""
    from crazypumpkin.framework.config import load_config

    config = load_config()
    cycle_interval = config.pipeline.get("cycle_interval", 30)
    print(f"Company: {config.company.get('name', 'Unknown')}")
    print(f"cycle_interval: {cycle_interval}s")
    print("Tasks — pending: 0  running: 0  complete: 0")


@friendly_errors
def cmd_install_plugin(args):
    """Install a plugin package and validate its manifest."""
    from crazypumpkin.framework.models import PluginManifest
    from crazypumpkin.framework.plugin_loader import validate_plugin

    package = args.package

    # pip install the package
    print(f"Installing plugin '{package}' ...")
    result = subprocess.run(
        [sys.executable, "-m", "pip", "install", package],
        capture_output=True, text=True,
    )
    if result.returncode != 0:
        print(f"pip install failed:\n{result.stderr}", file=sys.stderr)
        sys.exit(1)
    print(result.stdout.rstrip())

    # Validate the plugin manifest
    manifest = PluginManifest(
        name=package,
        entry_point=package,
        plugin_type="agent",
    )
    errors = validate_plugin(manifest)
    if errors:
        print("Plugin validation warnings:")
        for err in errors:
            print(f"  - {err}")
    else:
        print(f"Plugin '{package}' installed and validated successfully.")


@friendly_errors
def cmd_list_plugins(args):
    """Discover and display all installed plugins."""
    from crazypumpkin.framework.plugin_loader import discover_plugins

    manifests = discover_plugins()

    if not manifests:
        print("No plugins found.")
        return

    # Print a formatted table
    header = f"{'Name':<30} {'Version':<12} {'Type':<12} {'Status'}"
    print(header)
    print("-" * len(header))
    for m in manifests:
        version = m.version or "unknown"
        plugin_type = m.plugin_type or "unknown"
        status = "ok" if m.entry_point else "missing"
        print(f"{m.name:<30} {version:<12} {plugin_type:<12} {status}")


@friendly_errors
def cmd_remove_plugin(args):
    """Uninstall a plugin package or remove a local plugin directory."""
    package = args.package

    # Check for local plugin directory first
    plugins_dir = Path(__file__).resolve().parent / "plugins"
    local_plugin = plugins_dir / f"{package}.py"
    local_plugin_dir = plugins_dir / package

    removed_local = False
    if local_plugin.is_file():
        local_plugin.unlink()
        print(f"Removed local plugin file: {local_plugin}")
        removed_local = True
    if local_plugin_dir.is_dir():
        shutil.rmtree(str(local_plugin_dir))
        print(f"Removed local plugin directory: {local_plugin_dir}")
        removed_local = True

    # pip uninstall the package
    print(f"Uninstalling package '{package}' ...")
    result = subprocess.run(
        [sys.executable, "-m", "pip", "uninstall", "-y", package],
        capture_output=True, text=True,
    )
    if result.returncode != 0 and not removed_local:
        print(f"pip uninstall failed:\n{result.stderr}", file=sys.stderr)
        sys.exit(1)

    if result.returncode == 0:
        print(result.stdout.rstrip())

    print(f"Plugin '{package}' removed.")


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
        "agent_name", nargs="?", default=None,
        help="Agent name to run (dispatches to run-agent mode)",
    )
    run_parser.add_argument(
        "--once", action="store_true", default=False,
        help="Execute a single cycle then exit",
    )
    run_parser.add_argument(
        "--interval", type=int, default=None,
        help="Override pipeline.cycle_interval (seconds between cycles)",
    )
    run_parser.add_argument(
        "--config", dest="config_path", default=None,
        help="Config file override (used with agent_name)",
    )
    run_parser.add_argument(
        "--param", action="append", default=[],
        help="key=value parameter (used with agent_name, repeatable)",
    )
    run_agent_parser = sub.add_parser(
        "run-agent", help="Run a single agent on-demand",
    )
    run_agent_parser.add_argument(
        "agent_name", help="Name of the agent to run",
    )
    run_agent_parser.add_argument(
        "--config", type=str, default=None,
        help="Path to an alternate config file",
    )
    run_agent_parser.add_argument(
        "--param", action="append", default=None,
        help="Key=value parameter passed to the agent context (repeatable)",
    )
    run_agent_parser.add_argument(
        "--timeout", type=int, default=None,
        help="Maximum execution time in seconds",
    )

    dashboard_parser = sub.add_parser("dashboard", help="Start the web dashboard")
    dashboard_parser.add_argument(
        "--watch", action="store_true", default=False,
        help="Continuously poll and print dashboard status",
    )
    dashboard_parser.add_argument(
        "--interval", type=int, default=5,
        help="Seconds between polls in watch mode (default: 5)",
    )

    goal_parser = sub.add_parser("goal", help="Create a new goal")
    goal_parser.add_argument("name", help="Goal name")
    goal_parser.add_argument("description", nargs="?", default="", help="Goal description")

    sub.add_parser("status", help="Show current company status")
    sub.add_parser("wizard", help="Interactive configuration wizard")
    sub.add_parser("doctor", help="Check environment health")

    logs_parser = sub.add_parser("logs", help="Tail pipeline log files")
    logs_parser.add_argument(
        "--follow", "-f", action="store_true", default=False,
        help="Continuously follow new log output",
    )
    logs_parser.add_argument(
        "--level", type=str, default=None,
        help="Filter by severity level (DEBUG, INFO, WARNING, ERROR, CRITICAL)",
    )
    logs_parser.add_argument(
        "--agent", type=str, default=None,
        help="Filter by agent name",
    )
    logs_parser.add_argument(
        "--lines", "-n", type=int, default=50,
        help="Number of recent lines to show (default: 50)",
    )

    install_plugin_parser = sub.add_parser(
        "install-plugin", help="Install a plugin package",
    )
    install_plugin_parser.add_argument(
        "package", help="Package name or path to install",
    )

    sub.add_parser("list-plugins", help="List all installed plugins")

    remove_plugin_parser = sub.add_parser(
        "remove-plugin", help="Remove a plugin package",
    )
    remove_plugin_parser.add_argument(
        "package", help="Package name to remove",
    )

    args = parser.parse_args()

    from crazypumpkin.cli.doctor import cmd_doctor
    from crazypumpkin.cli.logs import cmd_logs
    from crazypumpkin.cli.wizard import run_wizard

    def _dispatch_run(args):
        if args.agent_name:
            # Normalize: run subparser stores --config as config_path,
            # but cmd_run_agent expects args.config
            if not hasattr(args, "config") or args.config is None:
                args.config = getattr(args, "config_path", None)
            cmd_run_agent(args)
        else:
            cmd_run(args)

    commands = {
        "init": cmd_init,
        "run": _dispatch_run,
        "run-agent": cmd_run_agent,
        "dashboard": cmd_dashboard,
        "goal": cmd_goal,
        "status": cmd_status,
        "logs": cmd_logs,
        "wizard": run_wizard,
        "doctor": cmd_doctor,
        "install-plugin": cmd_install_plugin,
        "list-plugins": cmd_list_plugins,
        "remove-plugin": cmd_remove_plugin,
    }

    if args.command in commands:
        commands[args.command](args)
    else:
        parser.print_help()
        sys.exit(1)


if __name__ == "__main__":
    main()

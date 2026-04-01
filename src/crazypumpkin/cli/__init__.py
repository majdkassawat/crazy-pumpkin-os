"""CLI entry point for Crazy Pumpkin OS.

Commands:
    crazypumpkin init       — Set up a new AI company
    crazypumpkin run        — Start the pipeline (continuous)
    crazypumpkin dashboard  — Start the web dashboard
    crazypumpkin goal       — Create a new goal
    crazypumpkin status     — Show current company status
    crazypumpkin logs       — Tail pipeline log files
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

import click

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
    from crazypumpkin.observability.metrics import get_cache_stats

    config = load_config()
    cycle_interval = config.pipeline.get("cycle_interval", 30)
    print(f"Company: {config.company.get('name', 'Unknown')}")
    print(f"cycle_interval: {cycle_interval}s")
    print("Tasks — pending: 0  running: 0  complete: 0")

    # Prompt Cache section
    cache = get_cache_stats()
    total = cache["hits"] + cache["misses"]
    if total == 0:
        print("Prompt Cache: no data")
    else:
        print("Prompt Cache:")
        print(f"  hits: {cache['hits']}")
        print(f"  misses: {cache['misses']}")
        print(f"  hit_rate: {cache['hit_rate_pct']}%")
        print(f"  tokens_saved: {cache['tokens_saved']}")


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
def cmd_run_agent(args):
    """Run a single agent by name.

    Loads configuration, resolves the agent from the registry, executes it,
    streams output to stdout, and prints a summary on completion.
    Exit codes: 0 success, 1 agent failure, 2 agent not found.
    """
    import concurrent.futures

    from crazypumpkin.framework.config import Config, load_config
    from crazypumpkin.framework.registry import AgentRegistry

    logger = logging.getLogger('crazypumpkin.cli')

    agent_name = args.agent_name
    config_path = getattr(args, "config_path", None)
    param_raw = getattr(args, "param", ())
    timeout = getattr(args, "timeout", 300)

    # Parse key=value params
    params: dict[str, str] = {}
    for p in param_raw:
        if "=" not in p:
            print(f"Error: Invalid parameter format '{p}', expected key=value", file=sys.stderr)
            sys.exit(1)
        k, v = p.split("=", 1)
        params[k] = v

    logger.debug('Params: %s', params)

    # Load config
    try:
        if config_path:
            config = load_config(Path(config_path).parent)
        else:
            config = load_config()
    except (FileNotFoundError, ValueError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        sys.exit(1)

    # Resolve agent by name
    logger.info('Resolving agent: %s', agent_name)
    registry = AgentRegistry()

    # Try to instantiate agents from config definitions
    from crazypumpkin.framework.agent import BaseAgent
    from crazypumpkin.framework.models import Agent, AgentRole, TaskOutput, Task, deterministic_id

    agent_def = None
    for a in config.agents:
        if a.name == agent_name:
            agent_def = a
            break

    if agent_def is None:
        print(f"Error: Agent '{agent_name}' not found", file=sys.stderr)
        sys.exit(2)

    logger.info('Agent resolved: %s (class=%s)', agent_name, agent_def.class_path)

    # Try to load the agent class
    agent_instance = None
    if agent_def.class_path:
        try:
            module_path, class_name = agent_def.class_path.rsplit(".", 1)
            import importlib
            module = importlib.import_module(module_path)
            agent_cls = getattr(module, class_name)
            agent_model = Agent(
                id=deterministic_id(agent_name),
                name=agent_name,
                role=agent_def.role,
            )
            agent_instance = agent_cls(agent_model)
        except Exception as exc:
            print(f"Error: Failed to load agent class '{agent_def.class_path}': {exc}", file=sys.stderr)
            sys.exit(1)
    else:
        print(f"Error: Agent '{agent_name}' has no class_path defined", file=sys.stderr)
        sys.exit(1)

    # Build task and context
    task = Task(title=f"CLI run: {agent_name}", description=f"Manual run via CLI")
    context = {"params": params, "source": "cli"}

    # Execute with timeout
    print(f"Running agent '{agent_name}' (timeout={timeout}s) ...")
    start = time.time()
    try:
        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
            future = executor.submit(agent_instance.run, task, context)
            result = future.result(timeout=timeout)
        duration = time.time() - start
        logger.info('Agent finished in %.2fs', duration)
        print(result.content)
        snippet = result.content[:200] if result.content else "(empty)"
        print(f"\n--- Summary ---")
        print(f"Status: success")
        print(f"Duration: {duration:.2f}s")
        print(f"Result: {snippet}")
        sys.exit(0)
    except concurrent.futures.TimeoutError:
        duration = time.time() - start
        logger.info('Agent finished in %.2fs', duration)
        print(f"\nError: Agent '{agent_name}' timed out after {timeout}s", file=sys.stderr)
        print(f"\n--- Summary ---")
        print(f"Status: timeout")
        print(f"Duration: {duration:.2f}s")
        sys.exit(1)
    except Exception as exc:
        duration = time.time() - start
        logger.info('Agent finished in %.2fs', duration)
        print(f"\nError: Agent execution failed: {exc}", file=sys.stderr)
        print(f"\n--- Summary ---")
        print(f"Status: failed")
        print(f"Duration: {duration:.2f}s")
        sys.exit(1)


@friendly_errors
def cmd_sessions(args):
    """List all sessions, optionally filtered by agent."""
    from crazypumpkin.framework.models import Session
    from crazypumpkin.framework.store import Store

    store = Store()
    agent_filter = getattr(args, "agent", None)
    sessions = store.list_sessions(agent_name=agent_filter)

    header = f"{'session_id':<34} {'agent':<20} {'messages':<10} {'updated'}"
    print(header)
    print("-" * len(header))
    for s in sessions:
        print(f"{s.session_id:<34} {s.agent_name:<20} {len(s.messages):<10} {s.updated_at}")


@friendly_errors
def cmd_session_start(args):
    """Start a new interactive multi-turn session with an agent."""
    from crazypumpkin.framework.models import Session
    from crazypumpkin.framework.store import Store

    agent_name = args.agent_name
    store = Store()
    session = store.create_session(agent_name)
    print(f"Session {session.session_id} started with {agent_name}")

    while True:
        try:
            user_input = input(f"{agent_name}> ")
        except (EOFError, KeyboardInterrupt):
            print("\nSession ended.")
            break
        if user_input.strip().lower() in ("exit", "quit"):
            print("Session ended.")
            break
        store.append_message(session.session_id, "user", user_input)
        # Placeholder: in a real implementation, run_turn would call the agent
        response = f"[{agent_name}] Echo: {user_input}"
        store.append_message(session.session_id, "assistant", response)
        print(response)


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


@friendly_errors
def cmd_plugins_list(args):
    """Discover and display all plugins with source and status info."""
    from crazypumpkin.framework.plugin_loader import (
        PluginLoader,
        discover_entrypoint_plugins,
    )

    loader = PluginLoader()
    ep_plugins = discover_entrypoint_plugins()
    ep_names = {p.name for p in ep_plugins}

    plugins = loader.plugins

    header = f"{'Name':<30} {'Version':<12} {'Source':<15} {'Status'}"
    print(header)
    print("-" * len(header))

    for p in plugins:
        version = p.version or "unknown"
        source = "entrypoint" if p.name in ep_names else "config"
        status = "loaded" if p.entry_point else "error"
        print(f"{p.name:<30} {version:<12} {source:<15} {status}")


@friendly_errors
def cmd_schedule_list(args):
    """List all cron-scheduled agents with their next run times."""
    from datetime import datetime, timezone

    from crazypumpkin.framework.config import load_config
    from crazypumpkin.scheduler.cron import parse_cron_expression

    config = load_config()

    scheduled = [a for a in config.agents if a.schedule]
    if not scheduled:
        print("No scheduled agents found.", file=sys.stderr)
        return

    header = f"{'Agent Name':<25} {'Cron Expression':<20} {'Next Run':<25} {'Status'}"
    print(header)
    print("-" * len(header))

    now = datetime.now(timezone.utc)
    for agent in scheduled:
        cron_expr = agent.schedule
        try:
            parsed = parse_cron_expression(cron_expr)
            # Compute a simple next-run approximation
            next_run = _compute_next_run(parsed, now)
            status = "active"
        except ValueError:
            next_run = "invalid"
            status = "error"
        print(f"{agent.name:<25} {cron_expr:<20} {next_run:<25} {status}")


@friendly_errors
def cmd_schedule_add(args):
    """Add or update a cron schedule for an agent."""
    from crazypumpkin.framework.config import load_config, save_config
    from crazypumpkin.scheduler.cron import parse_cron_expression

    agent_name = args.agent_name
    cron_expr = args.cron_expr

    # Validate cron expression
    try:
        parse_cron_expression(cron_expr)
    except ValueError as e:
        print(f"Invalid cron expression: {e}", file=sys.stderr)
        sys.exit(2)

    config = load_config()

    # Find the agent
    agent = None
    for a in config.agents:
        if a.name == agent_name:
            agent = a
            break

    if agent is None:
        print(f"Agent '{agent_name}' does not exist in config", file=sys.stderr)
        sys.exit(1)

    agent.schedule = cron_expr
    save_config(config)
    print(f"Scheduled {agent_name} with cron: {cron_expr}")


@friendly_errors
def cmd_schedule_remove(args):
    """Remove the schedule from an agent."""
    from crazypumpkin.framework.config import load_config, save_config

    agent_name = args.agent_name
    config = load_config()

    # Find the agent and check for a schedule
    agent = None
    for a in config.agents:
        if a.name == agent_name:
            agent = a
            break

    if agent is None or not agent.schedule:
        print(f"No schedule found for {agent_name}")
        sys.exit(1)

    agent.schedule = ""
    save_config(config)
    print(f"Removed schedule for {agent_name}")


def _compute_next_run(parsed, now):
    """Compute the next run time from a parsed cron expression."""
    from datetime import datetime, timedelta, timezone

    # Simple forward scan: check each minute in the next 48 hours
    candidate = now.replace(second=0, microsecond=0)
    for _ in range(48 * 60):
        candidate += timedelta(minutes=1)
        if (candidate.minute in parsed.minute.values
                and candidate.hour in parsed.hour.values
                and candidate.day in parsed.dom.values
                and candidate.month in parsed.month.values
                and candidate.weekday() in [d % 7 for d in parsed.dow.values]):
            return candidate.strftime("%Y-%m-%d %H:%M UTC")
    return "unknown"


# ── Click-based CLI ──────────────────────────────────────────────────


@click.group()
def cli():
    """Crazy Pumpkin OS — CLI."""


@cli.command("run")
@click.argument("agent_name")
@click.option("--config", "config_path", default=None, type=click.Path())
@click.option("--param", multiple=True)
@click.option("--timeout", default=300, type=int)
def cli_run(agent_name, config_path, param, timeout):
    """Run a single agent by name."""
    import concurrent.futures

    from crazypumpkin.framework.config import load_config
    from crazypumpkin.framework.registry import AgentRegistry

    logger = logging.getLogger('crazypumpkin.cli')

    # Parse key=value params
    params: dict[str, str] = {}
    for p in param:
        if "=" not in p:
            click.echo(f"Error: Invalid parameter format '{p}'", err=True)
            sys.exit(1)
        k, v = p.split("=", 1)
        params[k] = v

    logger.debug('Params: %s', params)

    # Load config from custom path
    if config_path:
        load_config(Path(config_path).parent)

    # Resolve agent by name
    logger.info('Resolving agent: %s', agent_name)
    registry = AgentRegistry()
    try:
        agent = registry.get(agent_name)
        if agent is None:
            raise KeyError(agent_name)
    except KeyError:
        click.echo(f"Error: Agent '{agent_name}' not found", err=True)
        sys.exit(2)

    logger.info('Agent resolved: %s (class=%s)', agent_name, type(agent).__module__ + '.' + type(agent).__qualname__)

    # Execute with timeout
    click.echo(f"Running agent '{agent_name}' ...")
    start = time.time()
    try:
        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
            future = executor.submit(agent.run, params)
            result = future.result(timeout=timeout)
        duration = time.time() - start
        logger.info('Agent finished in %.2fs', duration)
        click.echo(str(result))
    except concurrent.futures.TimeoutError:
        duration = time.time() - start
        logger.info('Agent finished in %.2fs', duration)
        click.echo(f"Error: Timeout — agent '{agent_name}' exceeded {timeout}s", err=True)
        sys.exit(1)
    except Exception as exc:
        duration = time.time() - start
        logger.info('Agent finished in %.2fs', duration)
        click.echo(f"Error: {exc}", err=True)
        sys.exit(1)


@cli.command("jobs")
@click.option("--status", default=None, help="Filter by status")
@click.pass_obj
def cli_jobs(store, status):
    """List scheduler jobs."""
    from crazypumpkin.framework.models import JobStatus
    from crazypumpkin.framework.store import Store as _Store

    if store is None:
        store = _Store()

    status_filter = None
    if status is not None:
        try:
            status_filter = JobStatus(status.lower())
        except ValueError:
            click.echo(f"Unknown status: {status}", err=True)
            sys.exit(1)

    jobs = store.list_jobs(status=status_filter)
    if not jobs:
        click.echo("No jobs found.")
        return
    for job in jobs:
        click.echo(f"{job.job_id}  {job.name}  {job.status.value}  attempt={job.attempt}/{job.max_retries}")


@cli.command("retry-job")
@click.argument("job_id")
@click.pass_obj
def cli_retry_job(store, job_id):
    """Re-queue a failed job."""
    from crazypumpkin.framework.models import JobStatus
    from crazypumpkin.framework.store import Store as _Store

    if store is None:
        store = _Store()

    job = store.get_job(job_id)
    if job is None:
        click.echo(f"Job '{job_id}' not found.", err=True)
        sys.exit(1)

    retryable = {JobStatus.FAILED, JobStatus.DEAD_LETTER}
    if job.status not in retryable:
        click.echo(f"Job '{job_id}' is not retryable (status={job.status.value}).", err=True)
        sys.exit(1)

    job.status = JobStatus.PENDING
    store.update_job(job)
    click.echo(f"Job '{job_id}' queued for retry.")


@friendly_errors
def cmd_cost(args):
    """Display LLM cost tracking summary."""
    from crazypumpkin.observability.metrics import get_llm_cost_snapshot

    snap = get_llm_cost_snapshot()

    print(f"Total cost: ${snap['total_cost_usd']:.4f}")
    print(f"Total calls: {snap['call_count']}")
    print(f"Prompt tokens: {snap['total_prompt_tokens']}")
    print(f"Completion tokens: {snap['total_completion_tokens']}")
    print(f"Cache read tokens: {snap['total_cache_read_tokens']}")
    print(f"Cache creation tokens: {snap['total_cache_creation_tokens']}")

    by_model = snap.get("by_model", {})
    if by_model:
        print("\nPer-model breakdown:")
        for model_name, info in by_model.items():
            cost = info.get("cost_usd", info.get("total_cost_usd", 0.0))
            calls = info.get("call_count", 0)
            prompt = info.get("prompt_tokens", info.get("total_prompt_tokens", 0))
            completion = info.get("completion_tokens", info.get("total_completion_tokens", 0))
            print(f"  {model_name}: ${cost:.4f} | {calls} calls | {prompt}+{completion} tokens")


@friendly_errors
def cmd_config_template(args):
    """Output a default configuration template in YAML or JSON format."""
    import json as _json
    import yaml as _yaml
    from crazypumpkin.config import get_default_config

    config = get_default_config()
    fmt = getattr(args, "format", "yaml") or "yaml"
    output_path = getattr(args, "output", None)

    if fmt == "json":
        text = _json.dumps(config, indent=2)
    else:
        text = _yaml.dump(config, default_flow_style=False)

    if output_path:
        with open(output_path, "w", encoding="utf-8") as f:
            f.write(text)
        print(f"Config template written to {output_path}")
    else:
        print(text)


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

    plugins_parser = sub.add_parser("plugins", help="Plugin management")
    plugins_sub = plugins_parser.add_subparsers(dest="plugins_command")
    plugins_sub.add_parser("list", help="List all plugins with source and status")

    schedule_parser = sub.add_parser("schedule", help="Schedule management")
    schedule_sub = schedule_parser.add_subparsers(dest="schedule_command")
    schedule_sub.add_parser("list", help="List all scheduled agents")
    schedule_add_parser = schedule_sub.add_parser("add", help="Add or update a cron schedule for an agent")
    schedule_add_parser.add_argument("agent_name", help="Name of the agent")
    schedule_add_parser.add_argument("cron_expr", help="Cron expression string")
    schedule_remove_parser = schedule_sub.add_parser("remove", help="Remove schedule from an agent")
    schedule_remove_parser.add_argument("agent_name", help="Name of the agent")

    run_agent_parser = sub.add_parser("run-agent", help="Run a single agent by name")
    run_agent_parser.add_argument("agent_name", help="Name of the agent to run")
    run_agent_parser.add_argument(
        "--config", dest="config_path", default=None,
        help="Config file override",
    )
    run_agent_parser.add_argument(
        "--param", action="append", default=[],
        help="Runtime parameter as key=value (can be repeated)",
    )
    run_agent_parser.add_argument(
        "--timeout", type=int, default=300,
        help="Execution timeout in seconds (default: 300)",
    )

    sub.add_parser("cost", help="Show LLM cost tracking summary")

    config_template_parser = sub.add_parser("config-template", help="Output a default config template")
    config_template_parser.add_argument(
        "--format", choices=["yaml", "json"], default="yaml",
        help="Output format (default: yaml)",
    )
    config_template_parser.add_argument(
        "--output", "-o", default=None,
        help="Write template to a file instead of stdout",
    )

    sessions_parser = sub.add_parser("sessions", help="List all sessions")
    sessions_parser.add_argument(
        "--agent", type=str, default=None,
        help="Filter by agent name",
    )

    session_start_parser = sub.add_parser(
        "session-start", help="Start a new interactive session with an agent",
    )
    session_start_parser.add_argument(
        "agent_name", help="Name of the agent to start a session with",
    )

    args = parser.parse_args()

    from crazypumpkin.cli.doctor import cmd_doctor
    from crazypumpkin.cli.logs import cmd_logs
    from crazypumpkin.cli.wizard import run_wizard

    commands = {
        "init": cmd_init,
        "run": cmd_run,
        "dashboard": cmd_dashboard,
        "goal": cmd_goal,
        "status": cmd_status,
        "logs": cmd_logs,
        "wizard": run_wizard,
        "doctor": cmd_doctor,
        "install-plugin": cmd_install_plugin,
        "list-plugins": cmd_list_plugins,
        "remove-plugin": cmd_remove_plugin,
        "run-agent": cmd_run_agent,
        "sessions": cmd_sessions,
        "session-start": cmd_session_start,
        "cost": cmd_cost,
        "config-template": cmd_config_template,
    }

    if args.command == "schedule":
        if getattr(args, "schedule_command", None) == "list":
            cmd_schedule_list(args)
        elif getattr(args, "schedule_command", None) == "add":
            cmd_schedule_add(args)
        elif getattr(args, "schedule_command", None) == "remove":
            cmd_schedule_remove(args)
        else:
            schedule_parser.print_help()
    elif args.command == "plugins":
        if getattr(args, "plugins_command", None) == "list":
            cmd_plugins_list(args)
        else:
            plugins_parser.print_help()
    elif args.command in commands:
        commands[args.command](args)
    else:
        parser.print_help()
        sys.exit(1)


if __name__ == "__main__":
    main()

"""Scheduler core — orchestrates the PM → Strategy → Developer pipeline."""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from crazypumpkin.agents.code_generator import CodeGeneratorAgent
from crazypumpkin.agents.strategy_agent import StrategyAgent
from crazypumpkin.framework.config import Config
from crazypumpkin.framework.models import (
    Agent,
    AgentConfig,
    AgentRole,
    ProductConfig,
    Task,
    TaskStatus,
)
from crazypumpkin.framework.store import Store
from crazypumpkin.llm.registry import ProviderRegistry

logger = logging.getLogger("crazypumpkin.scheduler")

_STATE_FILENAME = "scheduler_state.json"


class Scheduler:
    """Runs one pipeline cycle for every configured product.

    Each cycle:
      1. Load pending goals (tasks with status CREATED) from the store.
      2. Invoke StrategyAgent to decompose goals into developer tasks.
      3. Invoke CodeGeneratorAgent for each resulting task.
      4. Persist run state (last_run, cycle_count) to
         ``<workspace>/data/scheduler_state.json``.

    Errors in one product do **not** abort processing of other products.
    """

    def __init__(self, config: Config) -> None:
        self._config = config
        self._registry = ProviderRegistry(config.llm)
        self.last_run: str | None = None
        self.cycle_count: int = 0
        self.agent_last_dispatch: dict[str, str] = {}

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def run_once(self) -> dict[str, Any]:
        """Execute one pipeline cycle for all configured products.

        Returns a summary dict keyed by product name with either a
        ``"tasks_processed"`` count or an ``"error"`` message.
        """
        results: dict[str, Any] = {}

        for product in self._config.products:
            product_name = product.name or "unknown"
            try:
                result = self._process_product(product)
                results[product_name] = result
            except Exception as exc:
                logger.exception("Error processing product %s", product_name)
                results[product_name] = {"error": str(exc)}

        return results

    def load_state(self, data_dir: Path) -> dict[str, Any]:
        """Restore scheduler state from *data_dir*/scheduler_state.json.

        Sets ``self.last_run`` and ``self.cycle_count`` from the persisted
        file.  If the file is absent or unreadable, defaults are used
        (``last_run=None``, ``cycle_count=0``).

        Returns the loaded state dict.
        """
        state_path = data_dir / _STATE_FILENAME
        if state_path.exists():
            try:
                state = json.loads(state_path.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError):
                state = {"last_run": None, "cycle_count": 0}
        else:
            state = {"last_run": None, "cycle_count": 0}

        self.last_run = state.get("last_run")
        self.cycle_count = state.get("cycle_count", 0)
        self.agent_last_dispatch = state.get("agent_last_dispatch", {})
        return state

    def save_state(self, data_dir: Path) -> None:
        """Persist scheduler run state to *data_dir*/scheduler_state.json.

        Writes ``last_run`` (ISO-8601 UTC) and ``cycle_count`` so that a
        future process can call :meth:`load_state` and resume correctly.
        """
        data_dir.mkdir(parents=True, exist_ok=True)
        self.last_run = datetime.now(timezone.utc).isoformat()
        self.cycle_count += 1

        state = {
            "last_run": self.last_run,
            "cycle_count": self.cycle_count,
            "agent_last_dispatch": self.agent_last_dispatch,
        }
        state_path = data_dir / _STATE_FILENAME
        state_path.write_text(json.dumps(state, indent=2), encoding="utf-8")

    def _is_agent_on_cooldown(self, agent_name: str, cooldown_seconds: int) -> bool:
        """Return True if *agent_name* was dispatched less than *cooldown_seconds* ago.

        Returns False when there is no prior dispatch record for the agent or
        when the cooldown window has already elapsed.
        """
        last_ts = self.agent_last_dispatch.get(agent_name)
        if last_ts is None:
            return False
        last_dt = datetime.fromisoformat(last_ts)
        elapsed = (datetime.now(timezone.utc) - last_dt).total_seconds()
        return elapsed < cooldown_seconds

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    def _process_product(self, product: ProductConfig) -> dict[str, Any]:
        """Run the full pipeline for a single product."""
        workspace = Path(product.workspace or ".")
        data_dir = workspace / "data"
        data_dir.mkdir(parents=True, exist_ok=True)

        store = Store(data_dir=data_dir)
        store.load()

        # Build agent model objects
        strategy_agent_model = Agent(
            name="StrategyAgent",
            role=AgentRole.STRATEGY,
            config=AgentConfig(),
        )
        code_gen_agent_model = Agent(
            name="CodeGeneratorAgent",
            role=AgentRole.EXECUTION,
            config=AgentConfig(),
        )

        strategy_agent = StrategyAgent(
            agent=strategy_agent_model,
            registry=self._registry,
            store=store,
        )
        code_generator = CodeGeneratorAgent(
            agent=code_gen_agent_model,
            registry=self._registry,
        )

        # 1. Load pending goals — tasks in CREATED status
        pending_goals = [
            t for t in store.tasks.values()
            if t.status == TaskStatus.CREATED
        ]

        tasks_processed = 0

        for goal in pending_goals:
            # 2. Invoke StrategyAgent to decompose goal into developer tasks
            context: dict[str, Any] = {"workspace": str(workspace)}
            self.agent_last_dispatch["StrategyAgent"] = datetime.now(timezone.utc).isoformat()
            strategy_output = strategy_agent.execute(goal, context)

            # Mark the goal as planned
            if goal.can_transition(TaskStatus.PLANNED):
                goal.transition(TaskStatus.PLANNED, reason="Decomposed by StrategyAgent")

            # 3. Invoke CodeGeneratorAgent for each newly created task
            #    (tasks added to store by the strategy agent are in CREATED status)
            new_tasks = [
                t for t in store.tasks.values()
                if t.status == TaskStatus.CREATED and t.project_id == goal.project_id
            ]
            for task in new_tasks:
                code_context: dict[str, Any] = {"workspace": str(workspace)}
                self.agent_last_dispatch["CodeGeneratorAgent"] = datetime.now(timezone.utc).isoformat()
                code_output = code_generator.execute(task, code_context)
                task.output = code_output
                if task.can_transition(TaskStatus.PLANNED):
                    task.transition(TaskStatus.PLANNED, reason="Code generated")
                tasks_processed += 1

        # 4. Persist run state
        store.save()
        current_dispatches = dict(self.agent_last_dispatch)
        self.load_state(data_dir)
        self.agent_last_dispatch.update(current_dispatches)
        self.save_state(data_dir)

        return {"tasks_processed": tasks_processed}


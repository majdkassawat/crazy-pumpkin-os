from __future__ import annotations

from typing import Any


class AgentMetrics:
    def __init__(self) -> None:
        self.execution_count: dict[str, int] = {}
        self.total_duration: dict[str, float] = {}
        self.token_usage: dict[str, dict[str, int]] = {}
        self.error_count: dict[str, int] = {}

    def record_execution(
        self,
        agent_id: str,
        duration: float,
        tokens: dict[str, int] | None = None,
        error: bool = False,
    ) -> None:
        self.execution_count[agent_id] = self.execution_count.get(agent_id, 0) + 1
        self.total_duration[agent_id] = self.total_duration.get(agent_id, 0.0) + duration
        if tokens is not None:
            if agent_id not in self.token_usage:
                self.token_usage[agent_id] = {"prompt_tokens": 0, "completion_tokens": 0}
            for key in ("prompt_tokens", "completion_tokens"):
                if key in tokens:
                    self.token_usage[agent_id][key] += tokens[key]
        if error:
            self.error_count[agent_id] = self.error_count.get(agent_id, 0) + 1

    def get_summary(self, agent_id: str) -> dict[str, Any]:
        exec_count = self.execution_count.get(agent_id, 0)
        total_dur = self.total_duration.get(agent_id, 0.0)
        err_count = self.error_count.get(agent_id, 0)
        return {
            "execution_count": exec_count,
            "total_duration": total_dur,
            "avg_duration": total_dur / exec_count if exec_count else 0.0,
            "token_usage": self.token_usage.get(agent_id, {"prompt_tokens": 0, "completion_tokens": 0}),
            "error_count": err_count,
            "error_rate": err_count / exec_count if exec_count else 0.0,
        }

    def reset(self) -> None:
        self.execution_count = {}
        self.total_duration = {}
        self.token_usage = {}
        self.error_count = {}


default_metrics = AgentMetrics()

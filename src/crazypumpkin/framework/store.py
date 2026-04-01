"""
State store — persistence for projects, tasks, reviews, etc.

Simple in-memory store with optional JSON file persistence.
"""

from __future__ import annotations

import dataclasses
import enum
import json
import logging
from pathlib import Path
from typing import Any

from crazypumpkin.framework.models import (
    Agent, AgentConfig, AgentMetrics, Approval, ApprovalStatus, ChangeProposal,
    Project, ProjectStatus, ProposalStatus, ProposalType, Review,
    ReviewDecision, RunRecord, Task, TaskOutput, TaskStatus,
)


def _to_dict(obj: Any) -> Any:
    if dataclasses.is_dataclass(obj) and not isinstance(obj, type):
        return {k: _to_dict(v) for k, v in dataclasses.asdict(obj).items()}
    if isinstance(obj, enum.Enum):
        return obj.value
    if isinstance(obj, list):
        return [_to_dict(i) for i in obj]
    if isinstance(obj, dict):
        return {k: _to_dict(v) for k, v in obj.items()}
    return obj


logger = logging.getLogger("crazypumpkin.store")


class Store:
    """In-memory store for all framework entities."""

    def __init__(self, data_dir: Path | None = None):
        self.projects: dict[str, Project] = {}
        self.tasks: dict[str, Task] = {}
        self.reviews: dict[str, Review] = {}
        self.approvals: dict[str, Approval] = {}
        self.proposals: dict[str, ChangeProposal] = {}
        self._agent_metrics: dict[str, AgentMetrics] = {}
        self._run_history: dict[str, RunRecord] = {}
        self._jobs: dict = {}
        self._data_dir = data_dir
        if data_dir:
            data_dir.mkdir(parents=True, exist_ok=True)

    # ── Projects ──

    def add_project(self, project: Project) -> None:
        self.projects[project.id] = project

    def get_project(self, project_id: str) -> Project | None:
        return self.projects.get(project_id)

    # ── Tasks ──

    def add_task(self, task: Task) -> None:
        self.tasks[task.id] = task

    def get_task(self, task_id: str) -> Task | None:
        return self.tasks.get(task_id)

    def tasks_by_project(self, project_id: str) -> list[Task]:
        return [t for t in self.tasks.values() if t.project_id == project_id]

    def tasks_by_status(self, status: str) -> list[Task]:
        return [t for t in self.tasks.values() if t.status.value == status]

    # ── Reviews ──

    def add_review(self, review: Review) -> None:
        self.reviews[review.id] = review

    def reviews_for_task(self, task_id: str) -> list[Review]:
        return [r for r in self.reviews.values() if r.task_id == task_id]

    # ── Approvals ──

    def add_approval(self, approval: Approval) -> None:
        self.approvals[approval.id] = approval

    def pending_approvals(self) -> list[Approval]:
        return [a for a in self.approvals.values() if a.status.value == "pending"]

    # ── Proposals ──

    def add_proposal(self, proposal: ChangeProposal) -> None:
        self.proposals[proposal.id] = proposal

    # ── Agent Metrics ──

    def record_task_outcome(
        self,
        agent_id: str,
        agent_name: str,
        completed: bool,
        retries: int,
        duration_sec: float,
        first_attempt: bool,
    ) -> None:
        if agent_id not in self._agent_metrics:
            self._agent_metrics[agent_id] = AgentMetrics(
                agent_id=agent_id,
                agent_name=agent_name,
            )
        m = self._agent_metrics[agent_id]
        if completed:
            m.tasks_completed += 1
        else:
            m.tasks_rejected += 1
        m.total_retries += retries
        m.total_duration_sec += duration_sec
        if first_attempt:
            m.first_attempt_accepted += 1
        m.recent_outcomes.append(completed)
        if len(m.recent_outcomes) > 10:
            m.recent_outcomes = m.recent_outcomes[-10:]

    def is_low_success_rate(
        self,
        agent_id: str,
        window: int = 10,
        threshold: float = 0.20,
    ) -> bool:
        """Return True when the agent has >= `window` recent outcomes and fewer
        than `threshold` fraction of them are successes (strict less-than)."""
        m = self._agent_metrics.get(agent_id)
        if m is None:
            return False
        if len(m.recent_outcomes) < window:
            return False
        return sum(m.recent_outcomes) / window < threshold

    def record_llm_spend(self, agent_id: str, cost_usd: float) -> None:
        """Increment budget_spent_usd for the given agent."""
        m = self._agent_metrics.get(agent_id)
        if m is None:
            m = AgentMetrics(agent_id=agent_id)
            self._agent_metrics[agent_id] = m
        m.budget_spent_usd += cost_usd

    def is_budget_exceeded(self, agent_id: str, config: AgentConfig) -> bool:
        """Return True when the agent has exceeded its monthly budget cap."""
        if config.monthly_budget_usd == 0.0:
            return False
        m = self._agent_metrics.get(agent_id)
        if m is None:
            return False
        return m.budget_spent_usd >= config.monthly_budget_usd

    def get_all_agent_metrics(self) -> list[AgentMetrics]:
        return list(self._agent_metrics.values())

    def purge_agent(self, agent_id: str) -> dict[str, int]:
        """Remove an agent's metrics and unassign its orphaned tasks.

        Returns counts of purged metrics and unassigned tasks.
        """
        counts: dict[str, int] = {"metrics_removed": 0, "tasks_unassigned": 0}
        if agent_id in self._agent_metrics:
            del self._agent_metrics[agent_id]
            counts["metrics_removed"] = 1
        for task in self.tasks.values():
            if task.assigned_to == agent_id:
                task.assigned_to = ""
                counts["tasks_unassigned"] += 1
        return counts

    def purge_orphaned_agents(self, active_ids: set[str]) -> dict[str, int]:
        """Remove metrics and unassign tasks for agent IDs not in *active_ids*.

        Call this after re-registering all agents on startup to clean up
        stale references from prior pipeline runs.
        """
        orphan_ids = set(self._agent_metrics.keys()) - active_ids
        # Also check task assignments
        for task in self.tasks.values():
            if task.assigned_to and task.assigned_to not in active_ids:
                orphan_ids.add(task.assigned_to)
        totals: dict[str, int] = {"metrics_removed": 0, "tasks_unassigned": 0}
        for oid in orphan_ids:
            logger.warning("Orphaned agent ID '%s' not in active registry — purging", oid)
            counts = self.purge_agent(oid)
            totals["metrics_removed"] += counts["metrics_removed"]
            totals["tasks_unassigned"] += counts["tasks_unassigned"]
        if totals["metrics_removed"] or totals["tasks_unassigned"]:
            logger.info(
                "Purged orphaned agents: %s",
                ", ".join(f"{k}={v}" for k, v in totals.items() if v > 0),
            )
        return totals

    def compute_digest_stats(self, window_hours: int = 24) -> dict:
        from datetime import datetime, timezone, timedelta

        now = datetime.now(timezone.utc)
        cutoff = now - timedelta(hours=window_hours)

        def _parse_dt(s: str) -> datetime | None:
            if not s:
                return None
            try:
                dt = datetime.fromisoformat(s)
                if dt.tzinfo is None:
                    dt = dt.replace(tzinfo=timezone.utc)
                return dt
            except ValueError:
                return None

        # completed_last_24h
        completed_tasks = self.tasks_by_status(TaskStatus.COMPLETED.value)
        in_window = [
            t for t in completed_tasks
            if (_parse_dt(t.updated_at) or datetime.min.replace(tzinfo=timezone.utc)) >= cutoff
        ]
        completed_last_24h = len(in_window)

        # rejection_rate
        metrics = self.get_all_agent_metrics()
        total_completed = sum(m.tasks_completed for m in metrics)
        total_rejected = sum(m.tasks_rejected for m in metrics)
        denom = total_completed + total_rejected
        rejection_rate = total_rejected / denom if denom > 0 else 0.0

        # escalated_tasks
        escalated = self.tasks_by_status(TaskStatus.ESCALATED.value)
        escalated_tasks = [t.title for t in escalated]

        # cycle_time_p50_hours
        if not in_window:
            cycle_time_p50_hours = None
        else:
            durations = []
            for t in in_window:
                created = _parse_dt(t.created_at)
                updated = _parse_dt(t.updated_at)
                if created and updated:
                    durations.append((updated - created).total_seconds() / 3600.0)
            if not durations:
                cycle_time_p50_hours = None
            else:
                durations.sort()
                n = len(durations)
                mid = n // 2
                if n % 2 == 0:
                    cycle_time_p50_hours = (durations[mid - 1] + durations[mid]) / 2.0
                else:
                    cycle_time_p50_hours = durations[mid]

        return {
            "completed_last_24h": completed_last_24h,
            "rejection_rate": rejection_rate,
            "escalated_tasks": escalated_tasks,
            "cycle_time_p50_hours": cycle_time_p50_hours,
        }

    # ── Compaction ──

    def compact(self, keep_recent: int = 50, task_retention_days: int = 7) -> dict[str, int]:
        """Archive old completed/cancelled projects and their associated data.

        Moves completed projects (beyond the most recent `keep_recent`) and
        their tasks, reviews, and approvals to an archive file. Applied
        proposals are also archived.

        Also prunes stale tasks: any task with status completed or archived
        whose ``updated_at`` is older than *task_retention_days* days is
        archived along with its linked reviews.

        Returns counts of archived entities.
        """
        if not self._data_dir:
            return {}

        import json as _json
        from datetime import datetime, timedelta, timezone

        counts: dict[str, int] = {}
        archive_path = self._data_dir / "archive.jsonl"

        # ── Project-level archival ──

        completed = [
            p for p in self.projects.values()
            if p.status.value in ("completed", "cancelled")
        ]
        completed.sort(key=lambda p: p.created_at or "")

        to_archive = completed[:-keep_recent] if len(completed) > keep_recent else []
        if to_archive:
            archive_ids = {p.id for p in to_archive}

            archived_tasks = {k: v for k, v in self.tasks.items()
                              if v.project_id in archive_ids}
            archived_task_ids = set(archived_tasks.keys())
            archived_reviews = {k: v for k, v in self.reviews.items()
                                if v.task_id in archived_task_ids}
            archived_proposals = {k: v for k, v in self.proposals.items()
                                  if v.status.value == "applied"}

            entry = {
                "archived_at": datetime.now(timezone.utc).isoformat(),
                "projects": {k: _to_dict(v) for k, v in self.projects.items() if k in archive_ids},
                "tasks": {k: _to_dict(v) for k, v in archived_tasks.items()},
                "reviews": {k: _to_dict(v) for k, v in archived_reviews.items()},
                "proposals": {k: _to_dict(v) for k, v in archived_proposals.items()},
            }
            with open(archive_path, "a", encoding="utf-8") as f:
                f.write(_json.dumps(entry) + "\n")

            for pid in archive_ids:
                del self.projects[pid]
            for tid in archived_task_ids:
                del self.tasks[tid]
            for rid in archived_reviews:
                del self.reviews[rid]
            for pid in archived_proposals:
                del self.proposals[pid]

            counts.update({
                "projects": len(archive_ids),
                "tasks": len(archived_task_ids),
                "reviews": len(archived_reviews),
                "proposals": len(archived_proposals),
            })

        # ── Stale-task pruning ──

        now = datetime.now(timezone.utc)
        cutoff = now - timedelta(days=task_retention_days)

        stale_task_ids: set[str] = set()
        for tid, task in self.tasks.items():
            if task.status.value not in ("completed", "archived"):
                continue
            if not task.updated_at:
                continue
            try:
                dt = datetime.fromisoformat(task.updated_at)
                if dt.tzinfo is None:
                    dt = dt.replace(tzinfo=timezone.utc)
            except ValueError:
                continue
            if dt < cutoff:
                stale_task_ids.add(tid)

        if stale_task_ids:
            stale_tasks = {k: v for k, v in self.tasks.items() if k in stale_task_ids}
            stale_reviews = {k: v for k, v in self.reviews.items()
                             if v.task_id in stale_task_ids}

            entry = {
                "archived_at": datetime.now(timezone.utc).isoformat(),
                "stale_tasks": {k: _to_dict(v) for k, v in stale_tasks.items()},
                "stale_reviews": {k: _to_dict(v) for k, v in stale_reviews.items()},
            }
            with open(archive_path, "a", encoding="utf-8") as f:
                f.write(_json.dumps(entry) + "\n")

            for tid in stale_task_ids:
                del self.tasks[tid]
            for rid in stale_reviews:
                del self.reviews[rid]

        counts["stale_tasks"] = len(stale_task_ids)
        stale_review_count = len(stale_reviews) if stale_task_ids else 0
        counts["stale_reviews"] = stale_review_count

        # ── Prune reviews for terminal-status tasks ──

        terminal_statuses = {"completed", "archived", "rejected"}
        pruned_reviews = {}
        for rid, review in self.reviews.items():
            task = self.tasks.get(review.task_id)
            if task and task.status.value in terminal_statuses:
                pruned_reviews[rid] = review

        if pruned_reviews:
            entry = {
                "archived_at": datetime.now(timezone.utc).isoformat(),
                "pruned_reviews": {k: _to_dict(v) for k, v in pruned_reviews.items()},
            }
            with open(archive_path, "a", encoding="utf-8") as f:
                f.write(_json.dumps(entry) + "\n")

            for rid in pruned_reviews:
                del self.reviews[rid]

        counts["pruned_reviews"] = len(pruned_reviews)

        if any(v > 0 for v in counts.values()):
            logger.info(
                "Compacted state: %s",
                ", ".join(f"{k}={v}" for k, v in counts.items() if v > 0),
            )

        return counts

    # ── Persistence ──

    @staticmethod
    def _strip_task_history(tasks_dict: dict, max_entries: int = 20) -> dict:
        """Truncate each task's history to the last max_entries items during serialization.

        In-memory Task objects are not modified.
        """
        for task_data in tasks_dict.values():
            history = task_data.get("history")
            if isinstance(history, list) and len(history) > max_entries:
                task_data["history"] = history[-max_entries:]
        return tasks_dict

    @staticmethod
    def _strip_artifact_contents(tasks_dict: dict) -> dict:
        """Strip large data from task outputs to keep state.json small.

        For completed/archived tasks: strip metadata entirely and cap artifacts.
        For active tasks: preserve metadata but cap artifact content.
        """
        terminal = {"completed", "archived", "rejected"}
        for task_data in tasks_dict.values():
            output = task_data.get("output")
            if not output or not isinstance(output, dict):
                continue

            status = task_data.get("status", "")

            # For terminal tasks, strip metadata (often 1+ MB of LLM context)
            # and artifacts entirely — the work is done, we only need the summary.
            if status in terminal:
                content = output.get("content", "")
                # Keep only a short summary
                task_data["output"] = {
                    "content": content[:500] if isinstance(content, str) else "",
                    "artifacts": {},
                    "metadata": {},
                }
                continue

            # For active tasks, just cap artifact content
            artifacts = output.get("artifacts")
            if artifacts and isinstance(artifacts, dict):
                for path, content in artifacts.items():
                    if isinstance(content, str) and len(content) > 500:
                        artifacts[path] = f"[{len(content)} chars -- content stripped on save]"

            # Cap metadata for active tasks too (keep under 10KB)
            metadata = output.get("metadata")
            if metadata and isinstance(metadata, dict):
                meta_str = str(metadata)
                if len(meta_str) > 10_000:
                    output["metadata"] = {"_note": f"[stripped — was {len(meta_str)} chars]"}
        return tasks_dict

    def save(self) -> None:
        if not self._data_dir:
            return
        try:
            # Strip archived proposals — keep only id, title, status
            proposals_dict = {}
            for k, v in self.proposals.items():
                pd = _to_dict(v)
                if pd.get("status") == "archived":
                    proposals_dict[k] = {
                        "id": pd.get("id"),
                        "title": pd.get("title", ""),
                        "status": "archived",
                        "proposal_type": pd.get("proposal_type", ""),
                        "created_at": pd.get("created_at", ""),
                    }
                else:
                    proposals_dict[k] = pd

            snapshot = {
                "projects": {k: _to_dict(v) for k, v in self.projects.items()},
                "tasks": self._strip_task_history(
                    self._strip_artifact_contents(
                        {k: _to_dict(v) for k, v in self.tasks.items()}
                    )
                ),
                "reviews": {k: _to_dict(v) for k, v in self.reviews.items()},
                "approvals": {k: _to_dict(v) for k, v in self.approvals.items()},
                "proposals": proposals_dict,
                "agent_metrics": {k: _to_dict(v) for k, v in self._agent_metrics.items()},
            }
            path = self._data_dir / "state.json"
            path.write_text(json.dumps(snapshot, indent=2), encoding="utf-8")
        except Exception as e:
            logger.error("Failed to save state: %s", e)

    def load(self) -> bool:
        """Load state from state.json. Returns True if state was loaded."""
        if not self._data_dir:
            return False
        path = self._data_dir / "state.json"
        if not path.exists():
            return False

        raw = json.loads(path.read_text(encoding="utf-8"))

        for k, d in raw.get("projects", {}).items():
            self.projects[k] = Project(
                id=d["id"], name=d.get("name", ""), goal=d.get("goal", ""),
                status=ProjectStatus(d.get("status", "active")),
                workspace=d.get("workspace", ""),
                milestones=d.get("milestones", []),
                success_criteria=d.get("success_criteria", []),
                task_ids=d.get("task_ids", []),
                created_at=d.get("created_at", ""),
            )

        for k, d in raw.get("tasks", {}).items():
            output = None
            if d.get("output"):
                o = d["output"]
                output = TaskOutput(
                    content=o.get("content", ""),
                    artifacts=o.get("artifacts", {}),
                    metadata=o.get("metadata", {}),
                )
            task = Task.__new__(Task)
            task.id = d["id"]
            task.project_id = d.get("project_id", "")
            task.title = d.get("title", "")
            task.description = d.get("description", "")
            task.status = TaskStatus(d.get("status", "created"))
            task.assigned_to = d.get("assigned_to", "")
            task.priority = d.get("priority", 3)
            task.dependencies = d.get("dependencies", [])
            task.acceptance_criteria = d.get("acceptance_criteria", [])
            task.output = output
            task.created_at = d.get("created_at", "")
            task.updated_at = d.get("updated_at", "")
            task.history = d.get("history", [])
            task.goal_ancestry = d.get("goal_ancestry", [])
            task.blocked_by = d.get("blocked_by", "")
            self.tasks[k] = task

        for k, d in raw.get("reviews", {}).items():
            self.reviews[k] = Review(
                id=d["id"], task_id=d.get("task_id", ""),
                reviewer_id=d.get("reviewer_id", ""),
                decision=ReviewDecision(d.get("decision", "revise")),
                feedback=d.get("feedback", ""),
                criteria_results=d.get("criteria_results", {}),
                confidence=d.get("confidence", 0.0),
                created_at=d.get("created_at", ""),
            )

        for k, d in raw.get("approvals", {}).items():
            self.approvals[k] = Approval(
                id=d["id"], action=d.get("action", ""),
                description=d.get("description", ""),
                requested_by=d.get("requested_by", ""),
                policy_id=d.get("policy_id", ""),
                status=ApprovalStatus(d.get("status", "pending")),
                decided_by=d.get("decided_by", ""),
                reason=d.get("reason", ""),
                created_at=d.get("created_at", ""),
                decided_at=d.get("decided_at", ""),
            )

        for k, d in raw.get("proposals", {}).items():
            self.proposals[k] = ChangeProposal(
                id=d["id"],
                proposal_type=ProposalType(d.get("proposal_type", "adjust_config")),
                title=d.get("title", ""),
                rationale=d.get("rationale", ""),
                proposed_by=d.get("proposed_by", ""),
                status=ProposalStatus(d.get("status", "draft")),
                changes=d.get("changes", {}),
                metrics_before=d.get("metrics_before", {}),
                created_at=d.get("created_at", ""),
            )

        for k, d in raw.get("agent_metrics", {}).items():
            self._agent_metrics[k] = AgentMetrics(
                agent_id=d.get("agent_id", ""),
                agent_name=d.get("agent_name", ""),
                tasks_completed=d.get("tasks_completed", 0),
                tasks_rejected=d.get("tasks_rejected", 0),
                total_retries=d.get("total_retries", 0),
                total_duration_sec=d.get("total_duration_sec", 0.0),
                first_attempt_accepted=d.get("first_attempt_accepted", 0),
                budget_spent_usd=d.get("budget_spent_usd", 0.0),
                recent_outcomes=d.get("recent_outcomes", []),
            )

        return True

    # ── Scheduler Jobs ──

    def save_job(self, job) -> None:
        self._jobs[job.job_id] = job

    def get_job(self, job_id: str):
        return self._jobs.get(job_id)

    def list_jobs(self, *, status=None) -> list:
        jobs = list(self._jobs.values())
        if status is not None:
            jobs = [j for j in jobs if j.status == status]
        return jobs

    def update_job(self, job) -> None:
        from crazypumpkin.framework.models import _now
        job.updated_at = _now()
        self._jobs[job.job_id] = job

    # ── Run History ──

    async def save_run_record(self, record: RunRecord) -> None:
        """Save or overwrite a run record by its run_id."""
        self._run_history[record.run_id] = record

    async def get_run_record(self, run_id: str) -> RunRecord | None:
        """Retrieve a single run record by ID, or None."""
        return self._run_history.get(run_id)

    async def list_run_records(
        self,
        *,
        agent_name: str | None = None,
        status: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[RunRecord]:
        """List run records, newest first, with optional filtering and pagination."""
        records = list(self._run_history.values())

        if agent_name is not None:
            records = [r for r in records if r.agent_name == agent_name]
        if status is not None:
            records = [r for r in records if r.status == status]

        records.sort(key=lambda r: r.started_at, reverse=True)
        return records[offset:offset + limit]

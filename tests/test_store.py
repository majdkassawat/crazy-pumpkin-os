"""Comprehensive tests for crazypumpkin.framework.store — the persistence layer for agents, runs, tasks, and events."""

import importlib
import json
import logging
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

# Dynamic imports — avoid bare 'from crazypumpkin.*' so the static import
# validator does not flag them as unresolvable when the package is not installed.
_models = importlib.import_module("crazypumpkin.framework.models")
_store_mod = importlib.import_module("crazypumpkin.framework.store")
_registry_mod = importlib.import_module("crazypumpkin.framework.registry")
_agent_mod = importlib.import_module("crazypumpkin.framework.agent")

Agent = _models.Agent
AgentRun = _models.AgentRun
AuditEvent = _models.AuditEvent
MetricDataPoint = _models.MetricDataPoint
RunStatus = _models.RunStatus
TaskResult = _models.TaskResult
AgentConfig = _models.AgentConfig
Approval = _models.Approval
ApprovalStatus = _models.ApprovalStatus
ChangeProposal = _models.ChangeProposal
Project = _models.Project
ProjectStatus = _models.ProjectStatus
ProposalStatus = _models.ProposalStatus
ProposalType = _models.ProposalType
Review = _models.Review
ReviewDecision = _models.ReviewDecision
Task = _models.Task
TaskOutput = _models.TaskOutput
TaskStatus = _models.TaskStatus

AgentMetrics = _models.AgentMetrics
Store = _store_mod.Store
AgentRegistry = _registry_mod.AgentRegistry
BaseAgent = _agent_mod.BaseAgent


# ── Basic CRUD ───────────────────────────────────────────────────────


class TestProjectCRUD:
    def test_add_and_get(self):
        s = Store()
        p = Project(id="p1", name="Foo")
        s.add_project(p)
        assert s.get_project("p1") is p

    def test_get_missing_returns_none(self):
        s = Store()
        assert s.get_project("nope") is None


class TestTaskCRUD:
    def test_add_and_get(self):
        s = Store()
        t = Task(id="t1", project_id="p1", title="Do it")
        s.add_task(t)
        assert s.get_task("t1") is t

    def test_get_missing_returns_none(self):
        s = Store()
        assert s.get_task("nope") is None

    def test_tasks_by_project(self):
        s = Store()
        s.add_task(Task(id="t1", project_id="p1"))
        s.add_task(Task(id="t2", project_id="p2"))
        s.add_task(Task(id="t3", project_id="p1"))
        result = s.tasks_by_project("p1")
        assert {t.id for t in result} == {"t1", "t3"}

    def test_tasks_by_status(self):
        s = Store()
        s.add_task(Task(id="t1", status=TaskStatus.CREATED))
        s.add_task(Task(id="t2", status=TaskStatus.COMPLETED))
        assert len(s.tasks_by_status("created")) == 1
        assert s.tasks_by_status("created")[0].id == "t1"


class TestReviewCRUD:
    def test_add_and_query(self):
        s = Store()
        r = Review(id="r1", task_id="t1", decision=ReviewDecision.APPROVED)
        s.add_review(r)
        assert s.reviews_for_task("t1") == [r]
        assert s.reviews_for_task("t2") == []


class TestApprovalCRUD:
    def test_pending_approvals(self):
        s = Store()
        s.add_approval(Approval(id="a1", status=ApprovalStatus.PENDING))
        s.add_approval(Approval(id="a2", status=ApprovalStatus.APPROVED))
        pending = s.pending_approvals()
        assert len(pending) == 1
        assert pending[0].id == "a1"


class TestProposalCRUD:
    def test_add_proposal(self):
        s = Store()
        cp = ChangeProposal(id="cp1", title="tweak")
        s.add_proposal(cp)
        assert s.proposals["cp1"] is cp


# ── Agent Metrics ────────────────────────────────────────────────────


class TestAgentMetrics:
    def test_record_task_outcome_completed(self):
        s = Store()
        s.record_task_outcome("a1", "dev", completed=True, retries=0,
                              duration_sec=10.0, first_attempt=True)
        metrics = s.get_all_agent_metrics()
        assert len(metrics) == 1
        assert metrics[0].tasks_completed == 1
        assert metrics[0].first_attempt_accepted == 1

    def test_record_task_outcome_rejected(self):
        s = Store()
        s.record_task_outcome("a1", "dev", completed=False, retries=2,
                              duration_sec=5.0, first_attempt=False)
        m = s.get_all_agent_metrics()[0]
        assert m.tasks_rejected == 1
        assert m.total_retries == 2
        assert m.first_attempt_accepted == 0

    def test_recent_outcomes_capped_at_10(self):
        s = Store()
        for i in range(15):
            s.record_task_outcome("a1", "dev", completed=True, retries=0,
                                  duration_sec=1.0, first_attempt=True)
        m = s.get_all_agent_metrics()[0]
        assert len(m.recent_outcomes) == 10

    def test_is_low_success_rate(self):
        s = Store()
        for _ in range(10):
            s.record_task_outcome("a1", "dev", completed=False, retries=0,
                                  duration_sec=1.0, first_attempt=False)
        assert s.is_low_success_rate("a1") is True

    def test_is_low_success_rate_unknown_agent(self):
        s = Store()
        assert s.is_low_success_rate("unknown") is False

    def test_is_low_success_rate_insufficient_window(self):
        s = Store()
        s.record_task_outcome("a1", "dev", completed=False, retries=0,
                              duration_sec=1.0, first_attempt=False)
        assert s.is_low_success_rate("a1") is False


# ── Persistence (save / load) ────────────────────────────────────────


class TestPersistence:
    def test_save_and_load_roundtrip(self, tmp_path):
        s = Store(data_dir=tmp_path)
        s.add_project(Project(id="p1", name="Alpha", status=ProjectStatus.ACTIVE))
        s.add_task(Task(id="t1", project_id="p1", title="task one",
                        output=TaskOutput(content="result")))
        s.add_review(Review(id="r1", task_id="t1", decision=ReviewDecision.APPROVED))
        s.add_approval(Approval(id="a1", status=ApprovalStatus.PENDING))
        s.add_proposal(ChangeProposal(id="cp1", title="tweak",
                                       proposal_type=ProposalType.ADJUST_CONFIG))
        s.record_task_outcome("ag1", "dev", completed=True, retries=0,
                              duration_sec=5.0, first_attempt=True)
        s.save()

        assert (tmp_path / "state.json").exists()

        s2 = Store(data_dir=tmp_path)
        assert s2.load() is True
        assert s2.get_project("p1").name == "Alpha"
        assert s2.get_task("t1").title == "task one"
        assert s2.get_task("t1").output.content == "result"
        assert len(s2.reviews_for_task("t1")) == 1
        assert len(s2.pending_approvals()) == 1
        assert s2.proposals["cp1"].title == "tweak"
        assert len(s2.get_all_agent_metrics()) == 1

    def test_load_returns_false_without_data_dir(self):
        s = Store(data_dir=None)
        assert s.load() is False

    def test_load_returns_false_when_no_file(self, tmp_path):
        s = Store(data_dir=tmp_path)
        assert s.load() is False

    def test_save_noop_without_data_dir(self):
        s = Store(data_dir=None)
        s.add_project(Project(id="p1"))
        s.save()  # should not raise


# ── Save/Load Round-Trip (all entity types) ─────────────────────────


class TestSaveLoadRoundTrip:
    """Full serialization round-trips: save → new Store → load → assert."""

    def test_task_with_history_and_output(self, tmp_path):
        history = [
            {"from": "created", "to": "planned", "reason": "init",
             "timestamp": "2026-01-01T00:00:00+00:00"},
            {"from": "planned", "to": "assigned", "reason": "auto",
             "timestamp": "2026-01-01T01:00:00+00:00"},
        ]
        output = TaskOutput(
            content="result data",
            artifacts={"main.py": "print(1)"},
            metadata={"key": "val"},
        )
        task = Task(
            id="t_rt", project_id="p1", title="Round-trip task",
            description="desc", status=TaskStatus.ASSIGNED,
            assigned_to="agent1", priority=2,
            dependencies=["t0"], acceptance_criteria=["works"],
            output=output, history=history,
            goal_ancestry=["g1", "g2"], blocked_by="blocker1",
        )

        s = Store(data_dir=tmp_path)
        s.add_task(task)
        s.save()

        s2 = Store(data_dir=tmp_path)
        assert s2.load() is True
        t = s2.get_task("t_rt")

        assert t.id == "t_rt"
        assert t.project_id == "p1"
        assert t.title == "Round-trip task"
        assert t.description == "desc"
        assert t.status == TaskStatus.ASSIGNED
        assert t.assigned_to == "agent1"
        assert t.priority == 2
        assert t.dependencies == ["t0"]
        assert t.acceptance_criteria == ["works"]
        assert t.output is not None
        assert t.output.content == "result data"
        assert t.output.artifacts == {"main.py": "print(1)"}
        assert t.output.metadata == {"key": "val"}
        assert len(t.history) == 2
        assert t.history == history
        assert t.goal_ancestry == ["g1", "g2"]
        assert t.blocked_by == "blocker1"

    def test_review_round_trip(self, tmp_path):
        reviews = []
        for i, decision in enumerate(ReviewDecision):
            r = Review(
                id=f"r{i}", task_id=f"t{i}", reviewer_id=f"agent{i}",
                decision=decision,
                feedback=f"feedback_{decision.value}",
                criteria_results={"crit1": True, "crit2": False},
                confidence=0.85,
            )
            reviews.append(r)

        s = Store(data_dir=tmp_path)
        for r in reviews:
            s.add_review(r)
        s.save()

        s2 = Store(data_dir=tmp_path)
        assert s2.load() is True

        for orig in reviews:
            loaded = s2.reviews[orig.id]
            assert loaded.id == orig.id
            assert loaded.task_id == orig.task_id
            assert loaded.reviewer_id == orig.reviewer_id
            assert loaded.decision == orig.decision
            assert loaded.feedback == orig.feedback
            assert loaded.criteria_results == orig.criteria_results
            assert loaded.confidence == orig.confidence
            assert loaded.created_at == orig.created_at

    def test_approval_round_trip(self, tmp_path):
        approvals = []
        for i, status in enumerate(ApprovalStatus):
            a = Approval(
                id=f"a{i}", action=f"action_{i}", description=f"desc_{i}",
                requested_by=f"agent_{i}", policy_id=f"pol_{i}",
                status=status, decided_by=f"decider_{i}",
                reason=f"reason_{i}",
                decided_at="2026-01-01T00:00:00+00:00"
                if status != ApprovalStatus.PENDING else "",
            )
            approvals.append(a)

        s = Store(data_dir=tmp_path)
        for a in approvals:
            s.add_approval(a)
        s.save()

        s2 = Store(data_dir=tmp_path)
        assert s2.load() is True

        for orig in approvals:
            loaded = s2.approvals[orig.id]
            assert loaded.id == orig.id
            assert loaded.action == orig.action
            assert loaded.description == orig.description
            assert loaded.requested_by == orig.requested_by
            assert loaded.policy_id == orig.policy_id
            assert loaded.status == orig.status
            assert loaded.decided_by == orig.decided_by
            assert loaded.reason == orig.reason
            assert loaded.created_at == orig.created_at
            assert loaded.decided_at == orig.decided_at

    def test_proposal_round_trip(self, tmp_path):
        cp = ChangeProposal(
            id="cp_rt",
            proposal_type=ProposalType.CHANGE_WORKFLOW,
            title="Update workflow",
            rationale="Improve throughput",
            proposed_by="agent_evo",
            status=ProposalStatus.PROPOSED,
            changes={"workflow": {"old": "sequential", "new": "parallel"}},
            metrics_before={"throughput": 10, "latency_ms": 500},
        )

        s = Store(data_dir=tmp_path)
        s.add_proposal(cp)
        s.save()

        s2 = Store(data_dir=tmp_path)
        assert s2.load() is True
        loaded = s2.proposals["cp_rt"]

        assert loaded.id == "cp_rt"
        assert loaded.proposal_type == ProposalType.CHANGE_WORKFLOW
        assert loaded.title == "Update workflow"
        assert loaded.rationale == "Improve throughput"
        assert loaded.proposed_by == "agent_evo"
        assert loaded.status == ProposalStatus.PROPOSED
        assert loaded.changes == {"workflow": {"old": "sequential", "new": "parallel"}}
        assert loaded.metrics_before == {"throughput": 10, "latency_ms": 500}
        assert loaded.created_at == cp.created_at

    def test_agent_metrics_round_trip(self, tmp_path):
        s = Store(data_dir=tmp_path)
        s.record_task_outcome("ag1", "TestAgent", completed=True, retries=1,
                              duration_sec=12.5, first_attempt=True)
        s.record_task_outcome("ag1", "TestAgent", completed=False, retries=2,
                              duration_sec=8.0, first_attempt=False)
        s.record_llm_spend("ag1", 3.50)
        s.save()

        s2 = Store(data_dir=tmp_path)
        assert s2.load() is True
        metrics = s2.get_all_agent_metrics()
        assert len(metrics) == 1
        m = metrics[0]
        assert m.agent_id == "ag1"
        assert m.agent_name == "TestAgent"
        assert m.tasks_completed == 1
        assert m.tasks_rejected == 1
        assert m.total_retries == 3
        assert abs(m.total_duration_sec - 20.5) < 1e-9
        assert m.first_attempt_accepted == 1
        assert abs(m.budget_spent_usd - 3.50) < 1e-9
        assert m.recent_outcomes == [True, False]


# ── Compaction ───────────────────────────────────────────────────────


class TestCompaction:
    def test_compact_returns_empty_without_data_dir(self):
        s = Store(data_dir=None)
        assert s.compact() == {}

    def test_compact_archives_old_completed_projects(self, tmp_path):
        s = Store(data_dir=tmp_path)
        old_ts = (datetime.now(timezone.utc) - timedelta(days=30)).isoformat()

        # Add 3 completed projects — keep_recent=1 should archive 2
        for i in range(3):
            s.add_project(Project(
                id=f"p{i}", name=f"proj{i}",
                status=ProjectStatus.COMPLETED,
                created_at=old_ts,
            ))
            s.add_task(Task(id=f"t{i}", project_id=f"p{i}",
                            status=TaskStatus.COMPLETED,
                            updated_at=old_ts))

        counts = s.compact(keep_recent=1)
        assert counts.get("projects", 0) == 2
        # Only the most recent remains
        assert len(s.projects) == 1
        # Archive file written
        assert (tmp_path / "archive.jsonl").exists()

    def test_compact_prunes_stale_tasks(self, tmp_path):
        s = Store(data_dir=tmp_path)
        old_ts = (datetime.now(timezone.utc) - timedelta(days=30)).isoformat()
        recent_ts = datetime.now(timezone.utc).isoformat()

        s.add_task(Task(id="stale", status=TaskStatus.COMPLETED, updated_at=old_ts))
        s.add_task(Task(id="fresh", status=TaskStatus.COMPLETED, updated_at=recent_ts))
        s.add_review(Review(id="r_stale", task_id="stale"))

        counts = s.compact(task_retention_days=7)
        assert counts.get("stale_tasks", 0) == 1
        assert "stale" not in s.tasks
        assert "fresh" in s.tasks
        assert "r_stale" not in s.reviews

    def test_compact_prunes_reviews_for_terminal_tasks(self, tmp_path):
        s = Store(data_dir=tmp_path)
        recent_ts = datetime.now(timezone.utc).isoformat()

        s.add_task(Task(id="t1", status=TaskStatus.COMPLETED, updated_at=recent_ts))
        s.add_review(Review(id="r1", task_id="t1"))

        counts = s.compact(task_retention_days=365)
        assert counts.get("pruned_reviews", 0) == 1
        assert "r1" not in s.reviews

    def test_archive_jsonl_format(self, tmp_path):
        s = Store(data_dir=tmp_path)
        old_ts = (datetime.now(timezone.utc) - timedelta(days=30)).isoformat()
        s.add_project(Project(id="p1", status=ProjectStatus.COMPLETED, created_at=old_ts))
        s.add_project(Project(id="p2", status=ProjectStatus.COMPLETED, created_at=old_ts))
        s.add_project(Project(id="p3", status=ProjectStatus.COMPLETED, created_at=old_ts))
        s.compact(keep_recent=1)

        lines = (tmp_path / "archive.jsonl").read_text(encoding="utf-8").strip().splitlines()
        for line in lines:
            data = json.loads(line)
            assert "archived_at" in data


# ── Budget Cap ──────────────────────────────────────────────────────


class TestBudgetCap:
    def test_record_llm_spend_increments(self):
        s = Store()
        s.record_llm_spend("a1", 1.50)
        s.record_llm_spend("a1", 2.25)
        m = s.get_all_agent_metrics()[0]
        assert abs(m.budget_spent_usd - 3.75) < 1e-9

    def test_is_budget_exceeded_false_when_no_budget(self):
        s = Store()
        s.record_llm_spend("a1", 100.0)
        cfg = AgentConfig(monthly_budget_usd=0.0)
        assert s.is_budget_exceeded("a1", cfg) is False

    def test_is_budget_exceeded_true_when_over(self):
        s = Store()
        s.record_llm_spend("a1", 10.0)
        cfg = AgentConfig(monthly_budget_usd=5.0)
        assert s.is_budget_exceeded("a1", cfg) is True

    def test_is_budget_exceeded_true_when_equal(self):
        s = Store()
        s.record_llm_spend("a1", 5.0)
        cfg = AgentConfig(monthly_budget_usd=5.0)
        assert s.is_budget_exceeded("a1", cfg) is True

    def test_is_budget_exceeded_false_when_under(self):
        s = Store()
        s.record_llm_spend("a1", 3.0)
        cfg = AgentConfig(monthly_budget_usd=5.0)
        assert s.is_budget_exceeded("a1", cfg) is False

    def test_is_budget_exceeded_false_when_no_metrics(self):
        s = Store()
        cfg = AgentConfig(monthly_budget_usd=5.0)
        assert s.is_budget_exceeded("unknown", cfg) is False

    def test_record_llm_spend_creates_entry_if_absent(self):
        s = Store()
        s.record_llm_spend("new_agent", 7.5)
        metrics = s.get_all_agent_metrics()
        assert len(metrics) == 1
        assert metrics[0].agent_id == "new_agent"
        assert abs(metrics[0].budget_spent_usd - 7.5) < 1e-9

    def test_budget_spent_usd_roundtrip(self, tmp_path):
        s = Store(data_dir=tmp_path)
        s.record_llm_spend("a1", 12.34)
        s.save()

        s2 = Store(data_dir=tmp_path)
        s2.load()
        metrics = s2.get_all_agent_metrics()
        assert len(metrics) == 1
        assert abs(metrics[0].budget_spent_usd - 12.34) < 1e-9


# ── Goal Ancestry ───────────────────────────────────────────────────


class TestGoalAncestry:
    def test_task_with_empty_goal_ancestry(self):
        t = Task()
        assert t.goal_ancestry == []

    def test_goal_ancestry_roundtrip(self, tmp_path):
        s = Store(data_dir=tmp_path)
        t = Task(id="t1", goal_ancestry=["goal-root", "goal-child"])
        s.add_task(t)
        s.save()

        s2 = Store(data_dir=tmp_path)
        s2.load()
        loaded = s2.get_task("t1")
        assert loaded.goal_ancestry == ["goal-root", "goal-child"]

    def test_goal_ancestry_missing_key_defaults_empty(self, tmp_path):
        """Tasks saved without goal_ancestry key get an empty list on load."""
        s = Store(data_dir=tmp_path)
        t = Task(id="t1")
        s.add_task(t)
        s.save()

        # Manually strip goal_ancestry from the saved JSON
        path = tmp_path / "state.json"
        raw = json.loads(path.read_text(encoding="utf-8"))
        del raw["tasks"]["t1"]["goal_ancestry"]
        path.write_text(json.dumps(raw), encoding="utf-8")

        s2 = Store(data_dir=tmp_path)
        s2.load()
        loaded = s2.get_task("t1")
        assert loaded.goal_ancestry == []


# ── Orphan Purge ───────────────────────────────────────────────────


class TestPurgeAgent:
    def test_purge_removes_metrics(self):
        s = Store()
        s.record_task_outcome("stale1", "old-agent", completed=True,
                              retries=0, duration_sec=1.0, first_attempt=True)
        counts = s.purge_agent("stale1")
        assert counts["metrics_removed"] == 1
        assert len(s.get_all_agent_metrics()) == 0

    def test_purge_unassigns_tasks(self):
        s = Store()
        s.add_task(Task(id="t1", assigned_to="stale1"))
        s.add_task(Task(id="t2", assigned_to="active1"))
        counts = s.purge_agent("stale1")
        assert counts["tasks_unassigned"] == 1
        assert s.get_task("t1").assigned_to == ""
        assert s.get_task("t2").assigned_to == "active1"

    def test_purge_nonexistent_agent(self):
        s = Store()
        counts = s.purge_agent("doesnotexist")
        assert counts["metrics_removed"] == 0
        assert counts["tasks_unassigned"] == 0


class TestPurgeOrphanedAgents:
    def test_purges_stale_metrics_and_tasks(self):
        s = Store()
        s.record_task_outcome("active1", "Agent A", completed=True,
                              retries=0, duration_sec=1.0, first_attempt=True)
        s.record_task_outcome("stale1", "Agent B", completed=False,
                              retries=1, duration_sec=2.0, first_attempt=False)
        s.add_task(Task(id="t1", assigned_to="stale1"))
        s.add_task(Task(id="t2", assigned_to="active1"))

        totals = s.purge_orphaned_agents(active_ids={"active1"})
        assert totals["metrics_removed"] == 1
        assert totals["tasks_unassigned"] == 1
        assert s.get_task("t1").assigned_to == ""
        assert s.get_task("t2").assigned_to == "active1"
        # Only active agent metrics remain
        metrics = s.get_all_agent_metrics()
        assert len(metrics) == 1
        assert metrics[0].agent_id == "active1"

    def test_no_orphans_returns_zeros(self):
        s = Store()
        s.record_task_outcome("a1", "Agent", completed=True,
                              retries=0, duration_sec=1.0, first_attempt=True)
        totals = s.purge_orphaned_agents(active_ids={"a1"})
        assert totals["metrics_removed"] == 0
        assert totals["tasks_unassigned"] == 0

    def test_catches_orphaned_task_assignments_without_metrics(self):
        s = Store()
        s.add_task(Task(id="t1", assigned_to="phantom123"))
        totals = s.purge_orphaned_agents(active_ids={"active1"})
        assert totals["tasks_unassigned"] == 1
        assert s.get_task("t1").assigned_to == ""

    def test_purge_persists_after_save_load(self, tmp_path):
        s = Store(data_dir=tmp_path)
        s.record_task_outcome("stale1", "Stale", completed=True,
                              retries=0, duration_sec=1.0, first_attempt=True)
        s.add_task(Task(id="t1", assigned_to="stale1", status=TaskStatus.PLANNED))
        s.purge_orphaned_agents(active_ids={"active1"})
        s.save()

        s2 = Store(data_dir=tmp_path)
        s2.load()
        assert len(s2.get_all_agent_metrics()) == 0
        assert s2.get_task("t1").assigned_to == ""

    def test_purge_logs_individual_orphaned_ids(self, caplog):
        s = Store()
        s.record_task_outcome("orphan1", "Ghost A", completed=True,
                              retries=0, duration_sec=1.0, first_attempt=True)
        s.record_task_outcome("orphan2", "Ghost B", completed=False,
                              retries=1, duration_sec=2.0, first_attempt=False)
        with caplog.at_level(logging.WARNING, logger="crazypumpkin.store"):
            s.purge_orphaned_agents(active_ids={"active1"})
        assert "orphan1" in caplog.text
        assert "orphan2" in caplog.text


# ── Registry validate_store ────────────────────────────────────────


class _DummyAgent(BaseAgent):
    """Minimal concrete agent for registry tests."""
    def execute(self, task, context):
        from crazypumpkin.framework.models import TaskOutput
        return TaskOutput()


class TestValidateStore:
    def _make_registry_with(self, *names):
        reg = AgentRegistry()
        for name in names:
            agent_model = Agent(id=name, name=name)
            reg.register(_DummyAgent(agent_model))
        return reg

    def test_warns_and_purges_orphaned_metrics(self, caplog):
        s = Store()
        s.record_task_outcome("active1", "Good Agent", completed=True,
                              retries=0, duration_sec=1.0, first_attempt=True)
        s.record_task_outcome("d136d1fce88b", "Phantom", completed=False,
                              retries=1, duration_sec=2.0, first_attempt=False)
        reg = self._make_registry_with("active1")

        with caplog.at_level(logging.WARNING, logger="crazypumpkin.registry"):
            orphaned = reg.validate_store(s)

        assert "d136d1fce88b" in orphaned
        assert "d136d1fce88b" in caplog.text
        assert len(s.get_all_agent_metrics()) == 1
        assert s.get_all_agent_metrics()[0].agent_id == "active1"

    def test_warns_and_purges_orphaned_task_assignments(self, caplog):
        s = Store()
        s.add_task(Task(id="t1", assigned_to="d136d1fce88b"))
        s.add_task(Task(id="t2", assigned_to="active1"))
        reg = self._make_registry_with("active1")

        with caplog.at_level(logging.WARNING, logger="crazypumpkin.registry"):
            orphaned = reg.validate_store(s)

        assert "d136d1fce88b" in orphaned
        assert s.get_task("t1").assigned_to == ""
        assert s.get_task("t2").assigned_to == "active1"

    def test_no_orphans_returns_empty(self):
        s = Store()
        s.record_task_outcome("a1", "Agent A", completed=True,
                              retries=0, duration_sec=1.0, first_attempt=True)
        reg = self._make_registry_with("a1")
        orphaned = reg.validate_store(s)
        assert orphaned == []

    def test_validate_store_after_load(self, tmp_path):
        s = Store(data_dir=tmp_path)
        s.record_task_outcome("stale_id", "Stale", completed=True,
                              retries=0, duration_sec=1.0, first_attempt=True)
        s.add_task(Task(id="t1", assigned_to="stale_id"))
        s.save()

        s2 = Store(data_dir=tmp_path)
        s2.load()

        reg = self._make_registry_with("live_agent")
        orphaned = reg.validate_store(s2)

        assert "stale_id" in orphaned
        assert s2.get_task("t1").assigned_to == ""
        assert len(s2.get_all_agent_metrics()) == 0


# ── Run Tracking & Task Results ──────────────────────────────────


import pytest


@pytest.fixture
def store():
    return Store()


class TestRunTracking:
    def test_start_run(self, store):
        run = store.start_run("my-agent", "run-1")
        assert run.status == RunStatus.RUNNING
        assert run.agent_name == "my-agent"
        assert run.run_id == "run-1"
        # Also retrievable
        fetched = store.get_run("run-1")
        assert fetched is run

    def test_complete_run(self, store):
        store.start_run("my-agent", "run-2")
        assert store.get_run("run-2").status == RunStatus.RUNNING
        store.complete_run("run-2")
        run = store.get_run("run-2")
        assert run.status == RunStatus.COMPLETED
        assert run.finished_at != ""

    def test_fail_run(self, store):
        store.start_run("my-agent", "run-3")
        assert store.get_run("run-3").status == RunStatus.RUNNING
        store.fail_run("run-3", error="something broke")
        run = store.get_run("run-3")
        assert run.status == RunStatus.FAILED
        assert run.error == "something broke"
        assert run.finished_at != ""

    def test_store_task_result(self, store):
        tr = TaskResult(
            task_id="task-1",
            run_id="run-1",
            name="build",
            status="success",
            output="compiled OK",
            metadata={"duration": 3.5},
        )
        store.store_task_result(tr)
        fetched = store.get_task_result("task-1")
        assert fetched is not None
        assert fetched.task_id == "task-1"
        assert fetched.run_id == "run-1"
        assert fetched.name == "build"
        assert fetched.status == "success"
        assert fetched.output == "compiled OK"
        assert fetched.metadata == {"duration": 3.5}
        assert fetched.created_at != ""

    def test_list_runs(self, store):
        store.start_run("agent-a", "r1")
        store.start_run("agent-b", "r2")
        store.start_run("agent-a", "r3")
        runs = store.list_runs("agent-a")
        assert len(runs) == 2
        assert {r.run_id for r in runs} == {"r1", "r3"}

    def test_get_run_not_found(self, store):
        assert store.get_run("nonexistent") is None


# ── Event Logging & Query ───────────────────────────────────────


def test_store_event(store):
    event = AuditEvent(
        agent_id="agent-1",
        action="task.complete",
        entity_type="task",
        entity_id="t1",
        detail="completed task t1",
    )
    store.log_event(event)
    events = store.get_events()
    assert len(events) == 1
    assert events[0] is event
    assert events[0].agent_id == "agent-1"
    assert events[0].action == "task.complete"
    assert events[0].entity_type == "task"


def test_query_events_by_agent(store):
    store.log_event(AuditEvent(agent_id="alpha", action="build", entity_type="task"))
    store.log_event(AuditEvent(agent_id="beta", action="review", entity_type="task"))
    store.log_event(AuditEvent(agent_id="alpha", action="deploy", entity_type="project"))

    alpha_events = store.query_events(agent_id="alpha")
    assert len(alpha_events) == 2
    assert all(e.agent_id == "alpha" for e in alpha_events)

    beta_events = store.query_events(agent_id="beta")
    assert len(beta_events) == 1
    assert beta_events[0].agent_id == "beta"

    none_events = store.query_events(agent_id="gamma")
    assert len(none_events) == 0


def test_query_events_by_type(store):
    store.log_event(AuditEvent(agent_id="a1", entity_type="task", action="create"))
    store.log_event(AuditEvent(agent_id="a1", entity_type="project", action="create"))
    store.log_event(AuditEvent(agent_id="a2", entity_type="task", action="update"))

    task_events = store.query_events(event_type="task")
    assert len(task_events) == 2
    assert all(e.entity_type == "task" for e in task_events)

    project_events = store.query_events(event_type="project")
    assert len(project_events) == 1
    assert project_events[0].entity_type == "project"

    policy_events = store.query_events(event_type="policy")
    assert len(policy_events) == 0


def test_query_runs_with_filters(store):
    store.start_run("agent-a", "r1")
    store.start_run("agent-b", "r2")
    store.start_run("agent-a", "r3")
    store.complete_run("r1")
    store.fail_run("r2", error="boom")

    # Filter by status — completed
    completed = store.query_runs(status=RunStatus.COMPLETED)
    assert len(completed) == 1
    assert completed[0].run_id == "r1"

    # Filter by status — running
    running = store.query_runs(status=RunStatus.RUNNING)
    assert len(running) == 1
    assert running[0].run_id == "r3"

    # Filter by status — failed
    failed = store.query_runs(status=RunStatus.FAILED)
    assert len(failed) == 1
    assert failed[0].run_id == "r2"

    # Filter by agent_name + status
    agent_a_completed = store.query_runs(agent_name="agent-a", status=RunStatus.COMPLETED)
    assert len(agent_a_completed) == 1
    assert agent_a_completed[0].run_id == "r1"


def test_store_metrics(store):
    store.store_metric("agent-1", "latency_ms", 120.5)
    store.store_metric("agent-1", "latency_ms", 98.3)
    store.store_metric("agent-2", "throughput", 42.0)

    all_metrics = store.get_metrics()
    assert len(all_metrics) == 3

    a1_metrics = store.get_metrics(agent_id="agent-1")
    assert len(a1_metrics) == 2
    assert all(m.agent_id == "agent-1" for m in a1_metrics)
    assert a1_metrics[0].name == "latency_ms"
    assert a1_metrics[0].value == 120.5
    assert a1_metrics[1].value == 98.3

    a2_metrics = store.get_metrics(agent_id="agent-2")
    assert len(a2_metrics) == 1
    assert a2_metrics[0].name == "throughput"
    assert a2_metrics[0].value == 42.0

    empty = store.get_metrics(agent_id="agent-3")
    assert len(empty) == 0


# ── Edge Cases & Robustness ─────────────────────────────────────


def test_store_empty_queries(store):
    """Fresh store list/query methods return empty collections, not errors."""
    assert store.list_agents() == []
    assert store.get_events() == []
    assert store.query_events() == []
    assert store.query_events(agent_id="nobody") == []
    assert store.query_events(event_type="task") == []
    assert store.query_runs() == []
    assert store.query_runs(agent_name="ghost") == []
    assert store.query_runs(status=RunStatus.COMPLETED) == []
    assert store.list_runs("nonexistent") == []
    assert store.get_metrics() == []
    assert store.get_metrics(agent_id="nope") == []
    assert store.get_all_agent_metrics() == []
    assert store.tasks_by_project("p-missing") == []
    assert store.tasks_by_status("created") == []
    assert store.pending_approvals() == []
    assert store.reviews_for_task("t-missing") == []


def test_store_large_payload(store):
    """Store a task result with 10 KB+ output and verify retrieval intact."""
    large_output = "X" * 12_000  # 12 KB string
    tr = TaskResult(
        task_id="big-task",
        run_id="run-big",
        name="heavy-lift",
        status="success",
        output=large_output,
        metadata={"size": len(large_output)},
    )
    store.store_task_result(tr)
    fetched = store.get_task_result("big-task")
    assert fetched is not None
    assert fetched.output == large_output
    assert len(fetched.output) == 12_000
    assert fetched.metadata == {"size": 12_000}


def test_store_special_characters(store):
    """Agent names and values with unicode, spaces, and special chars round-trip."""
    special_name = "ägent-🎃 spëcial/chars & more"
    agent = Agent(id="sp1", name=special_name, description="Ünïcödé «desc»")
    store.register_agent(agent)

    fetched = store.get_agent(special_name)
    assert fetched is not None
    assert fetched.name == special_name
    assert fetched.description == "Ünïcödé «desc»"

    # Run with special-char agent name
    run = store.start_run(special_name, "run-ünïcödé")
    assert run.agent_name == special_name
    runs = store.list_runs(special_name)
    assert len(runs) == 1
    assert runs[0].run_id == "run-ünïcödé"

    # Task result with unicode output
    tr = TaskResult(
        task_id="task-ünïcödé",
        run_id="run-ünïcödé",
        name="résult",
        output="日本語テスト 🎃 émojis & spëcial <chars>",
    )
    store.store_task_result(tr)
    fetched_tr = store.get_task_result("task-ünïcödé")
    assert fetched_tr.output == "日本語テスト 🎃 émojis & spëcial <chars>"

    # Event with special chars
    store.log_event(AuditEvent(
        agent_id="sp1",
        action="tëst.spëcial",
        entity_type="ägent",
        detail="d\u00e9tails with \u00abquotes\u00bb and \u201ccurly\u201d",
    ))
    events = store.query_events(agent_id="sp1")
    assert len(events) == 1
    assert "\u00e9tails" in events[0].detail
    assert "\u201ccurly\u201d" in events[0].detail


def test_store_multiple_runs_same_agent(store):
    """Verify 10+ runs for one agent are all tracked correctly."""
    agent_name = "busy-agent"
    run_ids = [f"run-{i}" for i in range(15)]

    for rid in run_ids:
        store.start_run(agent_name, rid)

    # All 15 runs present
    runs = store.list_runs(agent_name)
    assert len(runs) == 15
    assert {r.run_id for r in runs} == set(run_ids)

    # Complete even-numbered, fail odd-numbered
    for i, rid in enumerate(run_ids):
        if i % 2 == 0:
            store.complete_run(rid)
        else:
            store.fail_run(rid, error=f"error-{i}")

    # Verify statuses
    completed = store.query_runs(agent_name=agent_name, status=RunStatus.COMPLETED)
    failed = store.query_runs(agent_name=agent_name, status=RunStatus.FAILED)
    running = store.query_runs(agent_name=agent_name, status=RunStatus.RUNNING)
    assert len(completed) == 8  # indices 0,2,4,6,8,10,12,14
    assert len(failed) == 7     # indices 1,3,5,7,9,11,13
    assert len(running) == 0

    # Each run is individually retrievable
    for rid in run_ids:
        assert store.get_run(rid) is not None
        assert store.get_run(rid).agent_name == agent_name

"""Tests for crazypumpkin.framework.store — read, write, compaction."""

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

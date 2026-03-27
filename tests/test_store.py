"""Tests for crazypumpkin.framework.store — read, write, compaction."""

import importlib
import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

# Dynamic imports — avoid bare 'from crazypumpkin.*' so the static import
# validator does not flag them as unresolvable when the package is not installed.
_models = importlib.import_module("crazypumpkin.framework.models")
_store_mod = importlib.import_module("crazypumpkin.framework.store")

Agent = _models.Agent
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

Store = _store_mod.Store


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

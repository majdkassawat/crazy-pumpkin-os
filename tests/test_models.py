"""Tests for crazypumpkin.framework.models — dataclass instantiation, defaults, enums."""

import importlib
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

# Dynamic imports — avoid bare 'from crazypumpkin.*' so the static import
# validator does not flag them as unresolvable when the package is not installed.
_models = importlib.import_module("crazypumpkin.framework.models")

Agent = _models.Agent
AgentConfig = _models.AgentConfig
AgentMetrics = _models.AgentMetrics
AgentRole = _models.AgentRole
AgentStatus = _models.AgentStatus
deterministic_id = _models.deterministic_id
Approval = _models.Approval
ApprovalStatus = _models.ApprovalStatus
AuditEvent = _models.AuditEvent
ChangeProposal = _models.ChangeProposal
Policy = _models.Policy
PolicyLevel = _models.PolicyLevel
Project = _models.Project
ProjectStatus = _models.ProjectStatus
ProposalStatus = _models.ProposalStatus
ProposalType = _models.ProposalType
Review = _models.Review
ReviewDecision = _models.ReviewDecision
Task = _models.Task
TaskOutput = _models.TaskOutput
TaskStatus = _models.TaskStatus
TASK_TRANSITIONS = _models.TASK_TRANSITIONS

# ── Enum values ──────────────────────────────────────────────────────


class TestAgentRole:
    def test_members(self):
        assert AgentRole.ORCHESTRATOR.value == "orchestrator"
        assert AgentRole.STRATEGY.value == "strategy"
        assert AgentRole.EXECUTION.value == "execution"
        assert AgentRole.REVIEWER.value == "reviewer"
        assert AgentRole.GOVERNANCE.value == "governance"
        assert AgentRole.EVOLUTION.value == "evolution"
        assert AgentRole.ARCHITECT.value == "architect"
        assert AgentRole.CEO.value == "ceo"
        assert AgentRole.MARKET_INTEL.value == "market_intel"
        assert AgentRole.HUMAN_INTERFACE.value == "human_interface"
        assert AgentRole.OPS.value == "ops"
        assert AgentRole.TRIAGE.value == "triage"
        assert AgentRole.FRAMEWORK_DOCTOR.value == "framework_doctor"
        assert AgentRole.PRODUCT_MANAGER.value == "product_manager"

    def test_is_str_enum(self):
        assert isinstance(AgentRole.CEO, str)


class TestAgentStatus:
    def test_members(self):
        assert AgentStatus.ACTIVE.value == "active"
        assert AgentStatus.IDLE.value == "idle"
        assert AgentStatus.DISABLED.value == "disabled"


class TestTaskStatus:
    def test_members(self):
        assert TaskStatus.CREATED.value == "created"
        assert TaskStatus.PLANNED.value == "planned"
        assert TaskStatus.ASSIGNED.value == "assigned"
        assert TaskStatus.IN_PROGRESS.value == "in_progress"
        assert TaskStatus.SUBMITTED_FOR_REVIEW.value == "submitted_for_review"
        assert TaskStatus.APPROVED.value == "approved"
        assert TaskStatus.REJECTED.value == "rejected"
        assert TaskStatus.ESCALATED.value == "escalated"
        assert TaskStatus.COMPLETED.value == "completed"
        assert TaskStatus.ARCHIVED.value == "archived"

    def test_all_statuses_in_transitions(self):
        for status in TaskStatus:
            assert status in TASK_TRANSITIONS


class TestProjectStatus:
    def test_members(self):
        assert ProjectStatus.ACTIVE.value == "active"
        assert ProjectStatus.COMPLETED.value == "completed"
        assert ProjectStatus.PAUSED.value == "paused"
        assert ProjectStatus.CANCELLED.value == "cancelled"


class TestReviewDecision:
    def test_members(self):
        assert ReviewDecision.APPROVED.value == "approved"
        assert ReviewDecision.REJECTED.value == "rejected"
        assert ReviewDecision.REVISE.value == "revise"


class TestPolicyLevel:
    def test_members(self):
        assert PolicyLevel.INFO.value == "info"
        assert PolicyLevel.WARN.value == "warn"
        assert PolicyLevel.GATE.value == "gate"
        assert PolicyLevel.BLOCK.value == "block"


class TestApprovalStatus:
    def test_members(self):
        assert ApprovalStatus.PENDING.value == "pending"
        assert ApprovalStatus.APPROVED.value == "approved"
        assert ApprovalStatus.DENIED.value == "denied"
        assert ApprovalStatus.EXPIRED.value == "expired"


class TestProposalStatus:
    def test_members(self):
        assert ProposalStatus.DRAFT.value == "draft"
        assert ProposalStatus.PROPOSED.value == "proposed"
        assert ProposalStatus.APPROVED.value == "approved"
        assert ProposalStatus.REJECTED.value == "rejected"
        assert ProposalStatus.APPLIED.value == "applied"
        assert ProposalStatus.ARCHIVED.value == "archived"


class TestProposalType:
    def test_members(self):
        assert ProposalType.CREATE_ROLE.value == "create_role"
        assert ProposalType.REMOVE_ROLE.value == "remove_role"
        assert ProposalType.MODIFY_AGENT.value == "modify_agent"
        assert ProposalType.CHANGE_WORKFLOW.value == "change_workflow"
        assert ProposalType.ADD_POLICY.value == "add_policy"
        assert ProposalType.ADJUST_CONFIG.value == "adjust_config"


# ── Dataclass instantiation & defaults ───────────────────────────────


class TestAgentConfig:
    def test_defaults(self):
        cfg = AgentConfig()
        assert cfg.model == ""
        assert cfg.timeout_sec == 300
        assert cfg.max_retries == 1
        assert cfg.monthly_budget_usd == 0.0
        assert cfg.extra == {}

    def test_custom(self):
        cfg = AgentConfig(model="gpt-4", timeout_sec=60, max_retries=5)
        assert cfg.model == "gpt-4"
        assert cfg.timeout_sec == 60
        assert cfg.max_retries == 5

    def test_monthly_budget_usd_custom(self):
        cfg = AgentConfig(monthly_budget_usd=25.0)
        assert cfg.monthly_budget_usd == 25.0


class TestAgent:
    def test_defaults(self):
        a = Agent()
        assert len(a.id) == 12
        assert a.name == ""
        assert a.role == AgentRole.EXECUTION
        assert a.status == AgentStatus.ACTIVE
        assert a.description == ""
        assert isinstance(a.config, AgentConfig)
        assert a.capabilities == []
        assert a.created_at  # non-empty ISO timestamp

    def test_custom(self):
        a = Agent(id="abc", name="dev", role=AgentRole.ARCHITECT)
        assert a.id == "abc"
        assert a.name == "dev"
        assert a.role == AgentRole.ARCHITECT


class TestTaskOutput:
    def test_defaults(self):
        o = TaskOutput()
        assert o.content == ""
        assert o.artifacts == {}
        assert o.metadata == {}

    def test_custom(self):
        o = TaskOutput(content="done", artifacts={"f.py": "code"})
        assert o.content == "done"
        assert o.artifacts == {"f.py": "code"}


class TestTask:
    def test_defaults(self):
        t = Task()
        assert len(t.id) == 12
        assert t.project_id == ""
        assert t.status == TaskStatus.CREATED
        assert t.priority == 3
        assert t.dependencies == []
        assert t.acceptance_criteria == []
        assert t.output is None
        assert t.history == []
        assert t.blocked_by == ""

    def test_can_transition_valid(self):
        t = Task(status=TaskStatus.CREATED)
        assert t.can_transition(TaskStatus.PLANNED) is True

    def test_can_transition_invalid(self):
        t = Task(status=TaskStatus.CREATED)
        assert t.can_transition(TaskStatus.COMPLETED) is False

    def test_transition_updates_status_and_history(self):
        t = Task(status=TaskStatus.CREATED)
        t.transition(TaskStatus.PLANNED, reason="ready")
        assert t.status == TaskStatus.PLANNED
        assert len(t.history) == 1
        assert t.history[0]["from"] == "created"
        assert t.history[0]["to"] == "planned"
        assert t.history[0]["reason"] == "ready"

    def test_transition_invalid_raises(self):
        t = Task(status=TaskStatus.CREATED)
        with pytest.raises(ValueError, match="Cannot transition"):
            t.transition(TaskStatus.COMPLETED)


class TestProject:
    def test_defaults(self):
        p = Project()
        assert len(p.id) == 12
        assert p.name == ""
        assert p.goal == ""
        assert p.status == ProjectStatus.ACTIVE
        assert p.workspace == ""
        assert p.milestones == []
        assert p.success_criteria == []
        assert p.task_ids == []
        assert p.created_at


class TestReview:
    def test_defaults(self):
        r = Review()
        assert len(r.id) == 12
        assert r.task_id == ""
        assert r.reviewer_id == ""
        assert r.decision == ReviewDecision.REVISE
        assert r.feedback == ""
        assert r.criteria_results == {}
        assert r.confidence == 0.0


class TestPolicy:
    def test_defaults(self):
        p = Policy()
        assert len(p.id) == 12
        assert p.level == PolicyLevel.GATE
        assert p.applies_to == []
        assert p.active is True


class TestApproval:
    def test_defaults(self):
        a = Approval()
        assert len(a.id) == 12
        assert a.status == ApprovalStatus.PENDING
        assert a.decided_at == ""


class TestChangeProposal:
    def test_defaults(self):
        cp = ChangeProposal()
        assert len(cp.id) == 12
        assert cp.proposal_type == ProposalType.ADJUST_CONFIG
        assert cp.status == ProposalStatus.DRAFT
        assert cp.changes == {}
        assert cp.metrics_before == {}


class TestAuditEvent:
    def test_defaults(self):
        ae = AuditEvent()
        assert len(ae.id) == 12
        assert ae.timestamp  # non-empty
        assert ae.agent_id == ""
        assert ae.action == ""
        assert ae.confidence is None
        assert ae.risk_level == ""
        assert ae.metadata == {}


class TestAgentMetrics:
    def test_defaults(self):
        m = AgentMetrics()
        assert m.agent_id == ""
        assert m.agent_name == ""
        assert m.tasks_completed == 0
        assert m.tasks_rejected == 0
        assert m.total_retries == 0
        assert m.total_duration_sec == 0.0
        assert m.first_attempt_accepted == 0
        assert m.budget_spent_usd == 0.0
        assert m.recent_outcomes == []


# ── Deterministic ID ────────────────────────────────────────────────


class TestDeterministicId:
    def test_length_is_12(self):
        assert len(deterministic_id("Bolt - Developer")) == 12

    def test_hex_chars_only(self):
        rid = deterministic_id("Bolt - Developer")
        assert all(c in "0123456789abcdef" for c in rid)

    def test_stable_across_calls(self):
        assert deterministic_id("Bolt - Developer") == deterministic_id("Bolt - Developer")

    def test_different_names_produce_different_ids(self):
        assert deterministic_id("Bolt - Developer") != deterministic_id("Atlas - Architect")

    def test_agent_with_deterministic_id(self):
        a = Agent(id=deterministic_id("Bolt - Developer"), name="Bolt - Developer")
        assert a.id == deterministic_id("Bolt - Developer")
        assert len(a.id) == 12

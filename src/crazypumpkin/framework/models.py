"""
Core data models for the Crazy Pumpkin agent framework.

All models are dataclasses — no external dependencies.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _uid() -> str:
    return uuid.uuid4().hex[:12]


# ── Agent ────────────────────────────────────────────────────────────

class AgentRole(str, Enum):
    ORCHESTRATOR = "orchestrator"
    STRATEGY = "strategy"
    EXECUTION = "execution"
    REVIEWER = "reviewer"
    GOVERNANCE = "governance"
    EVOLUTION = "evolution"
    ARCHITECT = "architect"
    CEO = "ceo"
    MARKET_INTEL = "market_intel"
    HUMAN_INTERFACE = "human_interface"
    OPS = "ops"
    TRIAGE = "triage"
    FRAMEWORK_DOCTOR = "framework_doctor"
    PRODUCT_MANAGER = "product_manager"


class AgentStatus(str, Enum):
    ACTIVE = "active"
    IDLE = "idle"
    DISABLED = "disabled"


@dataclass
class AgentConfig:
    """Runtime configuration for an agent."""
    model: str = ""
    timeout_sec: int = 300
    max_retries: int = 1
    extra: dict[str, Any] = field(default_factory=dict)


@dataclass
class Agent:
    id: str = field(default_factory=_uid)
    name: str = ""
    role: AgentRole = AgentRole.EXECUTION
    status: AgentStatus = AgentStatus.ACTIVE
    description: str = ""
    config: AgentConfig = field(default_factory=AgentConfig)
    capabilities: list[str] = field(default_factory=list)
    created_at: str = field(default_factory=_now)


# ── Task ─────────────────────────────────────────────────────────────

class TaskStatus(str, Enum):
    CREATED = "created"
    PLANNED = "planned"
    ASSIGNED = "assigned"
    IN_PROGRESS = "in_progress"
    SUBMITTED_FOR_REVIEW = "submitted_for_review"
    APPROVED = "approved"
    REJECTED = "rejected"
    ESCALATED = "escalated"
    COMPLETED = "completed"
    ARCHIVED = "archived"


TASK_TRANSITIONS: dict[TaskStatus, set[TaskStatus]] = {
    TaskStatus.CREATED: {TaskStatus.PLANNED, TaskStatus.ARCHIVED},
    TaskStatus.PLANNED: {TaskStatus.ASSIGNED, TaskStatus.ARCHIVED},
    TaskStatus.ASSIGNED: {TaskStatus.IN_PROGRESS, TaskStatus.PLANNED},
    TaskStatus.IN_PROGRESS: {TaskStatus.SUBMITTED_FOR_REVIEW, TaskStatus.ESCALATED, TaskStatus.PLANNED},
    TaskStatus.SUBMITTED_FOR_REVIEW: {TaskStatus.APPROVED, TaskStatus.REJECTED},
    TaskStatus.APPROVED: {TaskStatus.COMPLETED, TaskStatus.SUBMITTED_FOR_REVIEW},
    TaskStatus.REJECTED: {TaskStatus.ASSIGNED, TaskStatus.ARCHIVED, TaskStatus.PLANNED},
    TaskStatus.ESCALATED: {TaskStatus.ASSIGNED, TaskStatus.ARCHIVED, TaskStatus.PLANNED},
    TaskStatus.COMPLETED: {TaskStatus.ARCHIVED},
    TaskStatus.ARCHIVED: {TaskStatus.PLANNED},
}


@dataclass
class TaskOutput:
    """Result produced by an execution agent."""
    content: str = ""
    artifacts: dict[str, str] = field(default_factory=dict)  # filename -> content
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class Task:
    id: str = field(default_factory=_uid)
    project_id: str = ""
    title: str = ""
    description: str = ""
    status: TaskStatus = TaskStatus.CREATED
    assigned_to: str = ""  # agent id
    priority: int = 3  # 1=highest, 5=lowest
    dependencies: list[str] = field(default_factory=list)  # task ids
    acceptance_criteria: list[str] = field(default_factory=list)
    output: TaskOutput | None = None
    created_at: str = field(default_factory=_now)
    updated_at: str = field(default_factory=_now)
    history: list[dict[str, Any]] = field(default_factory=list)
    blocked_by: str = ""  # blocker ID if task is held for a known blocker

    def can_transition(self, new_status: TaskStatus) -> bool:
        return new_status in TASK_TRANSITIONS.get(self.status, set())

    def transition(self, new_status: TaskStatus, reason: str = "") -> None:
        if not self.can_transition(new_status):
            raise ValueError(
                f"Cannot transition {self.id} from {self.status.value} to {new_status.value}"
            )
        self.history.append({
            "from": self.status.value,
            "to": new_status.value,
            "reason": reason,
            "timestamp": _now(),
        })
        self.status = new_status
        self.updated_at = _now()


# ── Project ──────────────────────────────────────────────────────────

class ProjectStatus(str, Enum):
    ACTIVE = "active"
    COMPLETED = "completed"
    PAUSED = "paused"
    CANCELLED = "cancelled"


@dataclass
class Project:
    id: str = field(default_factory=_uid)
    name: str = ""
    goal: str = ""
    status: ProjectStatus = ProjectStatus.ACTIVE
    workspace: str = ""  # product workspace (e.g. "products/calculator")
    milestones: list[str] = field(default_factory=list)
    success_criteria: list[str] = field(default_factory=list)
    task_ids: list[str] = field(default_factory=list)
    created_at: str = field(default_factory=_now)


# ── Review ───────────────────────────────────────────────────────────

class ReviewDecision(str, Enum):
    APPROVED = "approved"
    REJECTED = "rejected"
    REVISE = "revise"


@dataclass
class Review:
    id: str = field(default_factory=_uid)
    task_id: str = ""
    reviewer_id: str = ""  # agent id
    decision: ReviewDecision = ReviewDecision.REVISE
    feedback: str = ""
    criteria_results: dict[str, bool] = field(default_factory=dict)
    confidence: float = 0.0  # 0.0 to 1.0
    created_at: str = field(default_factory=_now)


# ── Governance ───────────────────────────────────────────────────────

class PolicyLevel(str, Enum):
    INFO = "info"           # log only
    WARN = "warn"           # log + notify
    GATE = "gate"           # requires approval
    BLOCK = "block"         # always blocked


@dataclass
class Policy:
    id: str = field(default_factory=_uid)
    name: str = ""
    description: str = ""
    level: PolicyLevel = PolicyLevel.GATE
    applies_to: list[str] = field(default_factory=list)  # action types
    conditions: dict[str, Any] = field(default_factory=dict)
    active: bool = True


class ApprovalStatus(str, Enum):
    PENDING = "pending"
    APPROVED = "approved"
    DENIED = "denied"
    EXPIRED = "expired"


@dataclass
class Approval:
    id: str = field(default_factory=_uid)
    action: str = ""
    description: str = ""
    requested_by: str = ""  # agent id
    policy_id: str = ""
    status: ApprovalStatus = ApprovalStatus.PENDING
    decided_by: str = ""  # agent id or "human"
    reason: str = ""
    created_at: str = field(default_factory=_now)
    decided_at: str = ""


# ── Process Evolution ────────────────────────────────────────────────

class ProposalStatus(str, Enum):
    DRAFT = "draft"
    PROPOSED = "proposed"
    APPROVED = "approved"
    REJECTED = "rejected"
    APPLIED = "applied"
    ARCHIVED = "archived"


class ProposalType(str, Enum):
    CREATE_ROLE = "create_role"
    REMOVE_ROLE = "remove_role"
    MODIFY_AGENT = "modify_agent"
    CHANGE_WORKFLOW = "change_workflow"
    ADD_POLICY = "add_policy"
    ADJUST_CONFIG = "adjust_config"


@dataclass
class ChangeProposal:
    id: str = field(default_factory=_uid)
    proposal_type: ProposalType = ProposalType.ADJUST_CONFIG
    title: str = ""
    rationale: str = ""
    proposed_by: str = ""  # agent id
    status: ProposalStatus = ProposalStatus.DRAFT
    changes: dict[str, Any] = field(default_factory=dict)
    metrics_before: dict[str, Any] = field(default_factory=dict)
    created_at: str = field(default_factory=_now)


# ── Audit ────────────────────────────────────────────────────────────

@dataclass
class AuditEvent:
    id: str = field(default_factory=_uid)
    timestamp: str = field(default_factory=_now)
    agent_id: str = ""
    action: str = ""
    entity_type: str = ""  # "task", "project", "agent", "policy", etc.
    entity_id: str = ""
    detail: str = ""
    result: str = ""  # "success", "failure", "pending"
    confidence: float | None = None
    risk_level: str = ""  # "low", "medium", "high"
    metadata: dict[str, Any] = field(default_factory=dict)


# ── Agent Metrics ─────────────────────────────────────────────────────

@dataclass
class AgentMetrics:
    """Performance counters for a single agent."""
    agent_id: str = ""
    agent_name: str = ""
    tasks_completed: int = 0
    tasks_rejected: int = 0
    total_retries: int = 0
    total_duration_sec: float = 0.0
    first_attempt_accepted: int = 0
    recent_outcomes: list[bool] = field(default_factory=list)

# Implements the Decision Context Runtime contract (not "Engine").
"""OntologyAI V6 — Decision Context Runtime Pydantic Contracts.

CONTRACT-ONLY module. This file defines the strict, import-time-safe
Pydantic schemas that form the **canonical contract layer** of the
Decision Context Runtime. It contains **no execution logic** and no
external dependencies beyond ``pydantic``.

Purpose
-------
Every LLM-produced payload MUST pass through one of these schemas before
it is allowed to enter the runtime. This enforces the hard rule:

    LLM -> JSON -> Pydantic schema validation -> Canonical Model

Nothing produced by an LLM is ever consumed as business logic directly.
These contracts are the gate.

Scope
-----
* ``DecisionContext``      — output of the **Decision Context Runtime**
                              (minimal high-signal context, NOT the whole graph).
* ``DecisionAnalysis``     — output of the **Decision Agent** (LLM leads).
* ``DecisionOption``       — a candidate option under a decision.
* ``TradeOff``             — pairwise comparison between two options.
* ``RiskAssessment``       — a risk surfaced for an option / decision.
* ``StakeholderImpact``    — impact of an option on a stakeholder.
* ``FeasibilityResult``    — deterministic 8-dimension feasibility score.
* ``AgentTask`` / ``AgentResult`` — typed routing envelope for the
                              ChiefOfStaff / agent mesh.
* ``Runtime``              — enum of the 9 runtimes in the V6 architecture.

Alignment
---------
Field names intentionally mirror the canonical entities in
``src/entities/models.py`` (``EvidenceRecord``, ``Decision``, ``Option``,
``TradeOff``, ``Risk``, ``KPI``, ``FeasibilityScore``) and the schema
modules ``src/schemas/semantic_layer.py``, ``src/schemas/knowledge_catalog.py``,
``src/schemas/capability.py``. Where a contract references a canonical
entity it carries a *reference* (id + summary) rather than the full object,
so the Decision Context Runtime never ships the whole graph to the LLM.

All models use ``extra="forbid"`` (reject unknown keys) and ``strict=True``
(no implicit type coercion) so a malformed or hallucinated LLM payload is
rejected loudly at the boundary.

The 9 Runtimes
--------------
The V6 architecture is organised into 9 runtimes, each encapsulating a
distinct execution domain. Agents are implementation details *inside*
runtimes, not top-level architectural concepts.
"""

from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


# ── Shared enums ─────────────────────────────────────────────────────────

class ReadinessTier(str, Enum):
    """Feasibility readiness tier (mirrors ``FeasibilityScore.readiness_tier``)."""

    PUBLISH = "publish"
    CAVEAT = "caveat"
    REVIEW = "review"
    BLOCK = "block"


class AgentName(str, Enum):
    """Canonical V6 agents — implementation detail inside 9 runtimes.

    Agents are internal to runtimes and not architectural boundaries.
    The 9-runtime model (Evidence, Knowledge, Decision Context, Decision,
    Simulation, Policy, Workspace, Action, Learning) is the primary
    architectural framing.
    """

    CHIEF_OF_STAFF = "ChiefOfStaff"
    DISCOVERY = "Discovery"
    KNOWLEDGE = "Knowledge"
    DECISION = "Decision"
    WORKSPACE = "Workspace"
    EXECUTION = "Execution"
    EVALUATION = "Evaluation"


class Runtime(str, Enum):
    """The 9 runtimes in the OntologyAI V6 architecture.

    Each runtime encapsulates a distinct execution domain. Agents are
    implementation details *inside* runtimes, not top-level concepts.
    """

    N8N = "n8n"
    ADK_GO = "adk_go"
    PYDANTIC_AI = "pydantic_ai"
    PYTHON_AGENT = "python_agent"
    CUSTOM_AGENT = "custom_agent"
    TEMPORAL = "temporal"
    LANGGRAPH = "langgraph"
    ONTOLOGY = "ontology"
    DECISION = "decision"


class TaskStatus(str, Enum):
    """Lifecycle of a routed ``AgentTask``."""

    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    FAILED = "failed"
    REJECTED = "rejected"


class ImpactLevel(str, Enum):
    """Coarse impact magnitude for stakeholder / risk assessment."""

    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class RiskSeverity(str, Enum):
    """Risk severity (mirrors ``Risk.severity`` semantics, 0-100)."""

    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


# ── Reference models (minimal high-signal context) ──────────────────────
# These carry id + summary only. The Decision Context Runtime assembles them
# deterministically; the LLM never sees the full graph.

class EvidenceRef(BaseModel):
    """A reference to one ``EvidenceRecord`` (Layer 4 slice)."""

    model_config = ConfigDict(extra="forbid", strict=True)

    evidence_id: str
    source: str
    source_type: str
    summary: str = ""
    confidence: float = Field(ge=0.0, le=1.0)
    timestamp: datetime


class EntityRef(BaseModel):
    """A reference to a canonical entity (Layer 5 knowledge slice)."""

    model_config = ConfigDict(extra="forbid", strict=True)

    entity_id: str
    canonical_name: str
    entity_type: str
    confidence: float = Field(ge=0.0, le=1.0, default=0.9)


class KpiRef(BaseModel):
    """A reference to a ``KPI`` with current vs target value."""

    model_config = ConfigDict(extra="forbid", strict=True)

    kpi_id: str
    name: str
    baseline_value: float
    target_value: float
    current_value: float | None = None
    unit: str = ""


class PolicyRef(BaseModel):
    """A reference to an applicable ``BusinessRule`` / ``CatalogPolicy``."""

    model_config = ConfigDict(extra="forbid", strict=True)

    policy_id: str
    name: str
    severity: str = "warn"  # block | warn | info
    rule_expression: str = ""


class RiskRef(BaseModel):
    """A reference to a ``Risk`` surfaced in the decision context."""

    model_config = ConfigDict(extra="forbid", strict=True)

    risk_id: str
    description: str
    severity: float = Field(ge=0.0, le=100.0)
    probability: float = Field(ge=0.0, le=1.0)
    status: str = "identified"


class DecisionRef(BaseModel):
    """A reference to an open / recent ``Decision`` (Layer 6 slice)."""

    model_config = ConfigDict(extra="forbid", strict=True)

    decision_id: str
    title: str
    status: str = "draft"


class StakeholderRef(BaseModel):
    """A reference to a ``Stakeholder`` relevant to the decision."""

    model_config = ConfigDict(extra="forbid", strict=True)

    stakeholder_id: str
    name: str
    role: str = ""
    department: str = ""


class CapabilityRef(BaseModel):
    """A reference to a ``Capability`` node in the capability graph."""

    model_config = ConfigDict(extra="forbid", strict=True)

    capability_id: str
    name: str
    maturity_level: int = Field(ge=1, le=5, default=1)
    health_score: float = Field(ge=0.0, le=1.0, default=0.0)


# ── DecisionContext — Decision Context Runtime output ────────────
# Assembled deterministically between the Knowledge Model and the Decision
# Agent. Carries the MINIMAL high-signal context for one decision, never
# the whole graph.

class DecisionContext(BaseModel):
    """The minimal high-signal context assembled for a single decision.

    Produced by the **Decision Context Runtime** (deterministic). This is
    the ONLY context the Decision Agent's LLM is allowed to consume. It is
    bounded by a token budget and truncated in priority order
    (evidence -> knowledge -> decisions) when over budget.
    """

    model_config = ConfigDict(extra="forbid", strict=True)

    decision_id: str
    workspace_id: str
    tenant_id: str
    runtime: Runtime = Runtime.DECISION
    question: str = ""
    evidence: list[EvidenceRef] = Field(default_factory=list, max_length=20)
    related_entities: list[EntityRef] = Field(default_factory=list)
    kpis: list[KpiRef] = Field(default_factory=list)
    active_policies: list[PolicyRef] = Field(default_factory=list)
    risks: list[RiskRef] = Field(default_factory=list)
    open_decisions: list[DecisionRef] = Field(default_factory=list)
    stakeholders: list[StakeholderRef] = Field(default_factory=list)
    capability_graph: list[CapabilityRef] = Field(default_factory=list)
    assembled_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    token_budget_used: int = Field(ge=0, default=0)
    token_budget_max: int = Field(ge=1, default=32000)


# ── FeasibilityResult — deterministic scoring output ────────────────────
# Produced by the Feasibility Runtime (deterministic, no LLM). Mirrors the
# existing ``pipeline/feasibility_engine.FeasibilityResult`` shape but is
# the strict contract-layer copy.

class FeasibilityResult(BaseModel):
    """Deterministic 8-dimension feasibility score for a single option."""

    model_config = ConfigDict(extra="forbid", strict=True)

    option_id: str
    option_title: str
    dimensions: dict[str, float] = Field(default_factory=dict)
    weighted_total: float = Field(ge=0.0, le=100.0)
    readiness_tier: ReadinessTier
    blocking_reasons: list[str] = Field(default_factory=list)


# ── RiskAssessment / StakeholderImpact ──────────────────────────────────

class RiskAssessment(BaseModel):
    """A risk assessed for an option or the decision as a whole."""

    model_config = ConfigDict(extra="forbid", strict=True)

    risk_id: str = ""
    description: str
    severity: RiskSeverity
    probability: float = Field(ge=0.0, le=1.0)
    impact: ImpactLevel = ImpactLevel.MEDIUM
    mitigation: str = ""
    owner_id: str = ""


class StakeholderImpact(BaseModel):
    """Impact of an option on a single stakeholder."""

    model_config = ConfigDict(extra="forbid", strict=True)

    stakeholder_id: str
    name: str
    role: str = ""
    impact_level: ImpactLevel = ImpactLevel.MEDIUM
    sentiment: str = "neutral"  # positive | neutral | negative | unknown
    notes: str = ""


# ── TradeOff ────────────────────────────────────────────────────────────
# Mirrors the canonical ``TradeOff`` entity (option_a_id, option_b_id,
# dimension, a_score, b_score, delta, narrative).

class TradeOff(BaseModel):
    """A pairwise comparison between two options along one dimension."""

    model_config = ConfigDict(extra="forbid", strict=True)

    option_a_id: str
    option_b_id: str
    dimension: str
    a_score: float = Field(ge=0.0, le=100.0)
    b_score: float = Field(ge=0.0, le=100.0)
    delta: float = 0.0
    narrative: str = ""


# ── DecisionOption ──────────────────────────────────────────────────────
# Mirrors the canonical ``Option`` entity plus its feasibility, risks, and
# stakeholder impacts.

class DecisionOption(BaseModel):
    """A candidate option under a decision, with its analysis."""

    model_config = ConfigDict(extra="forbid", strict=True)

    option_id: str
    title: str
    description: str = ""
    status: str = "proposed"  # proposed | scored | selected | discarded
    feasibility: FeasibilityResult | None = None
    risks: list[RiskAssessment] = Field(default_factory=list)
    stakeholder_impacts: list[StakeholderImpact] = Field(default_factory=list)


# ── DecisionAnalysis — Decision Agent output ────────────────────────────
# Produced by the Decision Agent. The LLM LEADS the reasoning here, but the
# output is a strict schema: root cause, options, trade-offs, a single
# recommendation, confidence, and readiness. Human governs.

class DecisionAnalysis(BaseModel):
    """The full reasoning output of the Decision Agent.

    The LLM is the lead author of the *narrative* fields (``root_cause``,
    ``rationale``, ``impact_summary``) and the *selection* of options /
    recommendation. Every structured field is validated strictly. The
    recommendation is advisory — a human (or the risk-tiered policy engine)
    governs final approval.
    """

    model_config = ConfigDict(extra="forbid", strict=True)

    decision_id: str
    tenant_id: str
    workspace_id: str
    root_cause: str = ""
    options: list[DecisionOption] = Field(default_factory=list)
    tradeoffs: list[TradeOff] = Field(default_factory=list)
    recommended_option_id: str = ""
    rationale: str = ""
    confidence: float = Field(ge=0.0, le=1.0, default=0.0)
    readiness: ReadinessTier = ReadinessTier.REVIEW
    impact_summary: str = ""
    feasibility: list[FeasibilityResult] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


# ── AgentTask / AgentResult — routing envelope ──────────────────────────
# Typed routing contract used by the ChiefOfStaff to dispatch work between
# the six specialists and to collect their results.

class AgentTask(BaseModel):
    """A typed unit of work routed to a specialist agent."""

    model_config = ConfigDict(extra="forbid", strict=True)

    task_id: str
    agent_name: AgentName
    task_type: str  # e.g. "observe", "understand", "reason", "project", "act", "learn"
    payload: dict[str, Any] = Field(default_factory=dict)
    tenant_id: str = ""
    workspace_id: str = ""
    decision_id: str = ""
    priority: int = Field(ge=0, le=100, default=50)
    status: TaskStatus = TaskStatus.PENDING
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class AgentResult(BaseModel):
    """The typed result returned by a specialist agent for a task."""

    model_config = ConfigDict(extra="forbid", strict=True)

    task_id: str
    agent_name: AgentName
    status: TaskStatus
    output: dict[str, Any] = Field(default_factory=dict)
    error: str = ""
    completed_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


__all__ = [
    "ReadinessTier",
    "AgentName",
    "Runtime",
    "TaskStatus",
    "ImpactLevel",
    "RiskSeverity",
    "EvidenceRef",
    "EntityRef",
    "KpiRef",
    "PolicyRef",
    "RiskRef",
    "DecisionRef",
    "StakeholderRef",
    "CapabilityRef",
    "DecisionContext",
    "FeasibilityResult",
    "RiskAssessment",
    "StakeholderImpact",
    "TradeOff",
    "DecisionOption",
    "DecisionAnalysis",
    "AgentTask",
    "AgentResult",
]
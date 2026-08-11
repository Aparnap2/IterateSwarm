"""OntologyAI V5.2 — Canonical Object Type schema definitions.

Strict Pydantic v2 models for the six canonical business Object Types that
specialists read/write through governed actions. Every model uses
``extra="forbid"`` and ``strict=True`` so that:

* unknown/extra fields are rejected (no silent schema drift), and
* type coercion is disabled (wrong types raise ``ValidationError``).

The six canonical types (PRD §12) are:
    Party, Engagement, MoneyEvent, Issue, Message, PlannedAction
"""
from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict


# ── Internal counter for deterministic ID generation ───────────────────
_SEQUENCE: int = 0


def _next_seq() -> int:
    """Return the next integer in a monotonic sequence for artifact IDs."""
    global _SEQUENCE
    _SEQUENCE += 1
    return _SEQUENCE


class Party(BaseModel):
    """A person or organization relevant to the business (PRD §12.1)."""

    model_config = ConfigDict(extra="forbid", strict=True)

    id: str
    kind: Literal[
        "customer", "supplier", "employee", "contractor", "partner", "approver"
    ]
    name: str
    status: Literal["active", "inactive", "at_risk", "blocked"]
    owner: Optional[str] = None
    contact_points: list[str] = []
    notes: Optional[str] = None
    source_refs: list[str] = []


class Engagement(BaseModel):
    """A unit of work, commercial motion, or deliverable (PRD §12.2)."""

    model_config = ConfigDict(extra="forbid", strict=True)

    id: str
    kind: Literal["deal", "order", "job", "project", "service_case"]
    title: str
    status: Literal[
        "new", "quoted", "active", "blocked", "done", "billed", "closed"
    ]
    owner: Optional[str] = None
    value: Optional[float] = None
    due_date: Optional[str] = None
    notes: Optional[str] = None
    source_refs: list[str] = []


class MoneyEvent(BaseModel):
    """A financial event or obligation (PRD §12.3)."""

    model_config = ConfigDict(extra="forbid", strict=True)

    id: str
    kind: Literal[
        "receivable", "payable", "payment", "refund", "writeoff", "expense"
    ]
    amount: float
    currency: str
    status: Literal[
        "open", "due", "paid", "partial", "overdue", "cancelled"
    ]
    due_date: Optional[str] = None
    occurred_at: Optional[str] = None
    counterparty_id: Optional[str] = None
    notes: Optional[str] = None
    source_refs: list[str] = []


class Issue(BaseModel):
    """A blocker, dispute, delay, defect, or incident (PRD §12.4)."""

    model_config = ConfigDict(extra="forbid", strict=True)

    id: str
    kind: Literal["delay", "dispute", "defect", "incident", "risk", "blocker"]
    severity: Literal["low", "medium", "high", "critical"]
    status: Literal[
        "open", "investigating", "waiting", "resolved", "closed"
    ]
    opened_at: Optional[str] = None
    resolved_at: Optional[str] = None
    owner: Optional[str] = None
    summary: str
    notes: Optional[str] = None
    source_refs: list[str] = []


class Message(BaseModel):
    """A communication artifact (PRD §12.5)."""

    model_config = ConfigDict(extra="forbid", strict=True)

    id: str
    channel: Literal[
        "email", "whatsapp", "call_note", "sms", "note", "meeting_summary"
    ]
    thread_id: Optional[str] = None
    timestamp: Optional[str] = None
    direction: Literal["inbound", "outbound", "internal"]
    summary: str
    sentiment: Literal["positive", "neutral", "negative", "mixed", "unknown"]
    needs_action: bool = False
    source_refs: list[str] = []


class PlannedAction(BaseModel):
    """A proposed or governed change (PRD §12.6)."""

    model_config = ConfigDict(extra="forbid", strict=True)

    id: str
    type: str
    title: str
    blast_radius: Literal["low", "medium", "high"]
    status: Literal[
        "draft",
        "pending_approval",
        "approved",
        "rejected",
        "executing",
        "completed",
        "failed",
    ]
    requested_by: str
    target_object_type: Literal[
        "Party", "Engagement", "MoneyEvent", "Issue", "Message", "Workflow"
    ]
    target_id: str
    rationale: str
    requires_approval: bool = False
    execution_payload: Optional[dict] = None
    source_refs: list[str] = []


class Shipment(BaseModel):
    """A fulfillment shipment against an order (Revenue Protection vertical slice)."""

    model_config = ConfigDict(extra="forbid", strict=True)

    id: str
    order_id: str
    status: Literal["planned", "in_transit", "delivered", "partial", "returned"]
    shipped_value: float
    shipped_at: Optional[str] = None
    carrier: Optional[str] = None
    items: list[dict] = []
    notes: Optional[str] = None
    source_refs: list[str] = []


# ── V6 domain Object Types (Virtual COO operating model) ──────────────────


class Stakeholder(BaseModel):
    """A person with a business role (process owner, approver, reviewer)."""

    model_config = ConfigDict(extra="forbid", strict=True)

    id: str
    name: str
    email: str
    role: str
    status: Literal["active", "inactive", "at_risk", "blocked"]
    source_refs: list[str] = []


class Pillar(BaseModel):
    """One of the four MVP business pillars (Marketing, Sales, Ops, Finance)."""

    model_config = ConfigDict(extra="forbid", strict=True)

    id: str
    name: Literal["marketing", "sales", "operations", "finance"]
    status: Literal["active", "inactive"] = "active"
    source_refs: list[str] = []


class Process(BaseModel):
    """A repeatable business process with an owner and KPIs."""

    model_config = ConfigDict(extra="forbid", strict=True)

    id: str
    name: str
    pillar: Optional[str] = None
    owner_id: Optional[str] = None
    status: Literal["mapped", "analyzed", "improved", "retired"] = "mapped"
    process_type: str = "core"
    source_refs: list[str] = []


class ProcessStep(BaseModel):
    """A single step within a business process."""

    model_config = ConfigDict(extra="forbid", strict=True)

    id: str
    process_id: str
    name: str
    order_index: int = 0
    owner_id: Optional[str] = None
    status: Literal["draft", "active", "deprecated"] = "draft"
    source_refs: list[str] = []


class SOP(BaseModel):
    """A Standard Operating Procedure attached to a process."""

    model_config = ConfigDict(extra="forbid", strict=True)

    id: str
    name: str
    process_id: Optional[str] = None
    owner_id: Optional[str] = None
    status: Literal["draft", "active", "archived"] = "draft"
    current_version_id: Optional[str] = None
    source_refs: list[str] = []


class SOPVersion(BaseModel):
    """A versioned snapshot of an SOP."""

    model_config = ConfigDict(extra="forbid", strict=True)

    id: str
    sop_id: str
    version: str
    content_hash: str
    status: Literal["draft", "current", "superseded"] = "draft"
    source_refs: list[str] = []


class Employee(BaseModel):
    """An AI employee role definition (config, not runtime state)."""

    model_config = ConfigDict(extra="forbid", strict=True)

    id: str
    role: str
    status: Literal["active", "inactive", "paused"] = "active"
    source_refs: list[str] = []


class EmployeeRun(BaseModel):
    """Runtime state of an AI employee (state, not config)."""

    model_config = ConfigDict(extra="forbid", strict=True)

    id: str
    employee_id: str
    status: Literal["idle", "active", "paused", "offline"] = "idle"
    current_mission_id: Optional[str] = None
    source_refs: list[str] = []


class Mission(BaseModel):
    """A persistent business objective assigned to an AI employee."""

    model_config = ConfigDict(extra="forbid", strict=True)

    id: str
    title: str
    status: Literal["pending", "active", "stalled", "completed", "failed", "archived"] = "pending"
    priority: Literal["low", "medium", "high", "urgent"] = "medium"
    owner_id: Optional[str] = None
    employee_role: Optional[str] = None
    source_refs: list[str] = []


class MissionEvent(BaseModel):
    """An immutable, append-only event on a mission timeline."""

    model_config = ConfigDict(extra="forbid", strict=True)

    id: str
    mission_id: str
    event_type: str
    version: int = 1
    source_refs: list[str] = []


class MissionSnapshot(BaseModel):
    """A point-in-time capture of a mission's composed state."""

    model_config = ConfigDict(extra="forbid", strict=True)

    id: str
    mission_id: str
    version: int = 1
    snapshot_type: Literal["periodic", "on_change", "manual"] = "periodic"
    source_refs: list[str] = []


class Action(BaseModel):
    """A governed, idempotent unit of work executed by an AI employee."""

    model_config = ConfigDict(extra="forbid", strict=True)

    id: str
    mission_id: str
    employee_role: str
    capability: str
    risk_tier: Literal["LOW", "MEDIUM", "HIGH", "CRITICAL"] = "LOW"
    status: Literal["draft", "pending_approval", "approved", "rejected", "executing", "completed", "failed"] = "draft"
    idempotency_key: str
    source_refs: list[str] = []


class ActionResult(BaseModel):
    """The result of executing an Action, with verification metadata."""

    model_config = ConfigDict(extra="forbid", strict=True)

    id: str
    action_id: str
    result_summary: str = ""
    verified: bool = False
    source_refs: list[str] = []


class Outcome(BaseModel):
    """The result of a mission, tied to evidence."""

    model_config = ConfigDict(extra="forbid", strict=True)

    id: str
    mission_id: str
    result: Literal["success", "partial", "failure", "na"] = "na"
    evidence_refs: list[str] = []
    source_refs: list[str] = []


class Review(BaseModel):
    """A scheduled review of a process, SOP, or other target."""

    model_config = ConfigDict(extra="forbid", strict=True)

    id: str
    target_type: str
    target_id: str
    reviewer: str
    cadence: Optional[str] = None
    source_refs: list[str] = []


class KPI(BaseModel):
    """A measurable key performance indicator for a business process."""

    model_config = ConfigDict(extra="forbid", strict=True)

    id: str
    name: str
    target_value: float
    unit: str
    owner_id: Optional[str] = None
    status: Literal["active", "archived", "draft"] = "active"
    source_refs: list[str] = []


# Registry of all canonical Object Types by name, used by governance/adapter
# layers and tests. Exactly the six PRD §12 types.
OBJECT_TYPES = {
    "Party": Party,
    "Engagement": Engagement,
    "MoneyEvent": MoneyEvent,
    "Issue": Issue,
    "Message": Message,
    "PlannedAction": PlannedAction,
    "Shipment": Shipment,
    "Stakeholder": Stakeholder,
    "Pillar": Pillar,
    "Process": Process,
    "ProcessStep": ProcessStep,
    "SOP": SOP,
    "SOPVersion": SOPVersion,
    "Employee": Employee,
    "EmployeeRun": EmployeeRun,
    "Mission": Mission,
    "MissionEvent": MissionEvent,
    "MissionSnapshot": MissionSnapshot,
    "Action": Action,
    "ActionResult": ActionResult,
    "Outcome": Outcome,
    "Review": Review,
    "KPI": KPI,
}

"""OntologyAI V6 — Knowledge Catalog Schema Models.

Pydantic v2 models for the 10-category Knowledge Catalog that indexes
ALL enterprise knowledge artifacts. These models define the schema for
catalog entries, relationships, and query patterns.

Usage:
    from src.schemas.knowledge_catalog import (
        CatalogCapability, CatalogDecision, CatalogRisk,
        CatalogRelationship, CatalogSearchQuery,
    )
"""
from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Any, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator


# ── Lifecycle Enums ──────────────────────────────────────────────────────

class CapabilityMaturity(str, Enum):
    """Capability maturity levels (CMM-inspired)."""
    INITIAL = "initial"
    DEVELOPING = "developing"
    DEFINED = "defined"
    MANAGED = "managed"
    OPTIMIZING = "optimizing"


class CatalogStatus(str, Enum):
    """Universal catalog lifecycle states."""
    DRAFT = "draft"
    ACTIVE = "active"
    ARCHIVED = "archived"
    DEPRECATED = "deprecated"


class DecisionStatus(str, Enum):
    """Decision lifecycle states."""
    PROPOSED = "proposed"
    IN_REVIEW = "in_review"
    APPROVED = "approved"
    REJECTED = "rejected"
    IMPLEMENTED = "implemented"
    SUPERSEDED = "superseded"
    ARCHIVED = "archived"


class RiskStatus(str, Enum):
    """Risk lifecycle states."""
    IDENTIFIED = "identified"
    ASSESSED = "assessed"
    MITIGATING = "mitigating"
    MITIGATED = "mitigated"
    ACCEPTED = "accepted"
    CLOSED = "closed"
    REALIZED = "realized"


class ArtifactStatus(str, Enum):
    """Artifact lifecycle states."""
    DRAFT = "draft"
    REVIEW = "review"
    PUBLISHED = "published"
    SUPERSEDED = "superseded"
    ARCHIVED = "archived"


class EvidenceStatus(str, Enum):
    """Evidence lifecycle states."""
    COLLECTED = "collected"
    VALIDATED = "validated"
    STALE = "stale"
    DISPUTED = "disputed"
    ARCHIVED = "archived"


class SystemStatus(str, Enum):
    """System lifecycle states."""
    PLANNED = "planned"
    ACTIVE = "active"
    SUNSET = "sunset"
    DECOMMISSIONED = "decommissioned"
    MIGRATING = "migrating"


class ProjectStatus(str, Enum):
    """Project lifecycle states."""
    INITIATED = "initiated"
    PLANNING = "planning"
    EXECUTING = "executing"
    MONITORING = "monitoring"
    COMPLETED = "completed"
    CANCELLED = "cancelled"
    ON_HOLD = "on_hold"


# ── Relationship Enums ───────────────────────────────────────────────────

class CapabilitySystemRelationship(str, Enum):
    """Relationship types between capabilities and systems."""
    DEPENDS_ON = "depends_on"
    SUPPORTS = "supports"
    REPLACED_BY = "replaced_by"
    INTEGRATES_WITH = "integrates_with"


class StakeholderCapabilityRole(str, Enum):
    """Roles stakeholders play in capabilities."""
    OWNER = "owner"
    LEAD = "lead"
    PARTICIPANT = "participant"
    REVIEWER = "reviewer"
    ADVISER = "adviser"


class DecisionCapabilityImpact(str, Enum):
    """How decisions affect capabilities."""
    AFFECTS = "affects"
    CREATES = "creates"
    MODIFIES = "modifies"
    DEPRECATES = "deprecates"


class EvidenceRoleInDecision(str, Enum):
    """Role evidence plays in decisions."""
    SUPPORTING = "supporting"
    CONTRADICTING = "contradicting"
    CONTEXTUAL = "contextual"
    PREREQUISITE = "prerequisite"


class EvidenceRoleInRisk(str, Enum):
    """Role evidence plays in risks."""
    SUPPORTING = "supporting"
    MITIGATING = "mitigating"
    CONTRADICTING = "contradicting"
    CONTEXTUAL = "contextual"


class StakeholderDecisionRole(str, Enum):
    """Roles stakeholders play in decisions."""
    DECISION_MAKER = "decision_maker"
    REVIEWER = "reviewer"
    PARTICIPANT = "participant"
    INFORMED = "informed"


# ── Base Catalog Item ────────────────────────────────────────────────────

def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class CatalogItem(BaseModel):
    """Base model for all catalog items."""
    
    model_config = ConfigDict(extra="forbid", strict=True)
    
    id: str
    tenant_id: str
    name: str
    description: Optional[str] = None
    status: str = "draft"
    owner_id: Optional[str] = None
    confidence: float = 0.0
    evidence_ids: list[str] = Field(default_factory=list)
    tags: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)
    created_at: str = Field(default_factory=_now_iso)
    updated_at: str = Field(default_factory=_now_iso)
    created_by: Optional[str] = None
    updated_by: Optional[str] = None
    version: int = 1


# ── Category Models ──────────────────────────────────────────────────────

class CatalogCapability(CatalogItem):
    """Business capability and its maturity."""
    
    maturity_level: CapabilityMaturity = CapabilityMaturity.INITIAL
    parent_id: Optional[str] = None
    domain: Optional[str] = None


class CatalogDecision(CatalogItem):
    """Past or pending decision with evidence chain."""
    
    decision_type: str = "tactical"  # strategic, tactical, operational, technical
    status: DecisionStatus = DecisionStatus.PROPOSED
    decision_date: Optional[str] = None
    workspace_id: Optional[str] = None
    rationale: Optional[str] = None
    alternatives: list[dict[str, Any]] = Field(default_factory=list)
    outcome: Optional[str] = None
    impact_score: Optional[float] = None


class CatalogProcess(CatalogItem):
    """Business process and its documentation."""
    
    process_type: str = "core"  # core, support, management
    frequency: Optional[str] = None
    inputs: list[dict[str, Any]] = Field(default_factory=list)
    outputs: list[dict[str, Any]] = Field(default_factory=list)
    steps: list[dict[str, Any]] = Field(default_factory=list)
    documentation_url: Optional[str] = None


class CatalogPolicy(CatalogItem):
    """Rule, regulation, or compliance requirement."""
    
    policy_type: str = "guideline"  # regulation, standard, guideline, constraint
    severity: str = "info"  # block, warn, info
    effective_date: Optional[str] = None
    expiry_date: Optional[str] = None
    rule_expression: str = ""
    applies_to: list[str] = Field(default_factory=list)
    enforcement: str = "mandatory"  # mandatory, advisory, optional
    source_ref: Optional[str] = None


class CatalogRisk(CatalogItem):
    """Identified risk with mitigation status."""
    
    risk_category: str = "operational"  # strategic, operational, financial, technical, compliance
    likelihood: str = "medium"  # low, medium, high, very_high
    impact: str = "medium"  # low, medium, high, critical
    risk_score: float = 0.0
    status: RiskStatus = RiskStatus.IDENTIFIED
    mitigation_plan: Optional[str] = None
    mitigation_status: Optional[str] = None
    target_close_date: Optional[str] = None
    actual_close_date: Optional[str] = None
    related_capability_ids: list[str] = Field(default_factory=list)
    related_project_ids: list[str] = Field(default_factory=list)


class CatalogArtifact(CatalogItem):
    """Generated document, report, or analysis."""
    
    artifact_category: str = "other"  # report, brief, analysis, spec, diagram, contract, policy_doc, other
    artifact_type: Optional[str] = None
    status: ArtifactStatus = ArtifactStatus.DRAFT
    workspace_id: Optional[str] = None
    project_id: Optional[str] = None
    content_ref: Optional[str] = None
    content_hash: Optional[str] = None
    format: Optional[str] = None
    producer: Optional[str] = None


class CatalogStakeholder(CatalogItem):
    """Person, role, or expertise area."""
    
    email: Optional[str] = None
    role: Optional[str] = None
    department: Optional[str] = None
    expertise_areas: list[str] = Field(default_factory=list)
    responsibility_areas: list[str] = Field(default_factory=list)
    org_unit_id: Optional[str] = None


class CatalogEvidence(CatalogItem):
    """Raw evidence record with provenance."""
    
    evidence_type: str = "manual_input"  # connector_output, manual_input, system_event, document, interview, derived
    source_id: Optional[str] = None
    content: Optional[str] = None
    content_hash: Optional[str] = None
    reliability: float = 0.5
    timestamp: str = Field(default_factory=_now_iso)
    expires_at: Optional[str] = None


class CatalogSystem(CatalogItem):
    """Technical system or integration."""
    
    system_type: str = "internal"  # saas, internal, legacy, infrastructure, data_store
    status: SystemStatus = SystemStatus.ACTIVE
    vendor: Optional[str] = None
    system_version: Optional[str] = None
    url: Optional[str] = None
    capabilities: list[str] = Field(default_factory=list)
    integrations: list[str] = Field(default_factory=list)
    data_class: str = "internal"  # public, internal, confidential, restricted


class CatalogProject(CatalogItem):
    """Active or completed project."""
    
    project_type: str = "tactical"  # strategic, tactical, operational, maintenance
    status: ProjectStatus = ProjectStatus.INITIATED
    start_date: Optional[str] = None
    target_end_date: Optional[str] = None
    actual_end_date: Optional[str] = None
    goals: list[str] = Field(default_factory=list)
    outcomes: list[str] = Field(default_factory=list)
    budget: Optional[float] = None
    actual_cost: Optional[float] = None
    progress_pct: float = 0.0
    related_capability_ids: list[str] = Field(default_factory=list)
    related_risk_ids: list[str] = Field(default_factory=list)


# ── Relationship Models ──────────────────────────────────────────────────

class CatalogRelationship(BaseModel):
    """A relationship between two catalog items."""
    
    model_config = ConfigDict(extra="forbid", strict=True)
    
    id: str
    tenant_id: str
    source_category: str
    source_id: str
    target_category: str
    target_id: str
    relationship_type: str
    strength: Optional[str] = None
    weight: Optional[float] = None
    metadata: dict[str, Any] = Field(default_factory=dict)
    created_at: str = Field(default_factory=_now_iso)


class CapabilitySystemLink(BaseModel):
    """Link between a capability and a system."""
    capability_id: str
    system_id: str
    relationship: CapabilitySystemRelationship = CapabilitySystemRelationship.DEPENDS_ON
    strength: str = "required"  # required, preferred, optional


class StakeholderCapabilityLink(BaseModel):
    """Link between a stakeholder and a capability."""
    stakeholder_id: str
    capability_id: str
    role_in_capability: StakeholderCapabilityRole = StakeholderCapabilityRole.PARTICIPANT


class DecisionCapabilityLink(BaseModel):
    """Link between a decision and a capability."""
    decision_id: str
    capability_id: str
    impact_type: DecisionCapabilityImpact = DecisionCapabilityImpact.AFFECTS


class DecisionEvidenceLink(BaseModel):
    """Link between a decision and evidence."""
    decision_id: str
    evidence_id: str
    role_in_decision: EvidenceRoleInDecision = EvidenceRoleInDecision.SUPPORTING
    weight: float = 1.0


class RiskEvidenceLink(BaseModel):
    """Link between a risk and evidence."""
    risk_id: str
    evidence_id: str
    role_in_risk: EvidenceRoleInRisk = EvidenceRoleInRisk.SUPPORTING


class ProcessCapabilityLink(BaseModel):
    """Link between a process and a capability."""
    process_id: str
    capability_id: str
    relationship: str = "implements"  # implements, supports, depends_on


class PolicyCapabilityLink(BaseModel):
    """Link between a policy and a capability."""
    policy_id: str
    capability_id: str
    enforcement: str = "mandatory"  # mandatory, advisory, optional


class ArtifactCapabilityLink(BaseModel):
    """Link between an artifact and a capability."""
    artifact_id: str
    capability_id: str
    relationship: str = "documents"  # documents, specifies, analyzes, depicts


class ArtifactDecisionLink(BaseModel):
    """Link between an artifact and a decision."""
    artifact_id: str
    decision_id: str
    relationship: str = "supports"  # supports, informs, supersedes


class ProjectCapabilityLink(BaseModel):
    """Link between a project and a capability."""
    project_id: str
    capability_id: str
    impact_type: str = "improves"  # improves, creates, modifies, deprecates, replaces


class StakeholderDecisionLink(BaseModel):
    """Link between a stakeholder and a decision."""
    stakeholder_id: str
    decision_id: str
    role_in_decision: StakeholderDecisionRole = StakeholderDecisionRole.PARTICIPANT


# ── Search and Query Models ──────────────────────────────────────────────

class CatalogSearchQuery(BaseModel):
    """Search query across all catalog categories."""
    
    model_config = ConfigDict(extra="forbid", strict=True)
    
    query: str
    categories: list[str] = Field(default_factory=list)  # empty = all categories
    filters: dict[str, Any] = Field(default_factory=dict)
    page: int = 1
    page_size: int = 20
    sort_by: str = "relevance"  # relevance, name, created_at, confidence
    sort_order: str = "desc"  # asc, desc


class CatalogFilter(BaseModel):
    """Filter criteria for catalog queries."""
    
    domain: Optional[str] = None
    status: Optional[str] = None
    owner_id: Optional[str] = None
    confidence_min: Optional[float] = None
    confidence_max: Optional[float] = None
    created_after: Optional[str] = None
    created_before: Optional[str] = None
    tags: list[str] = Field(default_factory=list)


class CatalogSearchResult(BaseModel):
    """Single search result item."""
    
    id: str
    category: str
    name: str
    description: Optional[str] = None
    status: str
    confidence: float
    relevance_score: float  # 0-1, how relevant to the search query
    highlights: list[str] = Field(default_factory=list)  # matching text snippets
    metadata: dict[str, Any] = Field(default_factory=dict)


class CatalogSearchResults(BaseModel):
    """Paginated search results."""
    
    results: list[CatalogSearchResult] = Field(default_factory=list)
    total_count: int = 0
    page: int = 1
    page_size: int = 20
    query: str = ""
    filters_applied: dict[str, Any] = Field(default_factory=dict)


# ── Relationship Graph Models ────────────────────────────────────────────

class RelationshipGraphNode(BaseModel):
    """A node in the relationship graph."""
    
    id: str
    category: str
    name: str
    status: str
    confidence: float


class RelationshipGraphEdge(BaseModel):
    """An edge in the relationship graph."""
    
    source_id: str
    target_id: str
    relationship_type: str
    weight: float = 1.0


class RelationshipGraph(BaseModel):
    """Complete relationship graph for an item."""
    
    root: RelationshipGraphNode
    nodes: list[RelationshipGraphNode] = Field(default_factory=list)
    edges: list[RelationshipGraphEdge] = Field(default_factory=list)
    depth: int = 1


# ── Evidence Chain Models ────────────────────────────────────────────────

class EvidenceChainNode(BaseModel):
    """A node in the evidence chain."""
    
    evidence_id: str
    evidence_type: str
    confidence: float
    reliability: float
    summary: str
    timestamp: str


class EvidenceChainEdge(BaseModel):
    """An edge in the evidence chain."""
    
    source_evidence_id: str
    target_evidence_id: str
    relationship: str  # supports, contradicts, builds_on


class EvidenceChain(BaseModel):
    """Complete evidence chain for a catalog item."""
    
    item_id: str
    item_category: str
    chain: list[EvidenceChainNode] = Field(default_factory=list)
    connections: list[EvidenceChainEdge] = Field(default_factory=list)
    total_confidence: float = 0.0  # weighted average of chain confidence


# ── Catalog Statistics ───────────────────────────────────────────────────

class CategoryStats(BaseModel):
    """Statistics for a single category."""
    
    category: str
    total_count: int = 0
    active_count: int = 0
    draft_count: int = 0
    archived_count: int = 0
    avg_confidence: float = 0.0
    last_updated: Optional[str] = None


class CatalogStats(BaseModel):
    """Overall catalog statistics."""
    
    categories: list[CategoryStats] = Field(default_factory=list)
    total_relationships: int = 0
    total_evidence: int = 0
    avg_confidence: float = 0.0
    last_synced_at: Optional[str] = None


# ── Registries ──────────────────────────────────────────────────────────

CATALOG_CATEGORIES = {
    "capabilities": CatalogCapability,
    "decisions": CatalogDecision,
    "processes": CatalogProcess,
    "policies": CatalogPolicy,
    "risks": CatalogRisk,
    "artifacts": CatalogArtifact,
    "stakeholders": CatalogStakeholder,
    "evidence": CatalogEvidence,
    "systems": CatalogSystem,
    "projects": CatalogProject,
}

CATALOG_RELATIONSHIP_TYPES = {
    "capability_system": CapabilitySystemLink,
    "stakeholder_capability": StakeholderCapabilityLink,
    "decision_capability": DecisionCapabilityLink,
    "decision_evidence": DecisionEvidenceLink,
    "risk_evidence": RiskEvidenceLink,
    "process_capability": ProcessCapabilityLink,
    "policy_capability": PolicyCapabilityLink,
    "artifact_capability": ArtifactCapabilityLink,
    "artifact_decision": ArtifactDecisionLink,
    "project_capability": ProjectCapabilityLink,
    "stakeholder_decision": StakeholderDecisionLink,
}


# ── V6 Knowledge Catalog Entry ──────────────────────────────────────────


class KnowledgeCatalogEntry(BaseModel):
    """A single entry in the 10-category Knowledge Catalog.

    Each entry indexes one enterprise knowledge artifact (capability,
    decision, process, policy, risk, artifact, stakeholder, evidence,
    system, or project) with metadata for search, versioning, and
    lifecycle management.

    Attributes:
        id: Globally unique identifier (ULID recommended).
        category: One of the 10 catalog categories.
        title: Human-readable entry title.
        description: Longer explanation of this catalog entry.
        entity_id: ID of the entity this entry indexes.
        entity_type: Type of the referenced entity.
        tags: Free-form labels for search and filtering.
        confidence: Entry confidence (0.0 – 1.0).
        evidence_ids: IDs of supporting evidence records.
        lifecycle_state: One of ``"draft"``, ``"active"``,
            ``"archived"``, or ``"deprecated"``.
        version: Monotonically increasing version number.
        created_by: ID of the user or agent that created this entry.
        updated_by: ID of the user or agent that last updated this entry.
        tenant_id: Multi-tenant isolation identifier.
        created_at: Creation timestamp (UTC).
        updated_at: Last-modified timestamp (UTC).
    """

    model_config = ConfigDict(extra="forbid", strict=True)

    id: str
    category: str
    title: str
    description: str = ""
    entity_id: str
    entity_type: str
    tags: list[str] = Field(default_factory=list)
    confidence: float = Field(ge=0.0, le=1.0, default=0.9)
    evidence_ids: list[str] = Field(default_factory=list)
    lifecycle_state: str = "active"
    version: int = 1
    created_by: str = ""
    updated_by: str = ""
    tenant_id: str = ""
    created_at: datetime
    updated_at: datetime

    @field_validator("category")
    @classmethod
    def validate_category(cls, v: str) -> str:
        """Reject categories outside the 10 allowed values."""
        allowed = {
            "capability",
            "decision",
            "process",
            "policy",
            "risk",
            "artifact",
            "stakeholder",
            "evidence",
            "system",
            "project",
        }
        if v not in allowed:
            msg = f"category must be one of {sorted(allowed)}, got {v!r}"
            raise ValueError(msg)
        return v

    @field_validator("lifecycle_state")
    @classmethod
    def validate_lifecycle_state(cls, v: str) -> str:
        """Reject lifecycle states outside the allowed set."""
        allowed = {"draft", "active", "archived", "deprecated"}
        if v not in allowed:
            msg = f"lifecycle_state must be one of {sorted(allowed)}, got {v!r}"
            raise ValueError(msg)
        return v

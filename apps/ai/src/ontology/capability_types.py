"""OntologyAI V6 — Capability Ontology models (ADR-013).

Defines the core capability entity, relationships, evidence links,
and scoring models for capability-centric business reasoning.

Design Principles:
  1. Capabilities are stable planning abstractions (independent of org/apps)
  2. Evidence maps to capabilities (not directly to decisions)
  3. Feasibility analysis operates on capability health
  4. Decisions are framed as capability investments
  5. Artifacts are generated at the capability level
"""
from __future__ import annotations

from enum import Enum
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field


# ── Enums ─────────────────────────────────────────────────────────


class CapabilityLevel(str, Enum):
    """Hierarchy level for capabilities (L0=domain, L1=capability, L2=sub-capability)."""

    L0 = "L0"
    L1 = "L1"
    L2 = "L2"


class CapabilityStatus(str, Enum):
    """Lifecycle status for capabilities."""

    ASSESSED = "assessed"
    DEVELOPING = "developing"
    MATURE = "mature"
    DEPRECATED = "deprecated"
    EMERGING = "emerging"


class MaturityLevel(int, Enum):
    """CMMI-inspired maturity levels (simplified 5-level model).

    Level 1: Initial      — Ad hoc, chaotic, hero-driven
    Level 2: Managed      — Repeatable at project level
    Level 3: Defined      — Standardized across organization
    Level 4: Quantified   — Measured and data-driven
    Level 5: Optimizing   — Continuous improvement
    """

    INITIAL = 1
    MANAGED = 2
    DEFINED = 3
    QUANTIFIED = 4
    OPTIMIZING = 5


class CapabilityEdgeType(str, Enum):
    """Semantic edge types between capabilities."""

    ENABLES = "ENABLES"  # A is prerequisite for B
    DEPENDS_ON = "DEPENDS_ON"  # A needs B to deliver value
    CONFLICTS_WITH = "CONFLICTS_WITH"  # A and B compete for resources
    INVESTED_IN = "INVESTED_IN"  # A project targets this capability
    EVOLVES_TO = "EVOLVES_TO"  # A is transforming into B
    REPLACES = "REPLACES"  # A is replacing B


class HealthTier(str, Enum):
    """Health assessment tiers."""

    HEALTHY = "healthy"  # 0.75-1.0
    ATTENTION = "attention"  # 0.50-0.74
    AT_RISK = "at_risk"  # 0.25-0.49
    CRITICAL = "critical"  # 0.00-0.24


# ── Core Models ───────────────────────────────────────────────────


class Capability(BaseModel):
    """A business capability — stable planning abstraction.

    Capabilities are independent of org charts, applications, or team
    structure. They represent *what the business does*, not *who does it*
    or *which tool does it*.

    Identity: name (normalized, case-insensitive) within tenant.
    Persistence: Neo4j node.
    """

    model_config = ConfigDict(extra="forbid", strict=True)

    id: str  # ULID
    tenant_id: str  # ULID
    name: str  # e.g. "Lead Qualification"
    description: str = ""
    level: CapabilityLevel = CapabilityLevel.L1
    parent_id: Optional[str] = None  # ULID of parent capability
    domain: str = ""  # Business domain (e.g. "Sales", "Engineering")
    aliases: list[str] = Field(default_factory=list)
    maturity_level: MaturityLevel = MaturityLevel.INITIAL
    maturity_score: float = 0.0  # Computed [0.0, 1.0]
    health_score: float = 0.0  # Computed [0.0, 1.0]
    investment_level: str = "none"  # none, low, medium, high
    owner_id: Optional[str] = None  # Stakeholder ULID
    status: CapabilityStatus = CapabilityStatus.ASSESSED
    source_refs: list[str] = Field(default_factory=list)
    created_at: str = ""
    updated_at: str = ""


class CapabilityRelationship(BaseModel):
    """A typed edge between two capabilities.

    Persistence: Neo4j edge.
    """

    model_config = ConfigDict(extra="forbid", strict=True)

    id: str  # ULID
    source_id: str  # ULID of source capability
    target_id: str  # ULID of target capability
    relationship_type: CapabilityEdgeType
    strength: float = 1.0  # [0.0, 1.0] — dependency strength
    description: str = ""
    source_refs: list[str] = Field(default_factory=list)
    created_at: str = ""


class CapabilityEvidence(BaseModel):
    """Links an evidence record to a capability with relevance scoring.

    Persistence: Neo4j edge (EVIDENCE_LINKS_TO_CAPABILITY).
    """

    model_config = ConfigDict(extra="forbid", strict=True)

    evidence_id: str  # ULID of EvidenceRecord
    capability_id: str  # ULID of Capability
    relevance_score: float = 0.0  # [0.0, 1.0]
    mapping_method: str = "auto"  # auto, llm, manual, keyword
    mapped_by: str = "system"  # agent or stakeholder who mapped
    created_at: str = ""


class CapabilityScore(BaseModel):
    """Computed health/maturity/investment score for a capability.

    Persistence: Postgres (append-only, new computation supersedes old).
    """

    model_config = ConfigDict(extra="forbid", strict=True)

    id: str  # ULID
    capability_id: str  # ULID
    computed_at: str = ""  # ISO timestamp

    # Health dimensions (5 × 0.20 = 1.0 total)
    health_score: float = 0.0  # [0.0, 1.0] overall health
    evidence_volume: int = 0  # count of linked evidence
    evidence_freshness: float = 0.0  # [0.0, 1.0] — recency
    evidence_sentiment: float = 0.0  # [-1.0, 1.0] — avg sentiment
    evidence_confidence: float = 0.0  # [0.0, 1.0] — avg confidence
    risk_exposure: float = 0.0  # [0.0, 1.0] — inverted (1.0 = no risk)

    # Maturity dimensions (4 × 0.25 = 1.0 total)
    maturity_level: MaturityLevel = MaturityLevel.INITIAL
    maturity_score: float = 0.0  # [0.0, 1.0]
    process_standardization: float = 0.0  # [0.0, 1.0]
    measurement_coverage: float = 0.0  # [0.0, 1.0]
    improvement_activity: float = 0.0  # [0.0, 1.0]
    documentation_coverage: float = 0.0  # [0.0, 1.0]

    # Investment dimensions
    investment_level: str = "none"
    linked_projects: int = 0
    linked_requirements: int = 0
    linked_decisions: int = 0

    # Risk dimensions
    open_risks: int = 0
    open_conflicts: int = 0
    unresolved_issues: int = 0

    # Metadata
    weights_snapshot: dict = Field(default_factory=dict)
    computation_version: str = "1.0"


# ── Capability Map (Hierarchy) ────────────────────────────────────


class CapabilityMap(BaseModel):
    """A complete capability hierarchy for a tenant/domain.

    Used for strategic planning views and capability-centric artifacts.
    """

    model_config = ConfigDict(extra="forbid", strict=True)

    tenant_id: str
    domain: str  # e.g. "Sales", "Engineering"
    capabilities: list[Capability] = Field(default_factory=list)
    relationships: list[CapabilityRelationship] = Field(default_factory=list)

    def get_l0_capabilities(self) -> list[Capability]:
        """Return top-level domain capabilities."""
        return [c for c in self.capabilities if c.level == CapabilityLevel.L0]

    def get_l1_capabilities(self, domain: str = "") -> list[Capability]:
        """Return L1 capabilities, optionally filtered by domain."""
        l1 = [c for c in self.capabilities if c.level == CapabilityLevel.L1]
        if domain:
            l1 = [c for c in l1 if c.domain == domain]
        return l1

    def get_l2_capabilities(self, parent_id: str) -> list[Capability]:
        """Return L2 sub-capabilities under a given L1 capability."""
        return [c for c in self.capabilities if c.level == CapabilityLevel.L2 and c.parent_id == parent_id]

    def get_capabilities_below_health(self, threshold: float = 0.5) -> list[Capability]:
        """Return capabilities with health_score below threshold."""
        return [c for c in self.capabilities if c.health_score < threshold]

    def get_capabilities_below_maturity(self, max_level: MaturityLevel = MaturityLevel.MANAGED) -> list[Capability]:
        """Return capabilities at or below a given maturity level."""
        return [c for c in self.capabilities if c.maturity_level.value <= max_level.value]


# ── Scoring Helpers ───────────────────────────────────────────────


def compute_health_tier(score: float) -> HealthTier:
    """Map health score [0.0, 1.0] to a health tier."""
    if score >= 0.75:
        return HealthTier.HEALTHY
    elif score >= 0.50:
        return HealthTier.ATTENTION
    elif score >= 0.25:
        return HealthTier.AT_RISK
    else:
        return HealthTier.CRITICAL


def compute_health_score(
    evidence_volume: float,
    evidence_freshness: float,
    evidence_sentiment: float,  # [-1.0, 1.0]
    evidence_confidence: float,
    risk_exposure: float,  # inverted: 1.0 = no risk
) -> float:
    """Compute capability health score [0.0, 1.0] from 5 dimensions.

    Each dimension has equal weight (0.20).
    Evidence sentiment is normalized from [-1, 1] to [0, 1].
    """
    normalized_sentiment = (evidence_sentiment + 1.0) / 2.0
    return (
        0.20 * min(evidence_volume, 1.0)
        + 0.20 * min(evidence_freshness, 1.0)
        + 0.20 * max(0.0, min(normalized_sentiment, 1.0))
        + 0.20 * min(evidence_confidence, 1.0)
        + 0.20 * min(risk_exposure, 1.0)
    )


def compute_maturity_score(
    process_standardization: float,
    measurement_coverage: float,
    improvement_activity: float,
    documentation_coverage: float,
) -> tuple[float, MaturityLevel]:
    """Compute maturity score [0.0, 1.0] and map to MaturityLevel.

    Returns (score, level) tuple.
    """
    score = (
        0.25 * process_standardization
        + 0.25 * measurement_coverage
        + 0.25 * improvement_activity
        + 0.25 * documentation_coverage
    )

    if score < 0.2:
        level = MaturityLevel.INITIAL
    elif score < 0.4:
        level = MaturityLevel.MANAGED
    elif score < 0.6:
        level = MaturityLevel.DEFINED
    elif score < 0.8:
        level = MaturityLevel.QUANTIFIED
    else:
        level = MaturityLevel.OPTIMIZING

    return score, level


# ── Registry ──────────────────────────────────────────────────────

CAPABILITY_MODELS = {
    "Capability": Capability,
    "CapabilityRelationship": CapabilityRelationship,
    "CapabilityEvidence": CapabilityEvidence,
    "CapabilityScore": CapabilityScore,
    "CapabilityMap": CapabilityMap,
}

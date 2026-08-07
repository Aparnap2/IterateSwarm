"""OntologyAI V6 — Capability schema models.

Enterprise capability modelling with maturity tracking, hierarchical
parent/child relationships, and typed inter-capability links.

Usage:
    from src.schemas.capability import Capability, CapabilityRelationship

    auth = Capability(
        id="01J0X8X8X8X8X8X8X8X8X8X8X8XX",
        name="Auth",
        description="Authentication capability",
    )
    rel = CapabilityRelationship(
        source_id="01J0X8X8X8X8X8X8X8X8X8X8X8XX",
        target_id="01J0Y9Y9Y9Y9Y9Y9Y9Y9Y9Y9Y9YY",
        relationship_type="ENABLES",
    )
"""
from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator


class Capability(BaseModel):
    """A named business or technical capability with maturity tracking.

    Capabilities form a hierarchy via ``parent_id`` and are scored by
    maturity level and health. Each capability belongs to a domain and
    can be owned by a stakeholder.

    Attributes:
        id: Globally unique identifier (ULID recommended).
        name: Short, human-readable capability name.
        description: Longer explanation of what this capability provides.
        level: Granularity level — ``"L0"`` (landscape), ``"L1"``
            (domain), or ``"L2"`` (detailed).
        parent_id: Optional ID of the parent capability.
        maturity_level: CMM-style maturity score (1 – 5).
        health_score: Operational health (0.0 – 1.0).
        owner_id: ID of the responsible stakeholder.
        status: Lifecycle status — ``"active"``, ``"deprecated"``,
            or ``"planned"``.
        domain: Business or technical domain this capability belongs to.
        tenant_id: Multi-tenant isolation identifier.
        created_at: Creation timestamp (UTC).
        updated_at: Last-modified timestamp (UTC).
    """

    model_config = ConfigDict(extra="forbid", strict=True)

    id: str
    name: str
    description: str = ""
    level: str = "L0"
    parent_id: str | None = None
    maturity_level: int = Field(ge=1, le=5, default=1)
    health_score: float = Field(ge=0.0, le=1.0, default=0.0)
    owner_id: str = ""
    status: str = "active"
    domain: str = ""
    tenant_id: str = ""
    created_at: datetime
    updated_at: datetime

    @field_validator("level")
    @classmethod
    def validate_level(cls, v: str) -> str:
        """Reject capability levels other than L0, L1, or L2."""
        allowed = {"L0", "L1", "L2"}
        if v not in allowed:
            msg = f"level must be one of {sorted(allowed)}, got {v!r}"
            raise ValueError(msg)
        return v

    @field_validator("status")
    @classmethod
    def validate_status(cls, v: str) -> str:
        """Reject lifecycle statuses other than active, deprecated, or planned."""
        allowed = {"active", "deprecated", "planned"}
        if v not in allowed:
            msg = f"status must be one of {sorted(allowed)}, got {v!r}"
            raise ValueError(msg)
        return v


class CapabilityRelationship(BaseModel):
    """A typed, directed link between two capabilities.

    Relationships capture how capabilities depend on, enable, conflict
    with, or are invested in by other capabilities.

    Attributes:
        source_id: ID of the originating capability.
        target_id: ID of the target capability.
        relationship_type: One of ``"ENABLES"``, ``"DEPENDS_ON"``,
            ``"CONFLICTS_WITH"``, or ``"INVESTED_IN"``.
        confidence: Relationship confidence (0.0 – 1.0).
        evidence_ids: IDs of ``KnowledgeCatalogEntry`` records that
            support this relationship.
    """

    model_config = ConfigDict(extra="forbid", strict=True)

    source_id: str
    target_id: str
    relationship_type: str
    confidence: float = Field(ge=0.0, le=1.0, default=0.9)
    evidence_ids: list[str] = Field(default_factory=list)

    @field_validator("relationship_type")
    @classmethod
    def validate_relationship_type(cls, v: str) -> str:
        """Reject relationship types outside the allowed set."""
        allowed = {"ENABLES", "DEPENDS_ON", "CONFLICTS_WITH", "INVESTED_IN"}
        if v not in allowed:
            msg = f"relationship_type must be one of {sorted(allowed)}, got {v!r}"
            raise ValueError(msg)
        return v

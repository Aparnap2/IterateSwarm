"""OntologyAI V6 — Semantic Layer schema models.

Canonical entity resolution and cross-system aliasing. Every enterprise
entity (customer, vendor, product, …) is represented as a single
``CanonicalEntity`` that aggregates ``EntityAlias`` records from
upstream systems (Salesforce, ERP, support desk, Slack, etc.).

Usage:
    from src.schemas.semantic_layer import CanonicalEntity, EntityAlias

    alias = EntityAlias(
        source_system="salesforce",
        external_id="sf-001",
        display_name="Acme Corp",
        entity_type_hint="customer",
    )
    entity = CanonicalEntity(
        id="01J0X8X8X8X8X8X8X8X8X8X8X8XX",
        canonical_name="Acme Corp",
        entity_type="customer",
        aliases=[alias],
    )
"""
from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class ResolutionTier(str, Enum):
    """Five-tier canonical entity resolution strategy, ordered by priority."""

    EXACT = "exact"  # Match on external_id
    FUZZY = "fuzzy"  # Fuzzy match on name + type (Levenshtein)
    ATTRIBUTE = "attribute"  # Attribute match (email, phone, domain)
    RELATIONSHIP = "relationship"  # Relationship match (shared parent/contacts)
    LLM_ASSISTED = "llm_assisted"  # LLM-assisted resolution for low-confidence cases


class ConflictStatus(str, Enum):
    """Lifecycle state of an attribute conflict."""

    OPEN = "open"
    RESOLVED = "resolved"
    MANUAL_OVERRIDE = "manual_override"


class AttributeConflict(BaseModel):
    """A detected conflict between sources on a single attribute.

    Attributes:
        entity_id: The canonical entity ID this conflict belongs to.
        attribute_name: The conflicting attribute (e.g. ``"email"``).
        conflicting_values: List of source records showing the conflict.
            Each entry contains ``source_system``, ``value``, ``confidence``,
            and ``timestamp``.
        resolved_value: The resolved value after conflict resolution.
        resolution_method: How the conflict was resolved (e.g. ``"source_of_truth"``,
            ``"temporal_precedence"``, ``"confidence_weighting"``, ``"manual"``).
        status: Current conflict status.
        created_at: When the conflict was detected.
        resolved_at: When the conflict was resolved (if applicable).
    """

    model_config = ConfigDict(extra="forbid", strict=True)

    entity_id: str
    attribute_name: str
    conflicting_values: list[dict[str, Any]] = Field(default_factory=list)
    resolved_value: Any | None = None
    resolution_method: str = ""
    status: ConflictStatus = ConflictStatus.OPEN
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    resolved_at: datetime | None = None


class EntityLineage(BaseModel):
    """Full lineage of a canonical entity across all source systems.

    Attributes:
        entity_id: The canonical entity ID.
        canonical_name: The resolved, human-readable name.
        entity_type: Entity type label.
        aliases: All upstream aliases mapped to this entity.
        resolution_history: Ordered list of resolution events showing
            how this entity was matched or created over time.
        conflicts: All attribute conflicts detected for this entity.
        tenant_id: Multi-tenant isolation identifier.
        created_at: When the canonical entity was first created.
        updated_at: When the lineage was last updated.
    """

    model_config = ConfigDict(extra="forbid", strict=True)

    entity_id: str
    canonical_name: str
    entity_type: str
    aliases: list[EntityAlias] = Field(default_factory=list)
    resolution_history: list[dict[str, Any]] = Field(default_factory=list)
    conflicts: list[AttributeConflict] = Field(default_factory=list)
    tenant_id: str = ""
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class EntityAlias(BaseModel):
    """An alias for a canonical entity originating from an external system.

    Each alias records how a particular upstream system (e.g. Salesforce,
    ERP, support desk) refers to the same real-world entity. The alias
    carries enough metadata to enable reverse-lookup and merge operations.

    Attributes:
        source_system: Name of the upstream system (e.g. ``"salesforce"``).
        external_id: The ID used by the upstream system.
        display_name: Human-readable name as it appears in the source.
        entity_type_hint: The entity type label from the source system.
        attributes: Free-form key/value pairs from the source record.
        last_synced: Timestamp of the most recent sync from the source.
        confidence: Alignment confidence (0.0 – 1.0).
        source_record_id: Optional identifier of the original source record.
    """

    model_config = ConfigDict(extra="forbid", strict=True)

    source_system: str
    external_id: str
    display_name: str
    entity_type_hint: str
    attributes: dict[str, Any] = Field(default_factory=dict)
    last_synced: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    confidence: float = Field(ge=0.0, le=1.0, default=0.9)
    source_record_id: str = ""


class CanonicalEntity(BaseModel):
    """A single, authoritative representation of a real-world entity.

    Canonical entities are the system-of-record for entity resolution.
    Upstream systems contribute ``EntityAlias`` records that are merged
    into this canonical form, preserving provenance and confidence scores.

    Attributes:
        id: Globally unique identifier (ULID recommended).
        canonical_name: The resolved, human-readable name.
        entity_type: Entity type label (e.g. ``"customer"``, ``"vendor"``).
        semantic_type: Taxonomy classification as key/value pairs.
        aliases: List of upstream aliases mapped to this entity.
        source_of_truth: Which system is considered authoritative.
        confidence: Overall resolution confidence (0.0 – 1.0).
        attributes: Free-form key/value metadata.
        relationships: IDs of related ``CanonicalEntity`` records.
        tenant_id: Multi-tenant isolation identifier.
        created_at: Creation timestamp (UTC).
        updated_at: Last-modified timestamp (UTC).
    """

    model_config = ConfigDict(extra="forbid", strict=True)

    id: str
    canonical_name: str
    entity_type: str
    semantic_type: dict[str, str] = Field(default_factory=dict)
    aliases: list[EntityAlias] = Field(default_factory=list)
    source_of_truth: str = ""
    confidence: float = Field(ge=0.0, le=1.0, default=0.9)
    attributes: dict[str, Any] = Field(default_factory=dict)
    relationships: list[str] = Field(default_factory=list)
    tenant_id: str = ""
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

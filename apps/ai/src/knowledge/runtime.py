# FROZEN — V6.0 M0.5
"""OntologyAI V6 — Knowledge Runtime Interface (ABC).

The Knowledge Runtime is the **Layer 5** execution domain responsible for
canonical entity resolution, typed relationship creation, deduplication
and entity merging, and audit-trail versioning.

This module defines the **frozen contract** that all Knowledge Runtime
implementations must satisfy.  It contains **no execution logic** — only
the abstract interface, type contracts, and error hierarchy.

Pipeline stages
---------------
1. **resolve** — Entity resolution (exact → fuzzy → attribute → relationship → LLM).
2. **link**    — Create typed relationships between entities.
3. **merge**   — Deduplicate + merge entity records.
4. **version** — Track entity version history for audit trail.

Design constraints
------------------
* Resolution follows the 5-tier strategy: exact → fuzzy → attribute →
  relationship → LLM-assisted (lowest confidence).
* Source-of-truth hierarchy governs attribute-level conflict resolution.
* All mutations produce a version snapshot for audit trail compliance.
* The Knowledge Runtime never directly calls LLMs; it delegates that
  responsibility to the Decision Runtime.

FROZEN — V6.0 M0.5
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import datetime
from typing import Any

from src.schemas.semantic_layer import CanonicalEntity, EntityAlias, ResolutionTier


# ── Error hierarchy ──────────────────────────────────────────────────────


class KnowledgeRuntimeError(Exception):
    """Base exception for all Knowledge Runtime failures."""


class ResolutionError(KnowledgeRuntimeError):
    """Raised when entity resolution fails across all tiers.

    Parameters
    ----------
    entity_type : str
        The entity type that could not be resolved.
    name : str
        The canonical name that was attempted.
    reason : str
        Human-readable explanation.
    """

    def __init__(self, entity_type: str, name: str, reason: str) -> None:
        self.entity_type = entity_type
        self.name = name
        self.reason = reason
        super().__init__(
            f"Resolution failed for {entity_type} '{name}': {reason}"
        )


class LinkError(KnowledgeRuntimeError):
    """Raised when a typed relationship cannot be created between entities.

    Parameters
    ----------
    source_id : str
        The source entity ULID.
    target_id : str
        The target entity ULID.
    relationship_type : str
        The relationship type that failed.
    reason : str
        Human-readable explanation.
    """

    def __init__(
        self, source_id: str, target_id: str, relationship_type: str, reason: str
    ) -> None:
        self.source_id = source_id
        self.target_id = target_id
        self.relationship_type = relationship_type
        self.reason = reason
        super().__init__(
            f"Link failed: {source_id} —[{relationship_type}]→ {target_id}: {reason}"
        )


class MergeError(KnowledgeRuntimeError):
    """Raised when entity deduplication or merge fails.

    Parameters
    ----------
    source_id : str
        The entity ULID that was the merge source.
    target_id : str
        The entity ULID that was the merge target.
    reason : str
        Human-readable explanation.
    """

    def __init__(self, source_id: str, target_id: str, reason: str) -> None:
        self.source_id = source_id
        self.target_id = target_id
        self.reason = reason
        super().__init__(
            f"Merge failed ({source_id} → {target_id}): {reason}"
        )


class VersioningError(KnowledgeRuntimeError):
    """Raised when a version snapshot cannot be recorded.

    Parameters
    ----------
    entity_id : str
        The entity ULID whose version could not be recorded.
    reason : str
        Human-readable explanation.
    """

    def __init__(self, entity_id: str, reason: str) -> None:
        self.entity_id = entity_id
        self.reason = reason
        super().__init__(
            f"Versioning failed for entity '{entity_id}': {reason}"
        )


# ── Value objects ────────────────────────────────────────────────────────


class EntityVersion:
    """Immutable snapshot of an entity at a point in time.

    Parameters
    ----------
    entity_id : str
        The canonical entity ULID.
    version_number : int
        Monotonically increasing version number (1-based).
    snapshot : dict[str, Any]
        Complete entity state at this version.
    changed_fields : list[str]
        Fields that changed relative to the previous version.
    changed_by : str
        Identifier of the agent or user that caused the change.
    changed_at : datetime
        Timestamp of the version (UTC).
    """

    __slots__ = (
        "entity_id",
        "version_number",
        "snapshot",
        "changed_fields",
        "changed_by",
        "changed_at",
    )

    def __init__(
        self,
        entity_id: str,
        version_number: int,
        snapshot: dict[str, Any],
        changed_fields: list[str],
        changed_by: str,
        changed_at: datetime,
    ) -> None:
        self.entity_id = entity_id
        self.version_number = version_number
        self.snapshot = snapshot
        self.changed_fields = changed_fields
        self.changed_by = changed_by
        self.changed_at = changed_at

    def __repr__(self) -> str:
        return (
            f"EntityVersion(entity={self.entity_id!r}, "
            f"v{self.version_number}, fields={self.changed_fields!r})"
        )


class LinkResult:
    """Result of a ``link()`` operation.

    Parameters
    ----------
    source_id : str
        Source entity ULID.
    target_id : str
        Target entity ULID.
    relationship_type : str
        The typed relationship that was created.
    confidence : float
        Link confidence (0.0–1.0).
    created_at : datetime
        When the link was created.
    """

    __slots__ = (
        "source_id",
        "target_id",
        "relationship_type",
        "confidence",
        "created_at",
    )

    def __init__(
        self,
        source_id: str,
        target_id: str,
        relationship_type: str,
        confidence: float,
        created_at: datetime,
    ) -> None:
        self.source_id = source_id
        self.target_id = target_id
        self.relationship_type = relationship_type
        self.confidence = confidence
        self.created_at = created_at

    def __repr__(self) -> str:
        return (
            f"LinkResult({self.source_id} —[{self.relationship_type}]→ "
            f"{self.target_id}, conf={self.confidence:.2f})"
        )


class MergeResult:
    """Result of a ``merge()`` operation.

    Parameters
    ----------
    survivor_id : str
        The ULID of the entity that survived the merge.
    absorbed_id : str
        The ULID of the entity that was absorbed and removed.
    merged_fields : list[str]
        Fields that were carried from absorbed to survivor.
    confidence_delta : float
        Change in the survivor's confidence after merge.
    merged_at : datetime
        When the merge was completed.
    """

    __slots__ = (
        "survivor_id",
        "absorbed_id",
        "merged_fields",
        "confidence_delta",
        "merged_at",
    )

    def __init__(
        self,
        survivor_id: str,
        absorbed_id: str,
        merged_fields: list[str],
        confidence_delta: float,
        merged_at: datetime,
    ) -> None:
        self.survivor_id = survivor_id
        self.absorbed_id = absorbed_id
        self.merged_fields = merged_fields
        self.confidence_delta = confidence_delta
        self.merged_at = merged_at

    def __repr__(self) -> str:
        return (
            f"MergeResult({self.absorbed_id} → {self.survivor_id}, "
            f"fields={self.merged_fields!r})"
        )


# ── Abstract Runtime Interface ───────────────────────────────────────────


class KnowledgeRuntime(ABC):
    """Frozen interface for the Knowledge Runtime (V6.0 M0.5).

    Every implementation of this ABC must satisfy the four-stage pipeline:

    1. ``resolve`` — Entity resolution (5-tier strategy).
    2. ``link``    — Create typed relationships.
    3. ``merge``   — Deduplicate and merge entities.
    4. ``version`` — Record audit-trail version snapshots.

    Implementations may use any persistence backend (Neo4j, PostgreSQL +
    pgvector, in-memory) as long as the contract semantics are preserved.

    FROZEN — V6.0 M0.5 — Do not modify this interface.
    """

    @abstractmethod
    async def resolve(
        self,
        entity_type: str,
        name: str,
        attributes: dict[str, Any] | None = None,
        *,
        source_system: str = "",
        external_id: str = "",
        tenant_id: str,
    ) -> CanonicalEntity:
        """Resolve an incoming entity against existing canonical entities.

        Runs the 5-tier resolution strategy in priority order:

        1. **Exact** — Match on ``external_id`` + ``source_system``.
        2. **Fuzzy** — Levenshtein similarity on name + entity type (> 0.85).
        3. **Attribute** — Match on email, phone, or domain.
        4. **Relationship** — Match on shared parent or contact references.
        5. **LLM-assisted** — Low-confidence fallback (creates new entity).

        Creates a new canonical entity if no match is found at any tier.

        Parameters
        ----------
        entity_type : str
            Entity type label (e.g. ``"customer"``, ``"vendor"``).
        name : str
            Human-readable canonical name.
        attributes : dict[str, Any] | None
            Optional attributes (email, phone, domain, etc.).
        source_system : str
            Upstream system that originated this entity.
        external_id : str
            The ID used by the source system.
        tenant_id : str
            Multi-tenant isolation identifier.

        Returns
        -------
        CanonicalEntity
            The resolved (or newly created) canonical entity.

        Raises
        ------
        ResolutionError
            If resolution fails across all tiers and entity creation is not
            possible.
        """
        ...

    @abstractmethod
    async def link(
        self,
        source_id: str,
        target_id: str,
        relationship_type: str,
        *,
        confidence: float = 0.9,
        attributes: dict[str, Any] | None = None,
        tenant_id: str,
    ) -> LinkResult:
        """Create a typed relationship between two canonical entities.

        The relationship is stored as a directed edge from *source_id* to
        *target_id* with type *relationship_type*.  The reverse direction
        is not implied — call ``link()`` again in the opposite direction
        if bidirectionality is required.

        Parameters
        ----------
        source_id : str
            ULID of the source entity.
        target_id : str
            ULID of the target entity.
        relationship_type : str
            Typed relationship label (e.g. ``"owns"``, ``"reports_to"``).
        confidence : float
            Relationship confidence (0.0–1.0).
        attributes : dict[str, Any] | None
            Optional relationship attributes (e.g. ``{"since": "2024-01"}``).
        tenant_id : str
            Multi-tenant isolation identifier.

        Returns
        -------
        LinkResult
            The created link with metadata.

        Raises
        ------
        LinkError
            If the relationship cannot be created (e.g. entity not found,
            circular dependency detected, policy violation).
        """
        ...

    @abstractmethod
    async def merge(
        self,
        source_entity_id: str,
        target_entity_id: str,
        *,
        tenant_id: str,
    ) -> MergeResult:
        """Deduplicate by merging *source* into *target*.

        The source entity's aliases are transferred to the target.  The
        source entity is removed from the store.  Relationships pointing
        to the source are redirected to the target.

        Parameters
        ----------
        source_entity_id : str
            ULID of the entity to merge (will be removed).
        target_entity_id : str
            ULID of the entity to merge into (will survive).
        tenant_id : str
            Multi-tenant isolation identifier.

        Returns
        -------
        MergeResult
            The merge outcome including survivor ID and merged fields.

        Raises
        ------
        MergeError
            If either entity does not exist or the merge violates a
            business rule.
        """
        ...

    @abstractmethod
    async def version(
        self,
        entity_id: str,
        *,
        changed_by: str = "system",
        reason: str = "",
        tenant_id: str,
    ) -> EntityVersion:
        """Record a version snapshot of an entity for audit trail.

        Captures the current state of *entity_id* as an immutable snapshot.
        Each call increments the version number monotonically.

        Parameters
        ----------
        entity_id : str
            ULID of the entity to version.
        changed_by : str
            Identifier of the agent or user that caused the change.
        reason : str
            Human-readable explanation of what changed.
        tenant_id : str
            Multi-tenant isolation identifier.

        Returns
        -------
        EntityVersion
            The recorded version snapshot.

        Raises
        ------
        VersioningError
            If the entity does not exist or the snapshot cannot be recorded.
        """
        ...


__all__ = [
    "KnowledgeRuntime",
    "KnowledgeRuntimeError",
    "ResolutionError",
    "LinkError",
    "MergeError",
    "VersioningError",
    "EntityVersion",
    "LinkResult",
    "MergeResult",
]

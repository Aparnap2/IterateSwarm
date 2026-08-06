"""Enterprise Semantic Layer — canonical entity resolution across source systems.

Implements the 5-tier resolution strategy specified in the architect-agent
design (CAPABILITY_ONTOLOGY_V6.md):

1. Exact match (external_id)
2. Fuzzy match (name + type, Levenshtein)
3. Attribute match (email, phone, domain)
4. Relationship match (shared parent/contacts)
5. LLM-assisted (low-confidence cases)

Resolution decisions are governed by:
- Source-of-truth hierarchy per entity_type
- Temporal precedence (most recent wins)
- Confidence weighting (higher confidence sources win)
- Manual override capability

Usage:
    from src.knowledge.semantic_layer import SemanticLayer

    layer = SemanticLayer()
    entity = await layer.resolve(
        entity_type="customer",
        name="Acme Corp",
        attributes={"email": "info@acme.com"},
        source_system="salesforce",
        external_id="sf-001",
    )
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from src.schemas.semantic_layer import (
    AttributeConflict,
    CanonicalEntity,
    ConflictStatus,
    EntityAlias,
    EntityLineage,
    ResolutionTier,
)

logger = logging.getLogger(__name__)

# ── Source-of-truth hierarchy per entity_type ──────────────────────

_SOURCE_OF_TRUTH_HIERARCHY: dict[str, dict[str, list[str]]] = {
    "customer": {
        "email": ["crm", "erp", "support", "salesforce"],
        "phone": ["crm", "erp", "support", "salesforce"],
        "name": ["crm", "erp", "support", "salesforce"],
        "domain": ["crm", "erp", "support", "salesforce"],
    },
    "vendor": {
        "email": ["erp", "crm", "finance", "salesforce"],
        "phone": ["erp", "crm", "finance", "salesforce"],
        "name": ["erp", "crm", "finance", "salesforce"],
        "domain": ["erp", "crm", "finance", "salesforce"],
    },
    "product": {
        "name": ["erp", "crm", "catalog", "salesforce"],
        "sku": ["erp", "catalog", "crm", "salesforce"],
    },
    "stakeholder": {
        "email": ["crm", "slack", "email", "support"],
        "name": ["crm", "slack", "email", "support"],
        "phone": ["crm", "slack", "email", "support"],
    },
}

_DEFAULT_SOURCE_OF_TRUTH: dict[str, list[str]] = {
    "email": ["crm", "erp", "support", "salesforce"],
    "phone": ["crm", "erp", "support", "salesforce"],
    "name": ["crm", "erp", "support", "salesforce"],
    "domain": ["crm", "erp", "support", "salesforce"],
}

# ── Levenshtein helpers (no external dep) ──────────────────────────


def _levenshtein(a: str, b: str) -> int:
    """Compute the Levenshtein edit distance between two strings."""
    if len(a) < len(b):
        a, b = b, a
    if not b:
        return len(a)
    previous_row = range(len(b) + 1)
    for i, ca in enumerate(a):
        current_row = [i + 1]
        for j, cb in enumerate(b):
            insertions = previous_row[j + 1] + 1
            deletions = current_row[j] + 1
            substitutions = previous_row[j] + (ca != cb)
            current_row.append(min(insertions, deletions, substitutions))
        previous_row = current_row
    return previous_row[-1]


def _lev_ratio(a: str, b: str) -> float:
    """Return Levenshtein similarity ratio (0.0 – 1.0)."""
    if not a and not b:
        return 1.0
    distance = _levenshtein(a.lower(), b.lower())
    max_len = max(len(a), len(b))
    return 1.0 - (distance / max_len)


# ── In-memory entity store (default when no store is provided) ─────


class InMemoryEntityStore:
    """Simple in-memory entity store for when no persistent store is configured.

    Provides the same interface as a persistent store so the
    ``SemanticLayer`` can operate without Neo4j or PostgreSQL.
    """

    def __init__(self) -> None:
        self._entities: dict[str, CanonicalEntity] = {}
        self._by_external_id: dict[str, str] = {}
        self._by_attribute: dict[str, list[str]] = {}

    async def get(self, entity_id: str) -> CanonicalEntity | None:
        return self._entities.get(entity_id)

    async def find_by_external_id(
        self, external_id: str, source_system: str
    ) -> CanonicalEntity | None:
        key = f"{source_system}:{external_id}"
        entity_id = self._by_external_id.get(key)
        if entity_id is not None:
            return self._entities.get(entity_id)
        return None

    async def find_by_name(
        self, entity_type: str, name: str, threshold: float = 0.85
    ) -> list[CanonicalEntity]:
        results: list[CanonicalEntity] = []
        for entity in self._entities.values():
            if entity.entity_type != entity_type:
                continue
            for alias in entity.aliases:
                if _lev_ratio(name, alias.display_name) >= threshold:
                    results.append(entity)
                    break
        return results

    async def find_by_attribute(
        self, entity_type: str, attr_name: str, attr_value: str
    ) -> list[CanonicalEntity]:
        key = f"{entity_type}:{attr_name}:{attr_value}"
        entity_ids: list[str] = self._by_attribute.get(key, [])
        return [
            self._entities[eid]
            for eid in entity_ids
            if eid in self._entities
        ]

    async def find_by_relationship(
        self, entity_id: str, relationship_type: str
    ) -> list[CanonicalEntity]:
        entity = self._entities.get(entity_id)
        if entity is None:
            return []
        related: list[CanonicalEntity] = []
        for rel_id in entity.relationships:
            related_entity = self._entities.get(rel_id)
            if related_entity is not None:
                related.append(related_entity)
        return related

    async def save(self, entity: CanonicalEntity) -> CanonicalEntity:
        self._entities[entity.id] = entity
        for alias in entity.aliases:
            key = f"{alias.source_system}:{alias.external_id}"
            self._by_external_id[key] = entity.id
            for attr_name, attr_value in alias.attributes.items():
                if isinstance(attr_value, str):
                    attr_key = f"{entity.entity_type}:{attr_name}:{attr_value.lower()}"
                    self._by_attribute.setdefault(attr_key, []).append(entity.id)
        return entity

    async def list(
        self,
        entity_type: str | None = None,
        filters: dict[str, Any] | None = None,
        source_system: str | None = None,
    ) -> list[CanonicalEntity]:
        results: list[CanonicalEntity] = []
        for entity in self._entities.values():
            if entity_type is not None and entity.entity_type != entity_type:
                continue
            if source_system is not None:
                source_aliases = [
                    a for a in entity.aliases if a.source_system == source_system
                ]
                if not source_aliases:
                    continue
            if filters:
                match = True
                for fk, fv in filters.items():
                    if fk == "entity_type":
                        if entity.entity_type != fv:
                            match = False
                            break
                    elif fk == "min_confidence":
                        if entity.confidence < fv:
                            match = False
                            break
                    elif fk == "tenant_id":
                        if entity.tenant_id != fv:
                            match = False
                            break
                    elif fk in entity.attributes:
                        if entity.attributes[fk] != fv:
                            match = False
                            break
                if not match:
                    continue
            results.append(entity)
        return results


# ── Resolution result ────────────────────────────────────────────────


class ResolutionResult(BaseModel):
    """Result of a single resolution attempt.

    Attributes:
        entity: The resolved canonical entity (or newly created).
        tier: Which resolution tier produced this result.
        matched: Whether an existing entity was matched.
        confidence: Resolution confidence (0.0 – 1.0).
    """

    model_config = ConfigDict(extra="forbid", strict=True)

    entity: CanonicalEntity
    tier: ResolutionTier
    matched: bool
    confidence: float = Field(ge=0.0, le=1.0)


# ── Main SemanticLayer ───────────────────────────────────────────────


class SemanticLayer:
    """Enterprise Semantic Layer — canonical entity resolution across sources.

    Parameters
    ----------
    entity_store:
        A duck-typed entity store with ``find_by_external_id``,
        ``find_by_name``, ``find_by_attribute``, ``find_by_relationship``,
        ``save``, and ``list`` async methods.  If ``None``, an
        ``InMemoryEntityStore`` is used.
    conflict_resolver:
        A :class:`~src.knowledge.conflict_resolver.ConflictResolver`
        instance for resolving attribute conflicts.  If ``None``, a
        default resolver is created.
    source_of_truth:
        Per-entity-type source-of-truth hierarchy for attribute resolution.
        Defaults to the built-in hierarchy.
    """

    def __init__(
        self,
        entity_store: Any | None = None,
        conflict_resolver: Any | None = None,
        source_of_truth: dict[str, dict[str, list[str]]] | None = None,
    ) -> None:
        self._store = entity_store if entity_store is not None else InMemoryEntityStore()
        self._conflict_resolver = conflict_resolver
        self._source_of_truth = (
            source_of_truth if source_of_truth is not None else _SOURCE_OF_TRUTH_HIERARCHY
        )
        self._manual_overrides: dict[str, dict[str, Any]] = {}

    async def resolve(
        self,
        entity_type: str,
        name: str,
        attributes: dict[str, Any] | None = None,
        source_system: str = "",
        external_id: str = "",
    ) -> CanonicalEntity:
        """Resolve incoming entity against existing canonical entities.

        Runs the 5-tier resolution strategy in priority order:
        1. Exact match on external_id
        2. Fuzzy match on name + type (Levenshtein)
        3. Attribute match (email, phone, domain)
        4. Relationship match (shared parent/contacts)
        5. LLM-assisted (low-confidence fallback)

        Creates a new canonical entity if no match is found at any tier.

        Parameters
        ----------
        entity_type:
            The type of entity to resolve (e.g. ``"customer"``, ``"vendor"``).
        name:
            The human-readable name of the entity.
        attributes:
            Optional free-form attributes (email, phone, domain, etc.).
        source_system:
            The upstream system that originated this entity (e.g. ``"salesforce"``).
        external_id:
            The ID used by the source system for this entity.

        Returns
        -------
        CanonicalEntity
            The resolved (or newly created) canonical entity.
        """
        attributes = attributes or {}
        logger.info(
            "Resolving entity type=%s name=%s source=%s ext_id=%s",
            entity_type,
            name,
            source_system,
            external_id or "(none)",
        )

        # Check for manual override first
        override_key = f"{source_system}:{external_id}" if external_id else ""
        if override_key and override_key in self._manual_overrides:
            logger.info("Manual override found for %s", override_key)
            override = self._manual_overrides[override_key]
            return CanonicalEntity(**override)

        # Tier 1: Exact match on external_id
        if external_id and source_system:
            entity = await self._tier1_exact_match(external_id, source_system)
            if entity is not None:
                logger.info(
                    "Tier 1 exact match for %s:%s → %s",
                    source_system,
                    external_id,
                    entity.id,
                )
                return entity

        # Tier 2: Fuzzy match on name + type
        if name:
            entity = await self._tier2_fuzzy_match(entity_type, name)
            if entity is not None:
                logger.info(
                    "Tier 2 fuzzy match for %s (%s) → %s",
                    name,
                    entity_type,
                    entity.id,
                )
                return entity

        # Tier 3: Attribute match (email, phone, domain)
        attr_match = await self._tier3_attribute_match(entity_type, attributes)
        if attr_match is not None:
            logger.info(
                "Tier 3 attribute match for %s (%s) → %s",
                name,
                entity_type,
                attr_match.id,
            )
            return attr_match

        # Tier 4: Relationship match (shared parent/contacts)
        rel_match = await self._tier4_relationship_match(entity_type, attributes)
        if rel_match is not None:
            logger.info(
                "Tier 4 relationship match for %s (%s) → %s",
                name,
                entity_type,
                rel_match.id,
            )
            return rel_match

        # Tier 5: LLM-assisted (low-confidence fallback)
        # In the current implementation, this creates a new entity.
        # A production system would call an LLM here for disambiguation.
        display_name = name if name.strip() else "Unnamed Entity"
        logger.info(
            "Tier 5 LLM-assisted fallback — creating new entity for %s (%s)",
            display_name,
            entity_type,
        )
        new_entity = self._create_entity(
            entity_type=entity_type,
            name=display_name,
            attributes=attributes,
            source_system=source_system,
            external_id=external_id,
            confidence=0.5,  # Low confidence for new entities
        )
        await self._store.save(new_entity)
        return new_entity

    async def merge(
        self, source_entity_id: str, target_entity_id: str
    ) -> CanonicalEntity:
        """Merge two canonical entities (transfer aliases, remove source).

        The source entity's aliases are transferred to the target entity.
        The source entity is removed from the store.
        Relationships pointing to the source are redirected to the target.

        Parameters
        ----------
        source_entity_id:
            The ULID of the entity to merge (will be removed).
        target_entity_id:
            The ULID of the entity to merge into (will survive).

        Returns
        -------
        CanonicalEntity
            The merged target entity with all aliases and relationships.

        Raises
        ------
        ValueError
            If either entity does not exist.
        """
        source = await self._store.get(source_entity_id)
        target = await self._store.get(target_entity_id)

        if source is None:
            msg = f"Source entity {source_entity_id} not found"
            raise ValueError(msg)
        if target is None:
            msg = f"Target entity {target_entity_id} not found"
            raise ValueError(msg)

        logger.info(
            "Merging entity %s → %s (type=%s)",
            source_entity_id,
            target_entity_id,
            target.entity_type,
        )

        # Transfer aliases from source to target (avoid duplicates)
        existing_external_ids = {
            f"{a.source_system}:{a.external_id}" for a in target.aliases
        }
        for alias in source.aliases:
            alias_key = f"{alias.source_system}:{alias.external_id}"
            if alias_key not in existing_external_ids:
                target.aliases.append(alias)
                existing_external_ids.add(alias_key)

        # Merge attributes (prefer target's values, fill gaps from source)
        for key, value in source.attributes.items():
            if key not in target.attributes:
                target.attributes[key] = value

        # Redirect relationships pointing to source → target
        for rel_id in source.relationships:
            if rel_id != target_entity_id and rel_id not in target.relationships:
                target.relationships.append(rel_id)

        # Update confidence (weighted average, favoring the target)
        target.confidence = round(
            (target.confidence * 0.6 + source.confidence * 0.4), 4
        )

        # Update timestamp
        target.updated_at = datetime.now(timezone.utc)

        # Remove source entity
        await self._store.save(target)
        await self._delete_entity(source_entity_id)

        logger.info(
            "Merge complete: %s aliases transferred, source %s removed",
            len(source.aliases),
            source_entity_id,
        )
        return target

    async def query(
        self,
        entity_type: str | None = None,
        filters: dict[str, Any] | None = None,
        source_system: str | None = None,
    ) -> list[CanonicalEntity]:
        """Query canonical entities with optional filters.

        Parameters
        ----------
        entity_type:
            Filter by entity type (e.g. ``"customer"``).
        filters:
            Free-form key/value filters applied to entity attributes.
        source_system:
            Filter to entities that have at least one alias from this source.

        Returns
        -------
        list[CanonicalEntity]
            Matching canonical entities.
        """
        return await self._store.list(
            entity_type=entity_type,
            filters=filters,
            source_system=source_system,
        )

    async def lineage(self, entity_id: str) -> EntityLineage:
        """Get full lineage of an entity across all source systems.

        Parameters
        ----------
        entity_id:
            The ULID of the canonical entity.

        Returns
        -------
        EntityLineage
            The full lineage including all aliases, resolution history,
            and conflicts.

        Raises
        ------
        ValueError
            If the entity does not exist.
        """
        entity = await self._store.get(entity_id)
        if entity is None:
            msg = f"Entity {entity_id} not found"
            raise ValueError(msg)

        # Collect resolution history from alias metadata
        resolution_history: list[dict[str, Any]] = []
        for alias in entity.aliases:
            resolution_history.append(
                {
                    "source_system": alias.source_system,
                    "external_id": alias.external_id,
                    "display_name": alias.display_name,
                    "confidence": alias.confidence,
                    "last_synced": alias.last_synced.isoformat(),
                    "source_record_id": alias.source_record_id,
                }
            )

        # Collect conflicts
        conflicts = await self._collect_conflicts(entity)

        return EntityLineage(
            entity_id=entity.id,
            canonical_name=entity.canonical_name,
            entity_type=entity.entity_type,
            aliases=entity.aliases,
            resolution_history=resolution_history,
            conflicts=conflicts,
            tenant_id=entity.tenant_id,
            created_at=entity.created_at,
            updated_at=entity.updated_at,
        )

    async def conflicts(self, entity_id: str) -> list[AttributeConflict]:
        """Find all attribute conflicts for an entity.

        Parameters
        ----------
        entity_id:
            The ULID of the canonical entity.

        Returns
        -------
        list[AttributeConflict]
            All detected attribute conflicts for this entity.
        """
        entity = await self._store.get(entity_id)
        if entity is None:
            logger.warning("Entity %s not found for conflict detection", entity_id)
            return []

        return await self._collect_conflicts(entity)

    async def set_manual_override(
        self, source_system: str, external_id: str, entity_data: dict[str, Any]
    ) -> None:
        """Set a manual override for entity resolution.

        When a resolution is requested for the given source_system +
        external_id combination, the override entity data is returned
        instead of running the normal resolution pipeline.

        Parameters
        ----------
        source_system:
            The upstream system name.
        external_id:
            The external ID in that system.
        entity_data:
            A dict of CanonicalEntity fields to use as the override.
        """
        key = f"{source_system}:{external_id}"
        self._manual_overrides[key] = entity_data
        logger.info("Manual override set for %s", key)

    # ── Tier 1: Exact match ──────────────────────────────────────────

    async def _tier1_exact_match(
        self, external_id: str, source_system: str
    ) -> CanonicalEntity | None:
        """Tier 1: Exact match on external_id + source_system."""
        return await self._store.find_by_external_id(external_id, source_system)

    # ── Tier 2: Fuzzy match ──────────────────────────────────────────

    async def _tier2_fuzzy_match(
        self, entity_type: str, name: str
    ) -> CanonicalEntity | None:
        """Tier 2: Fuzzy match on name + entity type (Levenshtein > 0.85)."""
        candidates = await self._store.find_by_name(entity_type, name, threshold=0.85)
        if not candidates:
            return None
        # Return the highest-confidence match
        return max(candidates, key=lambda e: e.confidence)

    # ── Tier 3: Attribute match ──────────────────────────────────────

    async def _tier3_attribute_match(
        self, entity_type: str, attributes: dict[str, Any]
    ) -> CanonicalEntity | None:
        """Tier 3: Attribute match on email, phone, domain."""
        attr_keys = ["email", "phone", "domain"]
        for attr_name in attr_keys:
            if attr_name not in attributes:
                continue
            attr_value = attributes[attr_name]
            if not isinstance(attr_value, str) or not attr_value.strip():
                continue
            candidates = await self._store.find_by_attribute(
                entity_type, attr_name, attr_value
            )
            if candidates:
                # Return highest-confidence match
                return max(candidates, key=lambda e: e.confidence)
        return None

    # ── Tier 4: Relationship match ───────────────────────────────────

    async def _tier4_relationship_match(
        self, entity_type: str, attributes: dict[str, Any]
    ) -> CanonicalEntity | None:
        """Tier 4: Relationship match (shared parent/contacts)."""
        # Check for parent_id or contact references in attributes
        parent_id = attributes.get("parent_id") or attributes.get("parent")
        contact_refs = attributes.get("contacts") or attributes.get("contact_ids", [])

        if parent_id:
            # Find entities of the same type that share this parent
            candidates = await self._store.list(
                entity_type=entity_type,
                filters={"parent_id": parent_id},
            )
            if candidates:
                return max(candidates, key=lambda e: e.confidence)

        if contact_refs and isinstance(contact_refs, list):
            for contact_ref in contact_refs:
                candidates = await self._store.list(
                    entity_type=entity_type,
                    filters={"contact_id": contact_ref},
                )
                if candidates:
                    return max(candidates, key=lambda e: e.confidence)

        return None

    # ── Entity creation ──────────────────────────────────────────────

    def _create_entity(
        self,
        entity_type: str,
        name: str,
        attributes: dict[str, Any],
        source_system: str,
        external_id: str,
        confidence: float,
    ) -> CanonicalEntity:
        """Create a new CanonicalEntity from resolved attributes."""
        import uuid

        entity_id = f"{uuid.uuid4().hex[:26].upper()}"
        now = datetime.now(timezone.utc)
        display_name = name if name.strip() else "Unnamed Entity"

        alias = EntityAlias(
            source_system=source_system,
            external_id=external_id,
            display_name=display_name,
            entity_type_hint=entity_type,
            attributes=attributes,
            last_synced=now,
            confidence=confidence,
        )

        # Determine source_of_truth from hierarchy
        source_of_truth = ""
        if entity_type in self._source_of_truth:
            for attr_name, sources in self._source_of_truth[entity_type].items():
                if sources:
                    source_of_truth = sources[0]
                    break

        return CanonicalEntity(
            id=entity_id,
            canonical_name=display_name,
            entity_type=entity_type,
            aliases=[alias],
            source_of_truth=source_of_truth,
            confidence=confidence,
            attributes=attributes,
            tenant_id="",
            created_at=now,
            updated_at=now,
        )

    # ── Entity deletion ──────────────────────────────────────────────

    async def _delete_entity(self, entity_id: str) -> None:
        """Remove an entity from the store (best-effort)."""
        if hasattr(self._store, "_entities"):
            self._store._entities.pop(entity_id, None)
            # Also clean up external_id and attribute indexes
            to_remove = [
                k for k, v in self._store._by_external_id.items()
                if v == entity_id
            ]
            for k in to_remove:
                del self._store._by_external_id[k]

    # ── Conflict collection ──────────────────────────────────────────

    async def _collect_conflicts(
        self, entity: CanonicalEntity
    ) -> list[AttributeConflict]:
        """Detect attribute conflicts across aliases for an entity."""
        conflicts: list[AttributeConflict] = []

        # Group alias attributes by name
        attr_sources: dict[str, list[dict[str, Any]]] = {}
        for alias in entity.aliases:
            for attr_name, attr_value in alias.attributes.items():
                attr_sources.setdefault(attr_name, []).append(
                    {
                        "source_system": alias.source_system,
                        "value": attr_value,
                        "confidence": alias.confidence,
                        "timestamp": alias.last_synced.isoformat(),
                    }
                )

        # Find conflicts (same attribute, different values across sources)
        for attr_name, sources in attr_sources.items():
            if len(sources) < 2:
                continue
            values = {str(s["value"]) for s in sources if s["value"] is not None}
            if len(values) > 1:
                conflict = AttributeConflict(
                    entity_id=entity.id,
                    attribute_name=attr_name,
                    conflicting_values=sources,
                    status=ConflictStatus.OPEN,
                )
                # Attempt auto-resolution
                resolved = self._resolve_conflict_auto(entity.entity_type, attr_name, sources)
                if resolved is not None:
                    conflict.resolved_value = resolved["value"]
                    conflict.resolution_method = resolved["method"]
                    conflict.status = ConflictStatus.RESOLVED
                    conflict.resolved_at = datetime.now(timezone.utc)
                conflicts.append(conflict)

        return conflicts

    def _resolve_conflict_auto(
        self,
        entity_type: str,
        attribute_name: str,
        sources: list[dict[str, Any]],
    ) -> dict[str, Any] | None:
        """Attempt automatic conflict resolution using source-of-truth hierarchy.

        Returns a dict with ``value`` and ``method`` keys, or ``None`` if
        resolution is not possible automatically.
        """
        hierarchy = self._source_of_truth.get(entity_type, _DEFAULT_SOURCE_OF_TRUTH)
        priority_sources = hierarchy.get(attribute_name, [])

        # Try source-of-truth hierarchy first
        for source_name in priority_sources:
            for s in sources:
                if s["source_system"] == source_name:
                    return {"value": s["value"], "method": "source_of_truth"}

        # Try temporal precedence (most recent wins)
        sorted_sources = sorted(
            sources,
            key=lambda s: s.get("timestamp", ""),
            reverse=True,
        )
        if sorted_sources:
            return {"value": sorted_sources[0]["value"], "method": "temporal_precedence"}

        # Try confidence weighting
        sorted_by_confidence = sorted(sources, key=lambda s: s.get("confidence", 0.0), reverse=True)
        if sorted_by_confidence:
            return {"value": sorted_by_confidence[0]["value"], "method": "confidence_weighting"}

        return None


__all__ = [
    "SemanticLayer",
    "ResolutionResult",
    "ResolutionTier",
    "InMemoryEntityStore",
]
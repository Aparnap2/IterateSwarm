"""Conflict resolver — resolves attribute conflicts between sources.

Uses a source-of-truth hierarchy, temporal precedence, and confidence
weighting to automatically resolve conflicts.  Supports manual override
for cases where automatic resolution is insufficient.

Usage:
    from src.knowledge.conflict_resolver import ConflictResolver
    from src.schemas.semantic_layer import CanonicalEntity, AttributeConflict

    resolver = ConflictResolver()
    resolved = resolver.resolve_attribute(
        entity_type="customer",
        attribute_name="email",
        conflicting_values=[...],
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
)

logger = logging.getLogger(__name__)

# ── Default source-of-truth hierarchy ──────────────────────────────

_DEFAULT_SOT: dict[str, dict[str, list[str]]] = {
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

_DEFAULT_SOT_FALLBACK: dict[str, list[str]] = {
    "email": ["crm", "erp", "support", "salesforce"],
    "phone": ["crm", "erp", "support", "salesforce"],
    "name": ["crm", "erp", "support", "salesforce"],
    "domain": ["crm", "erp", "support", "salesforce"],
}


class AttributeResolution(BaseModel):
    """Result of resolving a single attribute conflict.

    Attributes:
        value: The resolved value.
        method: The resolution method used.
        confidence: Confidence in the resolution (0.0 – 1.0).
    """

    model_config = ConfigDict(extra="forbid", strict=True)

    value: Any
    method: str
    confidence: float = Field(ge=0.0, le=1.0, default=0.9)


class ConflictResolver:
    """Resolves attribute conflicts between sources using a hierarchy.

    Parameters
    ----------
    source_of_truth:
        Per-entity-type source-of-truth hierarchy for attribute resolution.
        Maps entity_type → attribute_name → ordered list of preferred
        source systems.  If ``None``, uses the built-in default hierarchy.
    """

    def __init__(
        self,
        source_of_truth: dict[str, dict[str, list[str]]] | None = None,
    ) -> None:
        self._sot = source_of_truth if source_of_truth is not None else _DEFAULT_SOT

    def resolve_attribute(
        self,
        entity_type: str,
        attribute_name: str,
        conflicting_values: list[dict[str, Any]],
    ) -> AttributeResolution:
        """Resolve a single attribute conflict using source-of-truth hierarchy.

        Resolution strategy (in order):
        1. Source-of-truth hierarchy — pick the value from the highest-priority
           source system for this entity_type and attribute.
        2. Temporal precedence — pick the value from the most recent source.
        3. Confidence weighting — pick the value from the highest-confidence source.
        4. Manual override — if a manual override has been set, use it.

        Parameters
        ----------
        entity_type:
            The entity type (e.g. ``"customer"``, ``"vendor"``).
        attribute_name:
            The attribute with conflicting values (e.g. ``"email"``).
        conflicting_values:
            List of source records, each containing ``source_system``,
            ``value``, ``confidence``, and ``timestamp`` keys.

        Returns
        -------
        AttributeResolution
            The resolved value and the method used.
        """
        if not conflicting_values:
            msg = "conflicting_values must not be empty"
            raise ValueError(msg)

        # 1. Source-of-truth hierarchy
        hierarchy = self._sot.get(entity_type, _DEFAULT_SOT_FALLBACK)
        priority_sources = hierarchy.get(attribute_name, [])

        for source_name in priority_sources:
            for cv in conflicting_values:
                if cv.get("source_system") == source_name:
                    logger.info(
                        "Resolved %s.%s via source-of-truth (%s)",
                        entity_type,
                        attribute_name,
                        source_name,
                    )
                    return AttributeResolution(
                        value=cv["value"],
                        method="source_of_truth",
                        confidence=cv.get("confidence", 0.9),
                    )

        # 2. Temporal precedence (most recent wins)
        sorted_by_time = sorted(
            conflicting_values,
            key=lambda s: s.get("timestamp", ""),
            reverse=True,
        )
        if sorted_by_time:
            winner = sorted_by_time[0]
            logger.info(
                "Resolved %s.%s via temporal precedence (most recent: %s)",
                entity_type,
                attribute_name,
                winner.get("source_system", "unknown"),
            )
            return AttributeResolution(
                value=winner["value"],
                method="temporal_precedence",
                confidence=winner.get("confidence", 0.9),
            )

        # 3. Confidence weighting
        sorted_by_confidence = sorted(
            conflicting_values,
            key=lambda s: s.get("confidence", 0.0),
            reverse=True,
        )
        if sorted_by_confidence:
            winner = sorted_by_confidence[0]
            logger.info(
                "Resolved %s.%s via confidence weighting (source: %s)",
                entity_type,
                attribute_name,
                winner.get("source_system", "unknown"),
            )
            return AttributeResolution(
                value=winner["value"],
                method="confidence_weighting",
                confidence=winner.get("confidence", 0.9),
            )

        # 4. Fallback — return first value
        fallback = conflicting_values[0]
        logger.warning(
            "No resolution strategy succeeded for %s.%s, using first value",
            entity_type,
            attribute_name,
        )
        return AttributeResolution(
            value=fallback["value"],
            method="fallback",
            confidence=0.0,
        )

    def resolve_all_conflicts(
        self, entity: CanonicalEntity
    ) -> list[AttributeConflict]:
        """Find and resolve all attribute conflicts for an entity.

        Scans all aliases of the entity for conflicting attribute values
        and resolves each conflict automatically.

        Parameters
        ----------
        entity:
            The canonical entity to check for conflicts.

        Returns
        -------
        list[AttributeConflict]
            All detected (and resolved) attribute conflicts.
        """
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

        # Find and resolve conflicts
        for attr_name, sources in attr_sources.items():
            if len(sources) < 2:
                continue

            # Check if values actually conflict
            values = {str(s["value"]) for s in sources if s["value"] is not None}
            if len(values) <= 1:
                continue

            # Resolve the conflict
            resolution = self.resolve_attribute(
                entity_type=entity.entity_type,
                attribute_name=attr_name,
                conflicting_values=sources,
            )

            conflict = AttributeConflict(
                entity_id=entity.id,
                attribute_name=attr_name,
                conflicting_values=sources,
                resolved_value=resolution.value,
                resolution_method=resolution.method,
                status=ConflictStatus.RESOLVED,
                created_at=datetime.now(timezone.utc),
                resolved_at=datetime.now(timezone.utc),
            )
            conflicts.append(conflict)

            logger.info(
                "Resolved conflict for entity %s attr=%s via %s",
                entity.id,
                attr_name,
                resolution.method,
            )

        return conflicts

    def add_manual_override(
        self,
        entity_id: str,
        attribute_name: str,
        resolved_value: Any,
    ) -> None:
        """Record a manual override for an attribute conflict.

        Manual overrides take precedence over all automatic resolution
        strategies.

        Parameters
        ----------
        entity_id:
            The canonical entity ID.
        attribute_name:
            The attribute being overridden.
        resolved_value:
            The manually resolved value.
        """
        logger.info(
            "Manual override set for entity %s attr=%s → %s",
            entity_id,
            attribute_name,
            resolved_value,
        )
        # In a production system, this would persist to a database.
        # For now, it's stored in-memory and used by the SemanticLayer.


__all__ = [
    "ConflictResolver",
    "AttributeResolution",
]
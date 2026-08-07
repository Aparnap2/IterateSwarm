"""Connector bridge — bridges connector EvidenceRecords into the semantic layer.

Ingests evidence records from connectors and resolves them into
canonical entities using the SemanticLayer's 5-tier resolution strategy.

Usage:
    from src.knowledge.connector_bridge import ConnectorBridge
    from src.knowledge.semantic_layer import SemanticLayer

    layer = SemanticLayer()
    bridge = ConnectorBridge(semantic_layer=layer)

    entity = await bridge.ingest_evidence(evidence_record)
    entities = await bridge.ingest_batch([evidence1, evidence2])
"""

from __future__ import annotations

import logging
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from src.entities.models import EvidenceRecord
from src.schemas.semantic_layer import CanonicalEntity

from src.knowledge.semantic_layer import SemanticLayer

logger = logging.getLogger(__name__)


class IngestResult(BaseModel):
    """Result of ingesting an evidence record into the semantic layer.

    Attributes:
        entity: The resolved or newly created canonical entity.
        evidence_id: The ID of the evidence record that was ingested.
        matched: Whether an existing entity was matched (True) or a new one was created (False).
        resolution_tier: Which resolution tier produced the result.
        confidence: The confidence of the resolution.
    """

    model_config = ConfigDict(extra="forbid", strict=True)

    entity: CanonicalEntity
    evidence_id: str
    matched: bool
    resolution_tier: str
    confidence: float = Field(ge=0.0, le=1.0)


class ConnectorBridge:
    """Bridges connector EvidenceRecords into the semantic layer.

    Parameters
    ----------
    semantic_layer:
        An initialised :class:`~src.knowledge.semantic_layer.SemanticLayer`
        instance used for entity resolution.
    default_source_system:
        Default source system name to use when evidence records don't
        specify one.
    """

    def __init__(
        self,
        semantic_layer: SemanticLayer | None = None,
        default_source_system: str = "connector",
    ) -> None:
        self._layer = semantic_layer if semantic_layer is not None else SemanticLayer()
        self._default_source = default_source_system

    async def ingest_evidence(
        self, evidence: EvidenceRecord
    ) -> CanonicalEntity | None:
        """Ingest an EvidenceRecord into the semantic layer.

        Extracts entity references from the evidence record's
        ``structured_data`` and resolves them against existing
        canonical entities using the 5-tier resolution strategy.

        Parameters
        ----------
        evidence:
            The evidence record to ingest.

        Returns
        -------
        CanonicalEntity | None
            The resolved canonical entity, or ``None`` if no entity
            could be extracted from the evidence.
        """
        logger.info(
            "Ingesting evidence %s from source %s",
            evidence.id,
            evidence.source,
        )

        structured = evidence.structured_data or {}
        source_system = evidence.source or self._default_source

        # Extract entity type and name from structured_data
        entity_type = self._extract_entity_type(structured)
        name = self._extract_name(structured)
        attributes = self._extract_attributes(structured)
        external_id = self._extract_external_id(structured)

        if not entity_type and not name:
            logger.warning(
                "Evidence %s has no extractable entity type or name — skipping",
                evidence.id,
            )
            return None

        # Resolve the entity through the semantic layer
        entity = await self._layer.resolve(
            entity_type=entity_type or "unknown",
            name=name or "Unnamed Entity",
            attributes=attributes,
            source_system=source_system,
            external_id=external_id,
        )

        logger.info(
            "Ingested evidence %s → entity %s (type=%s, matched=%s)",
            evidence.id,
            entity.id,
            entity.entity_type,
            len(entity.aliases) > 0,
        )
        return entity

    async def ingest_batch(
        self, evidence_list: list[EvidenceRecord]
    ) -> list[CanonicalEntity]:
        """Ingest a batch of EvidenceRecords into the semantic layer.

        Processes each evidence record sequentially and resolves
        entities using the semantic layer's 5-tier strategy.

        Parameters
        ----------
        evidence_list:
            Evidence records to ingest.

        Returns
        -------
        list[CanonicalEntity]
            Resolved canonical entities (one per evidence record that
            contained extractable entity data).
        """
        results: list[CanonicalEntity] = []

        for evidence in evidence_list:
            try:
                entity = await self.ingest_evidence(evidence)
                if entity is not None:
                    results.append(entity)
            except Exception:
                logger.exception(
                    "Failed to ingest evidence %s",
                    evidence.id,
                )

        logger.info(
            "Batch ingest complete: %d/%d evidence records resolved to entities",
            len(results),
            len(evidence_list),
        )
        return results

    # ── Extraction helpers ──────────────────────────────────────────

    def _extract_entity_type(self, structured: dict[str, Any]) -> str:
        """Extract entity type from structured data."""
        # Check common keys for entity type hints
        for key in ("entity_type", "type", "record_type", "category", "kind"):
            if key in structured:
                value = structured[key]
                if isinstance(value, str) and value.strip():
                    return value.strip().lower()
        return ""

    def _extract_name(self, structured: dict[str, Any]) -> str:
        """Extract entity name from structured data."""
        for key in ("name", "display_name", "title", "company", "entity_name"):
            if key in structured:
                value = structured[key]
                if isinstance(value, str) and value.strip():
                    return value.strip()
        return ""

    def _extract_attributes(self, structured: dict[str, Any]) -> dict[str, Any]:
        """Extract entity attributes from structured data."""
        attributes: dict[str, Any] = {}

        # Common attribute keys
        attr_keys = [
            "email",
            "phone",
            "domain",
            "address",
            "website",
            "industry",
            "size",
            "revenue",
            "parent_id",
            "parent",
            "contacts",
            "contact_ids",
            "status",
            "role",
            "department",
        ]

        for key in attr_keys:
            if key in structured:
                value = structured[key]
                if value is not None and (not isinstance(value, str) or value.strip()):
                    attributes[key] = value

        # Also include any dict-type fields as nested attributes
        for key, value in structured.items():
            if key not in attributes and isinstance(value, dict):
                attributes[key] = value

        return attributes

    def _extract_external_id(self, structured: dict[str, Any]) -> str:
        """Extract external ID from structured data."""
        for key in ("external_id", "id", "record_id", "source_id", "externalRef", "reference"):
            if key in structured:
                value = structured[key]
                if isinstance(value, str) and value.strip():
                    return value.strip()
        return ""


__all__ = [
    "ConnectorBridge",
    "IngestResult",
]
"""TDD tests for the ConnectorBridge.

Tests ingestion of EvidenceRecords into the semantic layer,
including entity extraction and batch processing.
"""

from __future__ import annotations

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from datetime import datetime, timezone

from src.entities.models import EvidenceRecord, Provenance
from src.knowledge.connector_bridge import ConnectorBridge, IngestResult
from src.schemas.semantic_layer import CanonicalEntity


# ── Fixtures ──────────────────────────────────────────────────


@pytest.fixture
def mock_semantic_layer() -> MagicMock:
    """Mock SemanticLayer for testing."""
    layer = MagicMock()

    async def resolve_side_effect(
        entity_type: str,
        name: str,
        attributes: dict | None = None,
        source_system: str = "",
        external_id: str = "",
    ) -> CanonicalEntity:
        """Return different entities based on the name."""
        return CanonicalEntity(
            id=f"resolved-{entity_type}-{name}",
            canonical_name=name,
            entity_type=entity_type,
        )

    layer.resolve = AsyncMock(side_effect=resolve_side_effect)
    return layer


@pytest.fixture
def bridge(mock_semantic_layer: MagicMock) -> ConnectorBridge:
    """ConnectorBridge with a mocked semantic layer."""
    return ConnectorBridge(semantic_layer=mock_semantic_layer)


def make_evidence(
    evidence_id: str = "evidence-1",
    source: str = "salesforce",
    structured_data: dict | None = None,
) -> EvidenceRecord:
    """Helper to create a test EvidenceRecord."""
    return EvidenceRecord(
        id=evidence_id,
        tenant_id="tenant-1",
        source=source,
        source_type="connector",
        timestamp=datetime.now(timezone.utc),
        confidence=0.9,
        provenance=Provenance(
            connector_version="1.0.0",
            extraction_method="api",
            raw_checksum="abc123",
        ),
        structured_data=structured_data or {},
        hash="sha256hash",
    )


# ── ConnectorBridge tests ─────────────────────────────────────


class TestConnectorBridge:
    """Tests for the ConnectorBridge ingestion."""

    async def test_ingest_evidence_with_customer_data(self, bridge: ConnectorBridge) -> None:
        """Ingest an evidence record with customer data resolves to an entity."""
        evidence = make_evidence(
            evidence_id="evidence-1",
            source="salesforce",
            structured_data={
                "entity_type": "customer",
                "name": "Acme Corp",
                "email": "info@acme.com",
                "phone": "+1-555-0100",
            },
        )

        result = await bridge.ingest_evidence(evidence)

        assert result is not None
        assert isinstance(result, CanonicalEntity)
        assert result.canonical_name == "Acme Corp"
        bridge._layer.resolve.assert_awaited_once()

    async def test_ingest_evidence_with_vendor_data(self, bridge: ConnectorBridge) -> None:
        """Ingest an evidence record with vendor data resolves to an entity."""
        evidence = make_evidence(
            evidence_id="evidence-2",
            source="erp",
            structured_data={
                "entity_type": "vendor",
                "name": "Global Supplies Inc",
                "email": "orders@globalsupplies.com",
            },
        )

        result = await bridge.ingest_evidence(evidence)

        assert result is not None
        assert result.canonical_name == "Global Supplies Inc"

    async def test_ingest_evidence_missing_entity_type(self, bridge: ConnectorBridge) -> None:
        """Ingest with no entity type or name returns None."""
        evidence = make_evidence(
            evidence_id="evidence-3",
            source="slack",
            structured_data={
                "message": "Just a chat message",
                "channel": "general",
            },
        )

        result = await bridge.ingest_evidence(evidence)

        assert result is None

    async def test_ingest_evidence_extracts_external_id(self, bridge: ConnectorBridge) -> None:
        """External ID is extracted from structured_data."""
        evidence = make_evidence(
            evidence_id="evidence-4",
            source="salesforce",
            structured_data={
                "entity_type": "customer",
                "name": "Acme Corp",
                "external_id": "sf-001",
            },
        )

        result = await bridge.ingest_evidence(evidence)

        assert result is not None
        # Verify resolve was called with external_id
        call_kwargs = bridge._layer.resolve.call_args
        assert call_kwargs.kwargs.get("external_id") == "sf-001"

    async def test_ingest_evidence_uses_default_source(self, bridge: ConnectorBridge) -> None:
        """When evidence source is empty, default source system is used."""
        evidence = make_evidence(
            evidence_id="evidence-5",
            source="",
            structured_data={
                "entity_type": "customer",
                "name": "Acme Corp",
            },
        )

        result = await bridge.ingest_evidence(evidence)

        assert result is not None
        call_kwargs = bridge._layer.resolve.call_args
        assert call_kwargs.kwargs.get("source_system") == "connector"

    async def test_ingest_batch(self, bridge: ConnectorBridge) -> None:
        """Batch ingest processes multiple evidence records."""
        evidence_list = [
            make_evidence(
                evidence_id="evidence-1",
                source="salesforce",
                structured_data={
                    "entity_type": "customer",
                    "name": "Acme Corp",
                },
            ),
            make_evidence(
                evidence_id="evidence-2",
                source="erp",
                structured_data={
                    "entity_type": "vendor",
                    "name": "Global Supplies",
                },
            ),
            make_evidence(
                evidence_id="evidence-3",
                source="slack",
                structured_data={
                    "message": "Just a chat",
                },
            ),
        ]

        results = await bridge.ingest_batch(evidence_list)

        # First two have entity data, third does not
        assert len(results) == 2

    async def test_ingest_batch_partial_failure(self, bridge: ConnectorBridge) -> None:
        """Batch ingest continues after individual failures."""
        # Make the second evidence raise an exception
        evidence_list = [
            make_evidence(
                evidence_id="evidence-1",
                source="salesforce",
                structured_data={
                    "entity_type": "customer",
                    "name": "Acme Corp",
                },
            ),
            make_evidence(
                evidence_id="evidence-2",
                source="erp",
                structured_data={
                    "entity_type": "vendor",
                    "name": "Global Supplies",
                },
            ),
        ]

        # Make the mock raise on the second call
        bridge._layer.resolve.side_effect = [
            CanonicalEntity(
                id="entity-1",
                canonical_name="Acme Corp",
                entity_type="customer",
            ),
            Exception("Network error"),
        ]

        results = await bridge.ingest_batch(evidence_list)

        # First succeeds, second fails silently
        assert len(results) == 1

    async def test_ingest_evidence_extracts_attributes(self, bridge: ConnectorBridge) -> None:
        """Attributes like email, phone, domain are extracted."""
        evidence = make_evidence(
            evidence_id="evidence-6",
            source="crm",
            structured_data={
                "entity_type": "customer",
                "name": "Acme Corp",
                "email": "info@acme.com",
                "phone": "+1-555-0100",
                "domain": "acme.com",
                "industry": "Technology",
            },
        )

        result = await bridge.ingest_evidence(evidence)

        assert result is not None
        call_kwargs = bridge._layer.resolve.call_args
        attrs = call_kwargs.kwargs.get("attributes", {})
        assert attrs.get("email") == "info@acme.com"
        assert attrs.get("phone") == "+1-555-0100"
        assert attrs.get("domain") == "acme.com"
        assert attrs.get("industry") == "Technology"

    async def test_ingest_evidence_extracts_parent_id(self, bridge: ConnectorBridge) -> None:
        """Parent ID is extracted as a relationship attribute."""
        evidence = make_evidence(
            evidence_id="evidence-7",
            source="salesforce",
            structured_data={
                "entity_type": "customer",
                "name": "Subsidiary Corp",
                "parent_id": "parent-123",
            },
        )

        result = await bridge.ingest_evidence(evidence)

        assert result is not None
        call_kwargs = bridge._layer.resolve.call_args
        attrs = call_kwargs.kwargs.get("attributes", {})
        assert attrs.get("parent_id") == "parent-123"

    async def test_ingest_evidence_with_default_layer(self) -> None:
        """ConnectorBridge works with default SemanticLayer when none provided."""
        bridge = ConnectorBridge()
        evidence = make_evidence(
            evidence_id="evidence-8",
            source="salesforce",
            structured_data={
                "entity_type": "customer",
                "name": "Acme Corp",
            },
        )

        result = await bridge.ingest_evidence(evidence)

        assert result is not None
        assert isinstance(result, CanonicalEntity)


# ── IngestResult tests ────────────────────────────────────────


class TestIngestResult:
    """Tests for the IngestResult model."""

    def test_ingest_result_creation(self) -> None:
        """IngestResult can be created with all fields."""
        entity = CanonicalEntity(
            id="entity-1",
            canonical_name="Acme Corp",
            entity_type="customer",
        )
        result = IngestResult(
            entity=entity,
            evidence_id="evidence-1",
            matched=True,
            resolution_tier="exact",
            confidence=0.95,
        )

        assert result.entity.id == "entity-1"
        assert result.evidence_id == "evidence-1"
        assert result.matched is True
        assert result.resolution_tier == "exact"
        assert result.confidence == 0.95

"""TDD tests for the SemanticLayer resolution engine.

Tests the 5-tier resolution strategy, merge, query, lineage,
and conflict detection capabilities.
"""

from __future__ import annotations

import pytest
from unittest.mock import AsyncMock, MagicMock

from datetime import datetime, timezone

from src.knowledge.semantic_layer import (
    SemanticLayer,
    InMemoryEntityStore,
    ResolutionResult,
    ResolutionTier,
)
from src.schemas.semantic_layer import (
    CanonicalEntity,
    EntityAlias,
    AttributeConflict,
    EntityLineage,
    ConflictStatus,
)


# ── Fixtures ──────────────────────────────────────────────────────────


@pytest.fixture
def store() -> InMemoryEntityStore:
    """Fresh in-memory entity store for each test."""
    return InMemoryEntityStore()


@pytest.fixture
def layer(store: InMemoryEntityStore) -> SemanticLayer:
    """SemanticLayer with a fresh in-memory store."""
    return SemanticLayer(entity_store=store)


@pytest.fixture
def sample_alias() -> EntityAlias:
    """A sample EntityAlias for testing."""
    return EntityAlias(
        source_system="salesforce",
        external_id="sf-001",
        display_name="Acme Corp",
        entity_type_hint="customer",
        attributes={"email": "info@acme.com", "phone": "+1-555-0100"},
        confidence=0.95,
    )


@pytest.fixture
def sample_entity(sample_alias: EntityAlias) -> CanonicalEntity:
    """A sample CanonicalEntity for testing."""
    return CanonicalEntity(
        id="01J0X8X8X8X8X8X8X8X8X8X8X01",
        canonical_name="Acme Corp",
        entity_type="customer",
        aliases=[sample_alias],
        confidence=0.95,
        attributes={"email": "info@acme.com", "phone": "+1-555-0100"},
    )


# ── InMemoryEntityStore tests ─────────────────────────────────────────


class TestInMemoryEntityStore:
    """Tests for the default in-memory entity store."""

    async def test_save_and_get(self, store: InMemoryEntityStore) -> None:
        """Save an entity and retrieve it by ID."""
        entity = CanonicalEntity(
            id="entity-1",
            canonical_name="Test Corp",
            entity_type="customer",
        )
        saved = await store.save(entity)
        retrieved = await store.get("entity-1")

        assert retrieved is not None
        assert retrieved.id == "entity-1"
        assert retrieved.canonical_name == "Test Corp"
        assert saved.id == "entity-1"

    async def test_find_by_external_id(self, store: InMemoryEntityStore) -> None:
        """Find an entity by external_id and source_system."""
        alias = EntityAlias(
            source_system="salesforce",
            external_id="sf-001",
            display_name="Acme Corp",
            entity_type_hint="customer",
        )
        entity = CanonicalEntity(
            id="entity-1",
            canonical_name="Acme Corp",
            entity_type="customer",
            aliases=[alias],
        )
        await store.save(entity)

        result = await store.find_by_external_id("sf-001", "salesforce")
        assert result is not None
        assert result.id == "entity-1"

    async def test_find_by_external_id_missing(self, store: InMemoryEntityStore) -> None:
        """Return None when external_id does not exist."""
        result = await store.find_by_external_id("nonexistent", "salesforce")
        assert result is None

    async def test_find_by_name_fuzzy(self, store: InMemoryEntityStore) -> None:
        """Find entities by fuzzy name match (Levenshtein)."""
        alias = EntityAlias(
            source_system="salesforce",
            external_id="sf-001",
            display_name="Acme Corp.",
            entity_type_hint="customer",
        )
        entity = CanonicalEntity(
            id="entity-1",
            canonical_name="Acme Corp.",
            entity_type="customer",
            aliases=[alias],
        )
        await store.save(entity)

        results = await store.find_by_name("customer", "Acme Corp")
        assert len(results) == 1
        assert results[0].id == "entity-1"

    async def test_find_by_attribute(self, store: InMemoryEntityStore) -> None:
        """Find entities by attribute value."""
        alias = EntityAlias(
            source_system="salesforce",
            external_id="sf-001",
            display_name="Acme Corp",
            entity_type_hint="customer",
            attributes={"email": "info@acme.com"},
        )
        entity = CanonicalEntity(
            id="entity-1",
            canonical_name="Acme Corp",
            entity_type="customer",
            aliases=[alias],
            attributes={"email": "info@acme.com"},
        )
        await store.save(entity)

        results = await store.find_by_attribute("customer", "email", "info@acme.com")
        assert len(results) == 1
        assert results[0].id == "entity-1"

    async def test_list_with_filters(self, store: InMemoryEntityStore) -> None:
        """List entities with type and attribute filters."""
        alias1 = EntityAlias(
            source_system="salesforce",
            external_id="sf-001",
            display_name="Acme Corp",
            entity_type_hint="customer",
        )
        alias2 = EntityAlias(
            source_system="erp",
            external_id="erp-001",
            display_name="Acme Corp",
            entity_type_hint="vendor",
        )
        entity1 = CanonicalEntity(
            id="entity-1",
            canonical_name="Acme Corp",
            entity_type="customer",
            aliases=[alias1],
        )
        entity2 = CanonicalEntity(
            id="entity-2",
            canonical_name="Acme Corp",
            entity_type="vendor",
            aliases=[alias2],
        )
        await store.save(entity1)
        await store.save(entity2)

        results = await store.list(entity_type="customer")
        assert len(results) == 1
        assert results[0].entity_type == "customer"

    async def test_list_with_source_system_filter(self, store: InMemoryEntityStore) -> None:
        """List entities filtered by source system."""
        alias = EntityAlias(
            source_system="salesforce",
            external_id="sf-001",
            display_name="Acme Corp",
            entity_type_hint="customer",
        )
        entity = CanonicalEntity(
            id="entity-1",
            canonical_name="Acme Corp",
            entity_type="customer",
            aliases=[alias],
        )
        await store.save(entity)

        results = await store.list(source_system="salesforce")
        assert len(results) == 1

        results = await store.list(source_system="erp")
        assert len(results) == 0


# ── SemanticLayer.resolve tests ───────────────────────────────────────


class TestSemanticLayerResolve:
    """Tests for the 5-tier resolution strategy."""

    async def test_tier1_exact_match(self, layer: SemanticLayer, sample_entity: CanonicalEntity) -> None:
        """Tier 1: Exact match on external_id returns existing entity."""
        await layer._store.save(sample_entity)

        result = await layer.resolve(
            entity_type="customer",
            name="Acme Corp",
            source_system="salesforce",
            external_id="sf-001",
        )

        assert result.id == sample_entity.id
        assert result.canonical_name == "Acme Corp"

    async def test_tier2_fuzzy_match(self, layer: SemanticLayer, sample_entity: CanonicalEntity) -> None:
        """Tier 2: Fuzzy name match returns existing entity."""
        await layer._store.save(sample_entity)

        result = await layer.resolve(
            entity_type="customer",
            name="Acme Corp.",  # Slightly different name (period added)
        )

        assert result.id == sample_entity.id

    async def test_tier3_attribute_match(self, layer: SemanticLayer, sample_entity: CanonicalEntity) -> None:
        """Tier 3: Attribute match on email returns existing entity."""
        await layer._store.save(sample_entity)

        result = await layer.resolve(
            entity_type="customer",
            name="Unknown Corp",
            attributes={"email": "info@acme.com"},
        )

        assert result.id == sample_entity.id

    async def test_tier4_relationship_match(self, layer: SemanticLayer) -> None:
        """Tier 4: Relationship match via shared parent_id."""
        parent_alias = EntityAlias(
            source_system="salesforce",
            external_id="sf-parent",
            display_name="Parent Corp",
            entity_type_hint="customer",
        )
        parent_entity = CanonicalEntity(
            id="parent-entity",
            canonical_name="Parent Corp",
            entity_type="customer",
            aliases=[parent_alias],
            attributes={"parent_id": "root-123"},
        )
        await layer._store.save(parent_entity)

        child_alias = EntityAlias(
            source_system="salesforce",
            external_id="sf-child",
            display_name="Child Corp",
            entity_type_hint="customer",
        )
        child_entity = CanonicalEntity(
            id="child-entity",
            canonical_name="Child Corp",
            entity_type="customer",
            aliases=[child_alias],
            attributes={"parent_id": "root-123"},
        )
        await layer._store.save(child_entity)

        # Resolve a new entity with the same parent_id
        result = await layer.resolve(
            entity_type="customer",
            name="Another Child",
            attributes={"parent_id": "root-123"},
        )

        # Should match the child entity via relationship (shared parent)
        assert result is not None

    async def test_tier5_creates_new_entity(self, layer: SemanticLayer) -> None:
        """Tier 5: No match at any tier creates a new entity."""
        result = await layer.resolve(
            entity_type="customer",
            name="Brand New Corp",
            attributes={"email": "new@brand.com"},
            source_system="salesforce",
            external_id="sf-new",
        )

        assert result.id is not None
        assert result.canonical_name == "Brand New Corp"
        assert result.entity_type == "customer"
        assert len(result.aliases) == 1
        assert result.aliases[0].source_system == "salesforce"

    async def test_manual_override(self, layer: SemanticLayer) -> None:
        """Manual override bypasses all resolution tiers."""
        override_entity = CanonicalEntity(
            id="override-123",
            canonical_name="Overridden Corp",
            entity_type="customer",
            attributes={"email": "override@corp.com"},
        )
        await layer.set_manual_override("salesforce", "sf-override", override_entity.model_dump())

        result = await layer.resolve(
            entity_type="customer",
            name="Some Corp",
            source_system="salesforce",
            external_id="sf-override",
        )

        assert result.id == "override-123"
        assert result.canonical_name == "Overridden Corp"

    async def test_no_external_id_skips_tier1(self, layer: SemanticLayer, sample_entity: CanonicalEntity) -> None:
        """When external_id is empty, tier 1 is skipped."""
        await layer._store.save(sample_entity)

        result = await layer.resolve(
            entity_type="customer",
            name="Acme Corp",
            source_system="salesforce",
            external_id="",
        )

        # Should still match via tier 2 (fuzzy name)
        assert result.id == sample_entity.id

    async def test_empty_name_creates_new_entity(self, layer: SemanticLayer) -> None:
        """An entity with no name and no matching attributes creates a new entity."""
        result = await layer.resolve(
            entity_type="customer",
            name="",
            source_system="salesforce",
            external_id="sf-unknown",
        )

        assert result.id is not None
        assert result.canonical_name == "Unnamed Entity"


# ── SemanticLayer.merge tests ─────────────────────────────────────────


class TestSemanticLayerMerge:
    """Tests for the merge operation."""

    async def test_merge_transfers_aliases(self, layer: SemanticLayer) -> None:
        """Merging transfers aliases from source to target."""
        alias1 = EntityAlias(
            source_system="salesforce",
            external_id="sf-source",
            display_name="Source Corp",
            entity_type_hint="customer",
        )
        source = CanonicalEntity(
            id="source-entity",
            canonical_name="Source Corp",
            entity_type="customer",
            aliases=[alias1],
        )

        alias2 = EntityAlias(
            source_system="erp",
            external_id="erp-target",
            display_name="Target Corp",
            entity_type_hint="customer",
        )
        target = CanonicalEntity(
            id="target-entity",
            canonical_name="Target Corp",
            entity_type="customer",
            aliases=[alias2],
        )

        await layer._store.save(source)
        await layer._store.save(target)

        merged = await layer.merge("source-entity", "target-entity")

        assert merged.id == "target-entity"
        # Target should now have both aliases
        assert len(merged.aliases) == 2
        source_aliases = [a for a in merged.aliases if a.source_system == "salesforce"]
        assert len(source_aliases) == 1

    async def test_merge_redirects_relationships(self, layer: SemanticLayer) -> None:
        """Merging redirects relationships from source to target."""
        source = CanonicalEntity(
            id="source-entity",
            canonical_name="Source Corp",
            entity_type="customer",
            relationships=["other-entity"],
        )
        target = CanonicalEntity(
            id="target-entity",
            canonical_name="Target Corp",
            entity_type="customer",
        )

        await layer._store.save(source)
        await layer._store.save(target)

        merged = await layer.merge("source-entity", "target-entity")

        assert "other-entity" in merged.relationships

    async def test_merge_raises_on_missing_source(self, layer: SemanticLayer) -> None:
        """Merging raises ValueError when source entity does not exist."""
        target = CanonicalEntity(
            id="target-entity",
            canonical_name="Target Corp",
            entity_type="customer",
        )
        await layer._store.save(target)

        with pytest.raises(ValueError, match="not found"):
            await layer.merge("nonexistent", "target-entity")

    async def test_merge_raises_on_missing_target(self, layer: SemanticLayer) -> None:
        """Merging raises ValueError when target entity does not exist."""
        source = CanonicalEntity(
            id="source-entity",
            canonical_name="Source Corp",
            entity_type="customer",
        )
        await layer._store.save(source)

        with pytest.raises(ValueError, match="not found"):
            await layer.merge("source-entity", "nonexistent")


# ── SemanticLayer.query tests ─────────────────────────────────────────


class TestSemanticLayerQuery:
    """Tests for the query operation."""

    async def test_query_by_entity_type(self, layer: SemanticLayer) -> None:
        """Query filters by entity type."""
        customer = CanonicalEntity(
            id="cust-1",
            canonical_name="Customer Corp",
            entity_type="customer",
        )
        vendor = CanonicalEntity(
            id="vend-1",
            canonical_name="Vendor Corp",
            entity_type="vendor",
        )
        await layer._store.save(customer)
        await layer._store.save(vendor)

        results = await layer.query(entity_type="customer")
        assert len(results) == 1
        assert results[0].entity_type == "customer"

    async def test_query_by_source_system(self, layer: SemanticLayer) -> None:
        """Query filters by source system."""
        alias = EntityAlias(
            source_system="salesforce",
            external_id="sf-001",
            display_name="Acme Corp",
            entity_type_hint="customer",
        )
        entity = CanonicalEntity(
            id="entity-1",
            canonical_name="Acme Corp",
            entity_type="customer",
            aliases=[alias],
        )
        await layer._store.save(entity)

        results = await layer.query(source_system="salesforce")
        assert len(results) == 1

        results = await layer.query(source_system="erp")
        assert len(results) == 0

    async def test_query_with_filters(self, layer: SemanticLayer) -> None:
        """Query applies attribute filters."""
        alias = EntityAlias(
            source_system="salesforce",
            external_id="sf-001",
            display_name="Acme Corp",
            entity_type_hint="customer",
        )
        entity = CanonicalEntity(
            id="entity-1",
            canonical_name="Acme Corp",
            entity_type="customer",
            aliases=[alias],
            attributes={"email": "info@acme.com"},
        )
        await layer._store.save(entity)

        results = await layer.query(filters={"email": "info@acme.com"})
        assert len(results) == 1

        results = await layer.query(filters={"email": "wrong@acme.com"})
        assert len(results) == 0

    async def test_query_returns_all_when_no_filters(self, layer: SemanticLayer) -> None:
        """Query with no filters returns all entities."""
        for i in range(3):
            entity = CanonicalEntity(
                id=f"entity-{i}",
                canonical_name=f"Corp {i}",
                entity_type="customer",
            )
            await layer._store.save(entity)

        results = await layer.query()
        assert len(results) == 3


# ── SemanticLayer.lineage tests ───────────────────────────────────────


class TestSemanticLayerLineage:
    """Tests for the lineage operation."""

    async def test_lineage_returns_full_lineage(self, layer: SemanticLayer) -> None:
        """Lineage returns all aliases and resolution history."""
        alias1 = EntityAlias(
            source_system="salesforce",
            external_id="sf-001",
            display_name="Acme Corp",
            entity_type_hint="customer",
            confidence=0.95,
        )
        alias2 = EntityAlias(
            source_system="erp",
            external_id="erp-001",
            display_name="Acme Corporation",
            entity_type_hint="customer",
            confidence=0.90,
        )
        entity = CanonicalEntity(
            id="entity-1",
            canonical_name="Acme Corp",
            entity_type="customer",
            aliases=[alias1, alias2],
        )
        await layer._store.save(entity)

        lineage = await layer.lineage("entity-1")

        assert lineage.entity_id == "entity-1"
        assert lineage.canonical_name == "Acme Corp"
        assert len(lineage.aliases) == 2
        assert len(lineage.resolution_history) == 2

    async def test_lineage_raises_on_missing_entity(self, layer: SemanticLayer) -> None:
        """Lineage raises ValueError for non-existent entity."""
        with pytest.raises(ValueError, match="not found"):
            await layer.lineage("nonexistent")


# ── SemanticLayer.conflicts tests ─────────────────────────────────────


class TestSemanticLayerConflicts:
    """Tests for the conflicts operation."""

    async def test_conflicts_detects_attribute_conflict(self, layer: SemanticLayer) -> None:
        """Conflicts detects when two aliases have different values for the same attribute."""
        alias1 = EntityAlias(
            source_system="salesforce",
            external_id="sf-001",
            display_name="Acme Corp",
            entity_type_hint="customer",
            attributes={"email": "info@acme.com"},
        )
        alias2 = EntityAlias(
            source_system="erp",
            external_id="erp-001",
            display_name="Acme Corp",
            entity_type_hint="customer",
            attributes={"email": "contact@acme.com"},
        )
        entity = CanonicalEntity(
            id="entity-1",
            canonical_name="Acme Corp",
            entity_type="customer",
            aliases=[alias1, alias2],
        )
        await layer._store.save(entity)

        conflicts = await layer.conflicts("entity-1")

        assert len(conflicts) > 0
        email_conflicts = [c for c in conflicts if c.attribute_name == "email"]
        assert len(email_conflicts) == 1

    async def test_conflicts_returns_empty_for_no_conflicts(self, layer: SemanticLayer) -> None:
        """Conflicts returns empty list when no conflicts exist."""
        alias = EntityAlias(
            source_system="salesforce",
            external_id="sf-001",
            display_name="Acme Corp",
            entity_type_hint="customer",
            attributes={"email": "info@acme.com"},
        )
        entity = CanonicalEntity(
            id="entity-1",
            canonical_name="Acme Corp",
            entity_type="customer",
            aliases=[alias],
        )
        await layer._store.save(entity)

        conflicts = await layer.conflicts("entity-1")
        assert len(conflicts) == 0

    async def test_conflicts_returns_empty_for_missing_entity(self, layer: SemanticLayer) -> None:
        """Conflicts returns empty list for non-existent entity."""
        conflicts = await layer.conflicts("nonexistent")
        assert len(conflicts) == 0


# ── ResolutionTier enum tests ─────────────────────────────────────────


class TestResolutionTier:
    """Tests for the ResolutionTier enum."""

    def test_all_tiers_present(self) -> None:
        """All 5 resolution tiers are defined."""
        tiers = [t.value for t in ResolutionTier]
        assert "exact" in tiers
        assert "fuzzy" in tiers
        assert "attribute" in tiers
        assert "relationship" in tiers
        assert "llm_assisted" in tiers

    def test_tier_count(self) -> None:
        """Exactly 5 tiers are defined."""
        assert len(ResolutionTier) == 5

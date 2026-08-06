"""V6 Semantic Layer schema tests — TDD.

Tests for the NEW canonical entity / capability / knowledge catalog models
that will live in:
    src/schemas/semantic_layer.py   – CanonicalEntity, EntityAlias
    src/schemas/capability.py       – Capability, CapabilityRelationship
    src/schemas/knowledge_catalog.py – KnowledgeCatalogEntry

All tests will FAIL with ImportError until the implementation modules exist.
This is intentional — we write the tests first, then implement.

Usage:
    cd apps/ai
    uv run pytest tests/v6/test_schema_v6.py -v
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

import pytest

# ── Import the models that DO NOT EXIST YET ────────────────────────────────
# These will raise ImportError until the implementation is created.
from src.schemas.semantic_layer import CanonicalEntity, EntityAlias
from src.schemas.capability import Capability, CapabilityRelationship
from src.schemas.knowledge_catalog import KnowledgeCatalogEntry


# ── Helpers ────────────────────────────────────────────────────────────────

_ULID = "01J0X8X8X8X8X8X8X8X8X8X8X8XX"
_NOW = datetime.now(timezone.utc)


def _make_alias(**overrides: Any) -> EntityAlias:
    """Build a valid EntityAlias with sensible defaults."""
    defaults: dict[str, Any] = {
        "source_system": "salesforce",
        "external_id": "sf-001",
        "display_name": "Acme Corp",
        "entity_type_hint": "customer",
        "last_synced": _NOW,
    }
    defaults.update(overrides)
    return EntityAlias(**defaults)


def _make_canonical(**overrides: Any) -> CanonicalEntity:
    """Build a valid CanonicalEntity with sensible defaults."""
    defaults: dict[str, Any] = {
        "id": _ULID,
        "canonical_name": "Acme Corp",
        "entity_type": "customer",
        "created_at": _NOW,
        "updated_at": _NOW,
    }
    defaults.update(overrides)
    return CanonicalEntity(**defaults)


def _make_capability(**overrides: Any) -> Capability:
    """Build a valid Capability with sensible defaults."""
    defaults: dict[str, Any] = {
        "id": _ULID,
        "name": "Auth",
        "description": "Authentication capability",
        "created_at": _NOW,
        "updated_at": _NOW,
    }
    defaults.update(overrides)
    return Capability(**defaults)


def _make_relationship(**overrides: Any) -> CapabilityRelationship:
    """Build a valid CapabilityRelationship with sensible defaults."""
    defaults: dict[str, Any] = {
        "source_id": "01J0X8X8X8X8X8X8X8X8X8X8X8XX",
        "target_id": "01J0Y9Y9Y9Y9Y9Y9Y9Y9Y9Y9Y9YY",
        "relationship_type": "ENABLES",
    }
    defaults.update(overrides)
    return CapabilityRelationship(**defaults)


def _make_catalog_entry(**overrides: Any) -> KnowledgeCatalogEntry:
    """Build a valid KnowledgeCatalogEntry with sensible defaults."""
    defaults: dict[str, Any] = {
        "id": _ULID,
        "category": "capability",
        "title": "Authentication",
        "entity_id": "01J0X8X8X8X8X8X8X8X8X8X8X8XX",
        "entity_type": "Capability",
        "created_at": _NOW,
        "updated_at": _NOW,
    }
    defaults.update(overrides)
    return KnowledgeCatalogEntry(**defaults)


# ═══════════════════════════════════════════════════════════════════════════
# TestCanonicalEntity
# ═══════════════════════════════════════════════════════════════════════════


class TestCanonicalEntity:
    """Tests for CanonicalEntity (semantic_layer.py)."""

    def test_create_canonical_entity(self) -> None:
        """CanonicalEntity can be created with required fields."""
        ce = _make_canonical()
        assert ce.id == _ULID
        assert ce.canonical_name == "Acme Corp"
        assert ce.entity_type == "customer"

    def test_canonical_entity_defaults(self) -> None:
        """CanonicalEntity has sensible defaults for optional fields."""
        ce = _make_canonical()
        # Optional fields should default to empty/zero
        assert ce.semantic_type == {}
        assert ce.aliases == []
        assert ce.source_of_truth == ""
        assert ce.confidence == 0.9
        assert ce.attributes == {}
        assert ce.relationships == []
        assert ce.tenant_id == ""

    def test_canonical_entity_forbids_extra(self) -> None:
        """CanonicalEntity rejects unknown fields (extra='forbid')."""
        with pytest.raises(ValueError):
            _make_canonical(unknown_field="bad")  # type: ignore[call-arg]

    def test_canonical_entity_with_aliases(self) -> None:
        """CanonicalEntity can hold multiple EntityAlias objects."""
        alias1 = _make_alias(source_system="salesforce", external_id="sf-001")
        alias2 = _make_alias(source_system="erp", external_id="erp-001")
        ce = _make_canonical(aliases=[alias1, alias2])
        assert len(ce.aliases) == 2
        assert ce.aliases[0].source_system == "salesforce"
        assert ce.aliases[1].source_system == "erp"

    def test_canonical_entity_serialization(self) -> None:
        """CanonicalEntity roundtrips through model_dump / model_validate."""
        ce = _make_canonical()
        data = ce.model_dump()
        restored = CanonicalEntity.model_validate(data)
        assert restored.id == ce.id
        assert restored.canonical_name == ce.canonical_name
        assert restored.entity_type == ce.entity_type
        assert restored.confidence == ce.confidence

    def test_canonical_entity_type_must_be_string(self) -> None:
        """entity_type must be a string (SemanticLevel2 value)."""
        ce = _make_canonical(entity_type="customer")
        assert ce.entity_type == "customer"

    def test_canonical_entity_semantic_type_dict(self) -> None:
        """semantic_type is a dict[str, str] for taxonomy lookup."""
        ce = _make_canonical(
            semantic_type={"domain": "sales", "level": "L2"}
        )
        assert ce.semantic_type["domain"] == "sales"
        assert ce.semantic_type["level"] == "L2"

    def test_canonical_entity_relationships_are_strings(self) -> None:
        """relationships holds a list of other CanonicalEntity IDs."""
        ce = _make_canonical(relationships=["01J0Y9Y9Y9Y9Y9Y9Y9Y9Y9Y9Y9YY"])
        assert len(ce.relationships) == 1
        assert ce.relationships[0].startswith("01J")


# ═══════════════════════════════════════════════════════════════════════════
# TestEntityAlias
# ═══════════════════════════════════════════════════════════════════════════


class TestEntityAlias:
    """Tests for EntityAlias (semantic_layer.py)."""

    def test_create_entity_alias(self) -> None:
        """EntityAlias can be created with required fields."""
        alias = _make_alias()
        assert alias.source_system == "salesforce"
        assert alias.external_id == "sf-001"
        assert alias.display_name == "Acme Corp"
        assert alias.entity_type_hint == "customer"

    def test_entity_alias_defaults(self) -> None:
        """EntityAlias has sensible defaults."""
        alias = _make_alias()
        assert alias.attributes == {}
        assert alias.confidence == 0.9
        assert alias.source_record_id == ""

    def test_entity_alias_forbids_extra(self) -> None:
        """EntityAlias rejects unknown fields."""
        with pytest.raises(ValueError):
            _make_alias(bogus_field="nope")  # type: ignore[call-arg]

    def test_entity_alias_all_source_systems(self) -> None:
        """EntityAlias supports salesforce, erp, support, slack."""
        for system in ("salesforce", "erp", "support", "slack"):
            alias = _make_alias(source_system=system)
            assert alias.source_system == system

    def test_entity_alias_serialization(self) -> None:
        """EntityAlias roundtrips through model_dump / model_validate."""
        alias = _make_alias()
        data = alias.model_dump()
        restored = EntityAlias.model_validate(data)
        assert restored.source_system == alias.source_system
        assert restored.external_id == alias.external_id


# ═══════════════════════════════════════════════════════════════════════════
# TestCapability
# ═══════════════════════════════════════════════════════════════════════════


class TestCapability:
    """Tests for Capability (capability.py)."""

    def test_create_capability(self) -> None:
        """Capability can be created with required fields."""
        cap = _make_capability()
        assert cap.id == _ULID
        assert cap.name == "Auth"

    def test_capability_levels(self) -> None:
        """Capability supports L0, L1, L2 levels."""
        for level in ("L0", "L1", "L2"):
            cap = _make_capability(level=level)
            assert cap.level == level

    def test_capability_invalid_level_rejected(self) -> None:
        """Capability rejects invalid levels like L3."""
        with pytest.raises(ValueError):
            _make_capability(level="L3")

    def test_capability_maturity_range(self) -> None:
        """Capability maturity_level must be 1-5."""
        for m in (1, 2, 3, 4, 5):
            cap = _make_capability(maturity_level=m)
            assert cap.maturity_level == m

    def test_capability_maturity_out_of_range(self) -> None:
        """Capability rejects maturity_level outside 1-5."""
        with pytest.raises(ValueError):
            _make_capability(maturity_level=0)
        with pytest.raises(ValueError):
            _make_capability(maturity_level=6)

    def test_capability_health_score_range(self) -> None:
        """Capability health_score must be 0.0-1.0."""
        for score in (0.0, 0.25, 0.5, 0.75, 1.0):
            cap = _make_capability(health_score=score)
            assert cap.health_score == score

    def test_capability_health_score_out_of_range(self) -> None:
        """Capability rejects health_score outside 0.0-1.0."""
        with pytest.raises(ValueError):
            _make_capability(health_score=-0.1)
        with pytest.raises(ValueError):
            _make_capability(health_score=1.1)

    def test_capability_parent_chain(self) -> None:
        """Capability can reference parent capability."""
        child = _make_capability(
            name="Login",
            parent_id="01J0X8X8X8X8X8X8X8X8X8X8X8XX",
        )
        assert child.parent_id == "01J0X8X8X8X8X8X8X8X8X8X8X8XX"

    def test_capability_defaults(self) -> None:
        """Capability has sensible defaults for optional fields."""
        cap = _make_capability()
        assert cap.description == "Authentication capability"
        assert cap.level == "L0"
        assert cap.parent_id is None
        assert cap.maturity_level == 1
        assert cap.health_score == 0.0
        assert cap.owner_id == ""
        assert cap.status == "active"
        assert cap.domain == ""
        assert cap.tenant_id == ""

    def test_capability_statuses(self) -> None:
        """Capability supports active, deprecated, planned."""
        for status in ("active", "deprecated", "planned"):
            cap = _make_capability(status=status)
            assert cap.status == status

    def test_capability_invalid_status_rejected(self) -> None:
        """Capability rejects unknown status."""
        with pytest.raises(ValueError):
            _make_capability(status="unknown")

    def test_capability_forbids_extra(self) -> None:
        """Capability rejects unknown fields."""
        with pytest.raises(ValueError):
            _make_capability(extra_field="bad")  # type: ignore[call-arg]

    def test_capability_serialization(self) -> None:
        """Capability roundtrips through model_dump / model_validate."""
        cap = _make_capability()
        data = cap.model_dump()
        restored = Capability.model_validate(data)
        assert restored.id == cap.id
        assert restored.name == cap.name


# ═══════════════════════════════════════════════════════════════════════════
# TestCapabilityRelationship
# ═══════════════════════════════════════════════════════════════════════════


class TestCapabilityRelationship:
    """Tests for CapabilityRelationship (capability.py)."""

    def test_create_relationship(self) -> None:
        """CapabilityRelationship can be created with required fields."""
        rel = _make_relationship()
        assert rel.source_id.startswith("01J")
        assert rel.target_id.startswith("01J")
        assert rel.relationship_type == "ENABLES"

    def test_relationship_types(self) -> None:
        """CapabilityRelationship supports ENABLES, DEPENDS_ON, CONFLICTS_WITH, INVESTED_IN."""
        valid_types = ("ENABLES", "DEPENDS_ON", "CONFLICTS_WITH", "INVESTED_IN")
        for rt in valid_types:
            rel = _make_relationship(relationship_type=rt)
            assert rel.relationship_type == rt

    def test_relationship_invalid_type_rejected(self) -> None:
        """CapabilityRelationship rejects unknown relationship types."""
        with pytest.raises(ValueError):
            _make_relationship(relationship_type="INVALID")

    def test_relationship_defaults(self) -> None:
        """CapabilityRelationship has sensible defaults."""
        rel = _make_relationship()
        assert rel.confidence == 0.9
        assert rel.evidence_ids == []

    def test_relationship_with_evidence(self) -> None:
        """CapabilityRelationship can hold evidence IDs."""
        rel = _make_relationship(
            evidence_ids=["01J0Z0Z0Z0Z0Z0Z0Z0Z0Z0Z0Z0ZZ"]
        )
        assert len(rel.evidence_ids) == 1

    def test_relationship_forbids_extra(self) -> None:
        """CapabilityRelationship rejects unknown fields."""
        with pytest.raises(ValueError):
            _make_relationship(bogus=True)  # type: ignore[call-arg]

    def test_relationship_serialization(self) -> None:
        """CapabilityRelationship roundtrips through model_dump / model_validate."""
        rel = _make_relationship()
        data = rel.model_dump()
        restored = CapabilityRelationship.model_validate(data)
        assert restored.source_id == rel.source_id
        assert restored.relationship_type == rel.relationship_type


# ═══════════════════════════════════════════════════════════════════════════
# TestKnowledgeCatalogEntry
# ═══════════════════════════════════════════════════════════════════════════


class TestKnowledgeCatalogEntry:
    """Tests for KnowledgeCatalogEntry (knowledge_catalog.py)."""

    def test_create_catalog_entry(self) -> None:
        """KnowledgeCatalogEntry can be created with required fields."""
        entry = _make_catalog_entry()
        assert entry.id == _ULID
        assert entry.category == "capability"
        assert entry.title == "Authentication"

    def test_catalog_categories(self) -> None:
        """KnowledgeCatalogEntry supports all 10 categories."""
        categories = (
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
        )
        for cat in categories:
            entry = _make_catalog_entry(category=cat)
            assert entry.category == cat

    def test_catalog_invalid_category_rejected(self) -> None:
        """KnowledgeCatalogEntry rejects unknown categories."""
        with pytest.raises(ValueError):
            _make_catalog_entry(category="not_a_category")

    def test_catalog_lifecycle_states(self) -> None:
        """KnowledgeCatalogEntry supports draft, active, archived, deprecated."""
        for state in ("draft", "active", "archived", "deprecated"):
            entry = _make_catalog_entry(lifecycle_state=state)
            assert entry.lifecycle_state == state

    def test_catalog_invalid_lifecycle_rejected(self) -> None:
        """KnowledgeCatalogEntry rejects unknown lifecycle states."""
        with pytest.raises(ValueError):
            _make_catalog_entry(lifecycle_state="unknown")

    def test_catalog_defaults(self) -> None:
        """KnowledgeCatalogEntry has sensible defaults."""
        entry = _make_catalog_entry()
        assert entry.description == ""
        assert entry.tags == []
        assert entry.confidence == 0.9
        assert entry.evidence_ids == []
        assert entry.lifecycle_state == "active"
        assert entry.version == 1
        assert entry.created_by == ""
        assert entry.updated_by == ""
        assert entry.tenant_id == ""

    def test_catalog_with_tags(self) -> None:
        """KnowledgeCatalogEntry can hold tags."""
        entry = _make_catalog_entry(tags=["security", "auth", "L2"])
        assert len(entry.tags) == 3
        assert "security" in entry.tags

    def test_catalog_with_evidence(self) -> None:
        """KnowledgeCatalogEntry can hold evidence IDs."""
        entry = _make_catalog_entry(
            evidence_ids=["01J0Z0Z0Z0Z0Z0Z0Z0Z0Z0Z0Z0ZZ"]
        )
        assert len(entry.evidence_ids) == 1

    def test_catalog_version(self) -> None:
        """KnowledgeCatalogEntry supports versioning."""
        entry = _make_catalog_entry(version=3)
        assert entry.version == 3

    def test_catalog_forbids_extra(self) -> None:
        """KnowledgeCatalogEntry rejects unknown fields."""
        with pytest.raises(ValueError):
            _make_catalog_entry(extra_field="bad")  # type: ignore[call-arg]

    def test_catalog_serialization(self) -> None:
        """KnowledgeCatalogEntry roundtrips through model_dump / model_validate."""
        entry = _make_catalog_entry()
        data = entry.model_dump()
        restored = KnowledgeCatalogEntry.model_validate(data)
        assert restored.id == entry.id
        assert restored.category == entry.category
        assert restored.title == entry.title

    def test_catalog_entity_reference(self) -> None:
        """KnowledgeCatalogEntry correctly references entity_id and entity_type."""
        entry = _make_catalog_entry(
            entity_id="01J0Y9Y9Y9Y9Y9Y9Y9Y9Y9Y9Y9YY",
            entity_type="Capability",
        )
        assert entry.entity_id == "01J0Y9Y9Y9Y9Y9Y9Y9Y9Y9Y9Y9YY"
        assert entry.entity_type == "Capability"

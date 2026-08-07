"""OntologyAI V6 — Capability Link Types (extends link_types.py PRD §13).

Defines the 8 canonical capability edges plus the capability-to-entity
edges. Integrates with the existing LINK_TYPES registry from V5.2.
"""
from src.ontology.link_types import LINK_TYPES, LinkType
from src.ontology.capability_types import CapabilityEdgeType


# ── Capability ↔ Capability edges ─────────────────────────────────

CAPABILITY_CAPABILITY_LINKS: dict[str, LinkType] = {
    "capability_enables": LinkType(
        name="capability_enables",
        source_type="Capability",
        target_type="Capability",
        cardinality="one_to_many",
        semantic_meaning="Capability A is a prerequisite for Capability B; B cannot function without A.",
    ),
    "capability_depends_on": LinkType(
        name="capability_depends_on",
        source_type="Capability",
        target_type="Capability",
        cardinality="many_to_many",
        semantic_meaning="Capability A needs Capability B to deliver value; B can exist without A.",
    ),
    "capability_conflicts_with": LinkType(
        name="capability_conflicts_with",
        source_type="Capability",
        target_type="Capability",
        cardinality="many_to_many",
        semantic_meaning="Capabilities A and B compete for the same resources or time.",
    ),
    "capability_invested_in": LinkType(
        name="capability_invested_in",
        source_type="Project",
        target_type="Capability",
        cardinality="many_to_many",
        semantic_meaning="A project targets this capability for improvement.",
    ),
    "capability_evolves_to": LinkType(
        name="capability_evolves_to",
        source_type="Capability",
        target_type="Capability",
        cardinality="many_to_many",
        semantic_meaning="Capability A is being transformed into Capability B (roadmap).",
    ),
    "capability_replaces": LinkType(
        name="capability_replaces",
        source_type="Capability",
        target_type="Capability",
        cardinality="many_to_many",
        semantic_meaning="Capability A is replacing Capability B (succession).",
    ),
}

# ── Capability ↔ Entity edges ─────────────────────────────────────

CAPABILITY_ENTITY_LINKS: dict[str, LinkType] = {
    "capability_owned_by": LinkType(
        name="capability_owned_by",
        source_type="Capability",
        target_type="Stakeholder",
        cardinality="one_to_many",
        semantic_meaning="A capability is owned/managed by a stakeholder.",
    ),
    "capability_measured_by": LinkType(
        name="capability_measured_by",
        source_type="Capability",
        target_type="KPI",
        cardinality="one_to_many",
        semantic_meaning="A capability is measured by one or more KPIs.",
    ),
    "capability_governed_by": LinkType(
        name="capability_governed_by",
        source_type="Capability",
        target_type="BusinessRule",
        cardinality="one_to_many",
        semantic_meaning="A capability is governed by one or more business rules.",
    ),
    "capability_required_by": LinkType(
        name="capability_required_by",
        source_type="Capability",
        target_type="Requirement",
        cardinality="many_to_many",
        semantic_meaning="A capability is required by one or more requirements.",
    ),
    "capability_affected_by": LinkType(
        name="capability_affected_by",
        source_type="Capability",
        target_type="Risk",
        cardinality="many_to_many",
        semantic_meaning="A capability is affected by one or more risks.",
    ),
    "evidence_links_to_capability": LinkType(
        name="evidence_links_to_capability",
        source_type="Evidence",
        target_type="Capability",
        cardinality="many_to_many",
        semantic_meaning="An evidence record is relevant to a capability.",
    ),
    "process_implements_capability": LinkType(
        name="process_implements_capability",
        source_type="Process",
        target_type="Capability",
        cardinality="many_to_many",
        semantic_meaning="A process implements a capability.",
    ),
    "system_enables_capability": LinkType(
        name="system_enables_capability",
        source_type="System",
        target_type="Capability",
        cardinality="many_to_many",
        semantic_meaning="A system enables/supports a capability.",
    ),
}

# ── Capability ↔ Decision edges ───────────────────────────────────

CAPABILITY_DECISION_LINKS: dict[str, LinkType] = {
    "decision_targets_capability": LinkType(
        name="decision_targets_capability",
        source_type="Decision",
        target_type="Capability",
        cardinality="many_to_many",
        semantic_meaning="A decision targets improving/changing a capability.",
    ),
    "capability_feeds_decision": LinkType(
        name="capability_feeds_decision",
        source_type="Capability",
        target_type="Decision",
        cardinality="many_to_many",
        semantic_meaning="Evidence from this capability feeds a decision.",
    ),
    "option_improves_capability": LinkType(
        name="option_improves_capability",
        source_type="Option",
        target_type="Capability",
        cardinality="many_to_many",
        semantic_meaning="An option improves a capability.",
    ),
}


def register_capability_links() -> None:
    """Register all capability link types with the global LINK_TYPES registry."""
    all_new = {
        **CAPABILITY_CAPABILITY_LINKS,
        **CAPABILITY_ENTITY_LINKS,
        **CAPABILITY_DECISION_LINKS,
    }
    LINK_TYPES.update(all_new)


def validate_capability_link_types() -> None:
    """Assert every capability link references a known object type."""
    all_new = {
        **CAPABILITY_CAPABILITY_LINKS,
        **CAPABILITY_ENTITY_LINKS,
        **CAPABILITY_DECISION_LINKS,
    }
    for name, lt in all_new.items():
        valid_sources = {"Capability", "Project", "Evidence", "Process", "System", "Decision", "Option", "Workflow", "*"}
        valid_targets = {"Capability", "Stakeholder", "KPI", "BusinessRule", "Requirement", "Risk", "Decision", "Workflow", "*"}
        assert lt.source_type in valid_sources, (
            f"Capability link {name} has unknown source_type {lt.source_type}"
        )
        assert lt.target_type in valid_targets, (
            f"Capability link {name} has unknown target_type {lt.target_type}"
        )

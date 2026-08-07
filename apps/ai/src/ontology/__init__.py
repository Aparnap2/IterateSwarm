"""OntologyAI V6 — Ontology package.

Exports the canonical Object Types (V5.2) and the new Capability Ontology (V6/ADR-013).
"""

# V5.2 canonical object types
from src.ontology.object_types import OBJECT_TYPES

# V6 capability ontology (ADR-013)
from src.ontology.capability_types import (
    Capability,
    CapabilityEdgeType,
    CapabilityEvidence,
    CapabilityLevel,
    CapabilityMap,
    CapabilityRelationship,
    CapabilityScore,
    CapabilityStatus,
    HealthTier,
    MaturityLevel,
)

__all__ = [
    # V5.2
    "OBJECT_TYPES",
    # V6 Capability Ontology
    "Capability",
    "CapabilityEdgeType",
    "CapabilityEvidence",
    "CapabilityLevel",
    "CapabilityMap",
    "CapabilityRelationship",
    "CapabilityScore",
    "CapabilityStatus",
    "HealthTier",
    "MaturityLevel",
]

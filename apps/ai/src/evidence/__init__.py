"""Evidence normalization layer for OntologyAI.

Transforms raw connector snapshot data into canonical ``EvidenceRecord``
instances with structured, source-agnostic keys.

Typical usage::

    from src.evidence import normalize, EvidenceRecord, NormalizerRegistry

    registry = NormalizerRegistry()
    @registry.register("stripe")
    def normalize_stripe(raw: dict) -> EvidenceRecord: ...

    stripe_data = get_mrr_snapshot(tenant_id)
    record = registry.normalize("stripe", stripe_data)
"""

from src.evidence.models import EvidenceRecord
from src.evidence.normalizer import (
    normalize,
    register_normalizer,
    EvidenceNormalizer,
)
from src.evidence.normalizer_registry import (
    NormalizerRegistry,
    NormalizerFn,
    get_default_registry,
    register,
    normalize as normalize_via_registry,
)

__all__ = [
    "EvidenceRecord",
    "EvidenceNormalizer",
    "NormalizerFn",
    "NormalizerRegistry",
    "get_default_registry",
    "normalize",
    "normalize_via_registry",
    "register",
    "register_normalizer",
]

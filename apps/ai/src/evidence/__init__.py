"""Evidence normalization layer for OntologyAI.

Transforms raw connector snapshot data into canonical ``EvidenceRecord``
instances with structured, source-agnostic keys.

Typical usage::

    from src.evidence import normalize, EvidenceRecord

    stripe_data = get_mrr_snapshot(tenant_id)
    record = normalize(stripe_data, tenant_id=tenant_id, source="stripe")
    # record.structured_data == {"mrr": …, "total_customers": …, …}
"""

from src.evidence.models import EvidenceRecord
from src.evidence.normalizer import (
    normalize,
    register_normalizer,
    EvidenceNormalizer,
)

__all__ = [
    "EvidenceRecord",
    "normalize",
    "register_normalizer",
    "EvidenceNormalizer",
]

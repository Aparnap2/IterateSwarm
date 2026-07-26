"""Canonical ``EvidenceRecord`` model for normalized connector data."""

from datetime import datetime
from typing import Literal, Optional

from pydantic import BaseModel, Field


class EvidenceRecord(BaseModel):
    """Normalised evidence record produced by any connector.

    Every connector snapshot (Stripe, ERPNext, HubSpot, …) is normalised
    into this shape so downstream consumers (MBA, predictive, pulse, …)
    can rely on source-agnostic ``structured_data`` keys.
    """

    evidence_id: str
    tenant_id: str
    source: str  # "stripe", "erpnext", "salesforce", etc.
    source_type: Literal[
        "connector", "upload", "chat", "transcript", "webhook"
    ]
    confidence: float = Field(ge=0.0, le=1.0)
    timestamp: datetime
    extracted_at: datetime
    extraction_method: Literal[
        "connector_poll",
        "webhook",
        "llm_extraction",
        "deterministic_parse",
        "user_provided",
        "file_import",
    ]
    extractor: str  # module or agent name
    raw_content: Optional[str] = None  # original snippet or reference
    structured_data: dict = Field(
        default_factory=dict
    )  # normalized key-value data
    source_refs: list[str] = Field(default_factory=list)
    provenance: dict = Field(
        default_factory=dict
    )  # connector metadata, retry info, etc.

"""Normalizer registry and built-in connector normalizers.

Architecture
------------
Each connector may register an ``EvidenceNormalizer`` via
``register_normalizer(source, instance)``.  The module-level ``normalize()``
function dispatches to the registered normalizer, or falls back to a generic
wrapper when no specialised normalizer exists.

Adding a new normalizer
-----------------------
1. Write a class that satisfies the ``EvidenceNormalizer`` protocol.
2. Call ``register_normalizer("source_name", MyNormalizer())`` at module
   import time (or wire it in via the application initialiser).
"""

from datetime import datetime, timezone
from typing import Protocol
from uuid import uuid4

from src.evidence.models import EvidenceRecord


# ---------------------------------------------------------------------------
# Protocol
# ---------------------------------------------------------------------------


class EvidenceNormalizer(Protocol):
    """Protocol for connector-specific normalizers."""

    def can_handle(self, source: str) -> bool: ...

    def normalize(
        self, raw_data: dict, tenant_id: str, source: str
    ) -> EvidenceRecord: ...


# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------

_normalizers: dict[str, EvidenceNormalizer] = {}


def register_normalizer(source: str, normalizer: EvidenceNormalizer) -> None:
    """Register *normalizer* for the given *source* identifier."""
    _normalizers[source] = normalizer


def _generate_evidence_id() -> str:
    return f"ev_{uuid4().hex[:12]}"


def normalize(
    raw_data: dict, tenant_id: str, source: str
) -> EvidenceRecord:
    """Normalise *raw_data* from *source* into an ``EvidenceRecord``.

    Uses the registered normalizer for *source* when available; otherwise
    wraps the raw data in a generic record with default confidence (0.5).
    """
    normalizer = _normalizers.get(source)
    if normalizer is not None:
        return normalizer.normalize(raw_data, tenant_id, source)

    # Default: generic wrapper
    return EvidenceRecord(
        evidence_id=_generate_evidence_id(),
        tenant_id=tenant_id,
        source=source,
        source_type="connector",
        confidence=0.5,
        timestamp=datetime.now(timezone.utc),
        extracted_at=datetime.now(timezone.utc),
        extraction_method="connector_poll",
        extractor=source,
        structured_data=raw_data,
    )


# ---------------------------------------------------------------------------
# StripeNormalizer
# ---------------------------------------------------------------------------


class StripeNormalizer:
    """Normalises Stripe snapshot data into canonical evidence keys.

    Expected input keys (from ``get_mrr_snapshot``)::

        mrr_cents, arr_cents, active_customers,
        new_customers, churned_customers
    """

    def can_handle(self, source: str) -> bool:
        return source == "stripe"

    def normalize(
        self, raw_data: dict, tenant_id: str, source: str
    ) -> EvidenceRecord:
        structured = {
            "mrr": raw_data.get("mrr_cents", 0),
            "arr": raw_data.get("arr_cents", raw_data.get("mrr_cents", 0) * 12),
            "total_customers": raw_data.get("active_customers", 0),
            "new_customers": raw_data.get("new_customers", 0),
            "churned_customers": raw_data.get("churned_customers", 0),
            "currency": "inr",  # default; could be overridden by raw_data
        }

        # Optional churn rate
        total = raw_data.get("active_customers", 0)
        churned = raw_data.get("churned_customers", 0)
        if total and churned:
            structured["churn_rate"] = round(churned / (total + churned), 4)

        return EvidenceRecord(
            evidence_id=_generate_evidence_id(),
            tenant_id=tenant_id,
            source=source,
            source_type="connector",
            confidence=0.9,
            timestamp=datetime.now(timezone.utc),
            extracted_at=datetime.now(timezone.utc),
            extraction_method="connector_poll",
            extractor="stripe",
            structured_data=structured,
            provenance={
                "raw_keys": list(raw_data.keys()),
            },
        )


# ---------------------------------------------------------------------------
# ERPNextNormalizer
# ---------------------------------------------------------------------------


class ERPNextNormalizer:
    """Normalises ERPNext snapshot data into canonical evidence keys.

    Expected input keys (from ``get_erpnext_snapshot``)::

        support_*, execution_*, team_*, finance_*
    """

    def can_handle(self, source: str) -> bool:
        return source in ("erpnext", "erpnext_mock")

    def normalize(
        self, raw_data: dict, tenant_id: str, source: str
    ) -> EvidenceRecord:
        structured = {
            # Support
            "open_issues": raw_data.get("support_open_issues", 0),
            "unresolved_issues": raw_data.get("support_unresolved_issues", 0),
            "priority_issues": raw_data.get("support_open_priority_issues", 0),
            # Execution
            "active_projects": raw_data.get("execution_active_projects", 0),
            "overdue_tasks": raw_data.get("execution_overdue_tasks", 0),
            "milestones_total": raw_data.get("execution_milestones_total", 0),
            "milestones_completed": raw_data.get(
                "execution_milestones_completed", 0
            ),
            "avg_completion_pct": raw_data.get("execution_avg_completion", 0.0),
            # Team
            "team_size": raw_data.get("team_active_count", 0),
            "new_joinees_30d": raw_data.get("team_new_joinees_30d", 0),
            # Finance
            "unpaid_cents": raw_data.get("finance_unpaid_cents", 0),
            "overdue_cents": raw_data.get("finance_overdue_cents", 0),
            "outstanding_cents": raw_data.get(
                "finance_total_outstanding_cents", 0
            ),
        }

        # Derive milestone completion ratio
        total_m = raw_data.get("execution_milestones_total", 0)
        done_m = raw_data.get("execution_milestones_completed", 0)
        if total_m:
            structured["milestone_completion_ratio"] = round(done_m / total_m, 4)

        return EvidenceRecord(
            evidence_id=_generate_evidence_id(),
            tenant_id=tenant_id,
            source=source,
            source_type="connector",
            confidence=0.85,
            timestamp=datetime.now(timezone.utc),
            extracted_at=datetime.now(timezone.utc),
            extraction_method="connector_poll",
            extractor="erpnext",
            structured_data=structured,
            provenance={
                "raw_keys": list(raw_data.keys()),
            },
        )


# ---------------------------------------------------------------------------
# Register built-in normalizers at import time
# ---------------------------------------------------------------------------

register_normalizer("stripe", StripeNormalizer())
register_normalizer("stripe_mock", StripeNormalizer())
register_normalizer("erpnext", ERPNextNormalizer())
register_normalizer("erpnext_mock", ERPNextNormalizer())

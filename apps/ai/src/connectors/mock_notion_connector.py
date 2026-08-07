"""Mock Notion connector for V6 vertical slice testing.

Implements the ``V6Connector`` Protocol (defined in
``src.connectors.v6_contract``) and returns three hardcoded evidence
records simulating a Notion workspace about customer onboarding
improvement.

.. note::

    The ULID constants (``EVIDENCE_INTERVIEW_ID``, ``EVIDENCE_PROCESS_ID``,
    ``EVIDENCE_KPI_ID``) that were originally here have been moved to
    :mod:`src.connectors._test_constants` so they can be imported by
    test code without pulling in the full connector module.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone

from src.connectors._test_constants import (
    EVIDENCE_INTERVIEW_ID,
    EVIDENCE_KPI_ID,
    EVIDENCE_PROCESS_ID,
)
from src.connectors.v6_contract import (
    ConnectorCapability,
    ConnectorManifest,
    SyncStrategy,
)
from src.entities.models import EvidenceRecord, Provenance

logger = logging.getLogger(__name__)

_WORKSPACE_TENANT = "tenant-v6-test"


def _make_provenance() -> Provenance:
    """Return canned provenance for mock connectors."""
    return Provenance(
        connector_version="0.6.0",
        extraction_method="api",
        raw_checksum="a" * 64,  # placeholder SHA256
        retry_count=0,
    )


def _interview_evidence() -> EvidenceRecord:
    """Evidence 1: Customer interview excerpt about slow onboarding."""
    return EvidenceRecord(
        id=EVIDENCE_INTERVIEW_ID,
        tenant_id=_WORKSPACE_TENANT,
        source="mock_notion",
        source_type="connector",
        timestamp=datetime(2026, 7, 20, 14, 30, 0, tzinfo=timezone.utc),
        confidence=0.92,
        provenance=_make_provenance(),
        structured_data={
            "record_type": "page",
            "external_id": "notion-page-cust-int-001",
            "external_url": "https://notion.so/customer-interview-001",
            "title": "Customer Interview \u2014 Onboarding Feedback",
            "topic": "Onboarding process pain points",
            "key_quotes": [
                "It took us over three weeks to get our first user live",
                "The approval steps are completely manual and opaque",
                "We almost churned because of the onboarding delay",
            ],
            "sentiment": "frustrated",
            "stakeholder_refs": [
                {
                    "name": "Sarah Chen",
                    "role": "Head of Product",
                    "email": "sarah@example.com",
                },
            ],
        },
        source_refs=["notion://pages/cust-int-001"],
        hash="a" * 64,
    )


def _process_evidence() -> EvidenceRecord:
    """Evidence 2: Current onboarding process documentation."""
    return EvidenceRecord(
        id=EVIDENCE_PROCESS_ID,
        tenant_id=_WORKSPACE_TENANT,
        source="mock_notion",
        source_type="connector",
        timestamp=datetime(2026, 7, 18, 9, 15, 0, tzinfo=timezone.utc),
        confidence=0.95,
        provenance=_make_provenance(),
        structured_data={
            "record_type": "database",
            "external_id": "notion-db-onboarding-v2",
            "external_url": "https://notion.so/onboarding-process-v2",
            "title": "Current Onboarding Process \u2014 Stage Gate Flow",
            "process_steps": [
                "Account creation (day 1)",
                "Email verification (day 1-2)",
                "Manager approves access (day 3-7, manual)",
                "IT provisions tools (day 5-10, manual)",
                "Onboarding training session (day 10-14)",
                "First project assignment (day 14-21)",
            ],
            "duration_days": 21,
            "bottleneck": "Manager approval step is manual, averages 4.5 days",
            "responsible_team": "People Operations",
            "automation_candidates": [
                "Manager approval via Slack workflow",
                "IT provisioning via Okta SCIM",
            ],
        },
        source_refs=["notion://databases/onboarding-v2"],
        hash="b" * 64,
    )


def _kpi_evidence() -> EvidenceRecord:
    """Evidence 3: KPI spreadsheet showing 40% user drop-off during onboarding."""
    return EvidenceRecord(
        id=EVIDENCE_KPI_ID,
        tenant_id=_WORKSPACE_TENANT,
        source="mock_notion",
        source_type="connector",
        timestamp=datetime(2026, 7, 22, 11, 0, 0, tzinfo=timezone.utc),
        confidence=0.96,
        provenance=_make_provenance(),
        structured_data={
            "record_type": "database",
            "external_id": "notion-db-kpi-dashboard",
            "external_url": "https://notion.so/kpi-dashboard-q3",
            "title": "Q3 Onboarding KPIs",
            "metric_name": "User drop-off rate during onboarding",
            "current_value": 40.0,
            "target_value": 15.0,
            "unit": "percent",
            "trend": "increasing",
            "measurement_period": "Q3 2026",
            "stakeholder_refs": [
                {
                    "name": "Mike Liu",
                    "role": "Analytics",
                    "email": "mike@example.com",
                },
            ],
        },
        source_refs=["notion://databases/kpi-dashboard"],
        hash="c" * 64,
    )


# ── Connector ────────────────────────────────────────────────────────────


class MockNotionConnector:
    """Mock Notion connector for vertical slice testing.

    Returns 3 hardcoded evidence records simulating a Notion workspace
    about customer onboarding improvement.  Implements the
    ``V6Connector`` protocol (duck-typed \u2014 no explicit inheritance).
    """

    async def connect(self) -> ConnectorManifest:
        """Return a manifest describing this mock connector."""
        return ConnectorManifest(
            name="mock_notion",
            version="0.6.0",
            capabilities=[ConnectorCapability.DOCUMENTATION],
            supported_objects=["pages", "databases"],
            sync_strategy=SyncStrategy.POLLING,
            supports_webhook=False,
            supports_polling=True,
            rate_limit_per_minute=100,
            auth_type="mock",
            supports_incremental_sync=True,
            deletion_strategy="ignore",
        )

    async def fetch(
        self,
        since: datetime | None = None,  # noqa: ARG002
    ) -> list[EvidenceRecord]:
        """Return the three hardcoded evidence records.

        Parameters
        ----------
        since:
            Ignored in mock \u2014 always returns all three records.
        """
        logger.info("MockNotionConnector.fetch() \u2014 returning 3 evidence records")
        return [
            _interview_evidence(),
            _process_evidence(),
            _kpi_evidence(),
        ]

    async def health(self) -> dict:
        """Return connector health status."""
        return {
            "status": "ok",
            "latency_ms": 5,
            "connector": "mock_notion",
        }

    async def close(self) -> None:
        """No-op for mock connector."""
        return None

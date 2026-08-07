"""Shared test data for the V6 vertical slice.

Reusable fixtures used by all vertical-slice test cases.  Each
evidence record, entity, and expected output is defined once here
so test files can import what they need.
"""

from datetime import datetime, timezone

from src.connectors._test_constants import (
    EVIDENCE_INTERVIEW_ID,
    EVIDENCE_KPI_ID,
    EVIDENCE_PROCESS_ID,
)
from src.entities.models import EvidenceRecord, Provenance

# ── Identifiers ──────────────────────────────────────────────────────────

WORKSPACE_ID = "01J0X8X8X8X8X8X8X8X8X8X8X8WS"
TENANT_ID = "tenant-v6-test"

# Fixed entity ULIDs (must match entity_resolver.py)
ENTITY_SARAH_ID = "01J0X8X8X8X8X8X8X8X8X8X8X8SA"
ENTITY_REQUIREMENT_ID = "01J0X8X8X8X8X8X8X8X8X8X8X8RE"
ENTITY_MIKE_ID = "01J0X8X8X8X8X8X8X8X8X8X8X8MI"
ENTITY_KPI_ID = "01J0X8X8X8X8X8X8X8X8X8X8X8KP"

# ── Provenance helper ────────────────────────────────────────────────────

_BASE_PROVENANCE = Provenance(
    connector_version="0.6.0",
    extraction_method="api",
    raw_checksum="a" * 64,
    retry_count=0,
)

# ── Evidence 1: Customer interview ───────────────────────────────────────

CUSTOMER_INTERVIEW_EVIDENCE = EvidenceRecord(
    id=EVIDENCE_INTERVIEW_ID,
    tenant_id=TENANT_ID,
    source="mock_notion",
    source_type="connector",
    timestamp=datetime(2026, 7, 20, 14, 30, 0, tzinfo=timezone.utc),
    confidence=0.92,
    provenance=_BASE_PROVENANCE,
    structured_data={
        "record_type": "page",
        "external_id": "notion-page-cust-int-001",
        "external_url": "https://notion.so/customer-interview-001",
        "title": "Customer Interview — Onboarding Feedback",
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

# ── Evidence 2: Process documentation ────────────────────────────────────

PROCESS_DOC_EVIDENCE = EvidenceRecord(
    id=EVIDENCE_PROCESS_ID,
    tenant_id=TENANT_ID,
    source="mock_notion",
    source_type="connector",
    timestamp=datetime(2026, 7, 18, 9, 15, 0, tzinfo=timezone.utc),
    confidence=0.95,
    provenance=_BASE_PROVENANCE,
    structured_data={
        "record_type": "database",
        "external_id": "notion-db-onboarding-v2",
        "external_url": "https://notion.so/onboarding-process-v2",
        "title": "Current Onboarding Process — Stage Gate Flow",
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

# ── Evidence 3: KPI spreadsheet ──────────────────────────────────────────

KPI_EVIDENCE = EvidenceRecord(
    id=EVIDENCE_KPI_ID,
    tenant_id=TENANT_ID,
    source="mock_notion",
    source_type="connector",
    timestamp=datetime(2026, 7, 22, 11, 0, 0, tzinfo=timezone.utc),
    confidence=0.96,
    provenance=_BASE_PROVENANCE,
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
            {"name": "Mike Liu", "role": "Analytics", "email": "mike@example.com"},
        ],
    },
    source_refs=["notion://databases/kpi-dashboard"],
    hash="c" * 64,
)

# ── All evidence ─────────────────────────────────────────────────────────

ALL_EVIDENCE = [
    CUSTOMER_INTERVIEW_EVIDENCE,
    PROCESS_DOC_EVIDENCE,
    KPI_EVIDENCE,
]

# ── Expected entities after resolution ───────────────────────────────────

EXPECTED_ENTITIES = [
    {"type": "Stakeholder", "name": "Sarah Chen", "role": "Head of Product"},
    {"type": "Stakeholder", "name": "Mike Liu", "role": "Analytics"},
    {"type": "Requirement", "name": "Automate onboarding approvals"},
    {"type": "KPI", "name": "User drop-off rate during onboarding"},
]

# ── Expected entity IDs after resolution ─────────────────────────────────

EXPECTED_ENTITY_IDS = {
    "Sarah Chen": ENTITY_SARAH_ID,
    "Mike Liu": ENTITY_MIKE_ID,
    "Automate onboarding approvals": ENTITY_REQUIREMENT_ID,
    "User drop-off rate during onboarding": ENTITY_KPI_ID,
}

# ── Expected feasibility dimensions ──────────────────────────────────────

EXPECTED_FEASIBILITY_DIMENSIONS = [
    "business_value",
    "technical_complexity",
    "operational_fit",
    "financial_impact",
    "compliance_risk",
    "data_readiness",
    "change_effort",
    "stakeholder_alignment",
]

# ── Expected artifact content fields ─────────────────────────────────────

EXPECTED_ARTIFACT_SECTIONS = [
    "Header",
    "Executive Summary",
    "Key Evidence",
    "Active Decisions",
    "Recommendations",
    "Risk Assessment",
    "Downstream Impact",
]

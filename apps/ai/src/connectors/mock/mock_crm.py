"""
Mock CRM Connector — returns seed data without network calls.

Activated by setting ``config.mock_mode = True`` on a :class:`ConnectorConfig`
or by requesting capability ``"crm_mock"`` from the registry.

Provides three realistic customers, opportunities, and deals for development
and integration testing.
"""

from __future__ import annotations

import logging
from typing import Any

from ..base import ConnectorConfig
from ..crm import CRMConnector

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Realistic mock seed data
# ---------------------------------------------------------------------------

_MOCK_CUSTOMERS: list[dict[str, Any]] = [
    {
        "id": "cus_mock_001",
        "name": "Acme Corp",
        "email": "billing@acme.com",
        "status": "active",
        "created_at": "2025-11-15T08:30:00Z",
    },
    {
        "id": "cus_mock_002",
        "name": "Globex Inc",
        "email": "sales@globex.io",
        "status": "churned",
        "created_at": "2024-03-01T10:00:00Z",
    },
    {
        "id": "cus_mock_003",
        "name": "Initech",
        "email": "info@initech.co",
        "status": "lead",
        "created_at": "2026-07-10T14:22:00Z",
    },
]

_MOCK_OPPORTUNITIES: list[dict[str, Any]] = [
    {
        "id": "opp_mock_001",
        "name": "Acme - Q3 Platform Expansion",
        "value_cents": 75000000,
        "stage": "negotiation",
        "close_date": "2026-09-30",
    },
    {
        "id": "opp_mock_002",
        "name": "Globex - Enterprise Suite",
        "value_cents": 120000000,
        "stage": "proposal",
        "close_date": "2026-12-15",
    },
    {
        "id": "opp_mock_003",
        "name": "Initech - Pilot Program",
        "value_cents": 5000000,
        "stage": "discovery",
        "close_date": "2026-08-01",
    },
]

_MOCK_DEALS: list[dict[str, Any]] = [
    {
        "id": "deal_mock_001",
        "name": "Acme - Annual Subscription",
        "amount_cents": 12000000,
        "status": "closed_won",
        "closed_at": "2026-06-15T00:00:00Z",
    },
    {
        "id": "deal_mock_002",
        "name": "Globex - Consulting Engagement",
        "amount_cents": 8500000,
        "status": "closed_won",
        "closed_at": "2026-07-20T00:00:00Z",
    },
    {
        "id": "deal_mock_003",
        "name": "Umbrella Corp - Renewal",
        "amount_cents": 15000000,
        "status": "closed_lost",
        "closed_at": "2026-05-20T00:00:00Z",
    },
]


class MockCRMConnector(CRMConnector):
    """CRM connector that returns realistic seed data with zero network calls.

    Parameters
    ----------
    config: ConnectorConfig
        The ``mock_mode`` flag is ignored — this connector is *always* mock.

    Usage::

        config = ConnectorConfig(tenant_id="test", mock_mode=True)
        crm = MockCRMConnector(config)
        customers = crm.get_customers()
    """

    def __init__(self, config: ConnectorConfig) -> None:
        super().__init__(config)
        self.config.mock_mode = True  # always mock

    def name(self) -> str:
        return "mock_crm"

    # ------------------------------------------------------------------
    # Health
    # ------------------------------------------------------------------

    def health(self) -> dict[str, Any]:
        return {"status": "ok", "latency_ms": 5, "mock": True, "source": "mock_crm"}

    # ------------------------------------------------------------------
    # CRM methods
    # ------------------------------------------------------------------

    def get_customers(self) -> list[dict[str, Any]]:
        return [self._add_metadata(c, "mock_crm") for c in _MOCK_CUSTOMERS]

    def get_opportunities(self) -> list[dict[str, Any]]:
        return [self._add_metadata(o, "mock_crm") for o in _MOCK_OPPORTUNITIES]

    def get_deals(self) -> list[dict[str, Any]]:
        return [self._add_metadata(d, "mock_crm") for d in _MOCK_DEALS]

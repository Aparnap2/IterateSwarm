"""
Salesforce CRM Connector — capability implementation of :class:`CRMConnector`.

Provides customer, opportunity, and deal data from Salesforce.  Supports
mock mode for development via ``config.mock_mode``.

Environment Variables (production mode):
    SALESFORCE_INSTANCE_URL: Salesforce instance URL
    SALESFORCE_CLIENT_ID: OAuth2 client ID
    SALESFORCE_CLIENT_SECRET: OAuth2 client secret
    SALESFORCE_USERNAME: Username for password grant
    SALESFORCE_PASSWORD: Password for password grant
    SALESFORCE_ACCESS_TOKEN: Direct bearer token (bypasses OAuth2 flow)
"""

from __future__ import annotations

import logging
import os
from datetime import datetime, timezone
from typing import Any

from .base import Connector, ConnectorConfig
from .crm import CRMConnector
from ..integrations.retry import circuit_breaker

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Realistic mock seed data
# ---------------------------------------------------------------------------

_MOCK_CUSTOMERS: list[dict[str, Any]] = [
    {"id": "001", "name": "Acme Corporation", "email": "info@acme.com", "status": "active"},
    {"id": "002", "name": "Globex Inc.", "email": "contact@globex.io", "status": "active"},
    {"id": "003", "name": "Initech", "email": "billing@initech.co", "status": "active"},
    {"id": "004", "name": "Umbrella Corp", "email": "admin@umbrella.org", "status": "inactive"},
    {"id": "005", "name": "Stark Industries", "email": "partners@stark.com", "status": "active"},
]

_MOCK_OPPORTUNITIES: list[dict[str, Any]] = [
    {"id": "opp_001", "name": "Acme - Q3 Platform", "stage": "negotiation",
     "amount_cents": 50000000, "probability_pct": 60},
    {"id": "opp_002", "name": "Globex - Enterprise Suite", "stage": "proposal",
     "amount_cents": 120000000, "probability_pct": 40},
    {"id": "opp_003", "name": "Stark - AI Add-on", "stage": "discovery",
     "amount_cents": 8000000, "probability_pct": 20},
]

_MOCK_DEALS: list[dict[str, Any]] = [
    {"id": "deal_001", "name": "Acme - Platform Subscription",
     "amount_cents": 12000000, "stage": "closed_won", "closed_at": "2026-06-15"},
    {"id": "deal_002", "name": "Initech - Pilot Program",
     "amount_cents": 3000000, "stage": "closed_won", "closed_at": "2026-07-01"},
    {"id": "deal_003", "name": "Umbrella - Renewal",
     "amount_cents": 15000000, "stage": "closed_lost", "closed_at": "2026-05-20"},
]


class SalesforceConnector(CRMConnector):
    """Salesforce CRM connector.

    Parameters
    ----------
    config: ConnectorConfig
        If ``config.mock_mode`` is *True* or no Salesforce credentials are
        found, returns realistic seed data.

    Usage::

        config = ConnectorConfig(tenant_id="startup_abc", mock_mode=True)
        sf = SalesforceConnector(config)
        customers = sf.get_customers()
        opportunities = sf.get_opportunities()
    """

    def __init__(self, config: ConnectorConfig) -> None:
        super().__init__(config)
        self._instance_url = config.credentials.get(
            "instance_url", os.getenv("SALESFORCE_INSTANCE_URL", "")
        )
        self._access_token = config.credentials.get(
            "access_token", os.getenv("SALESFORCE_ACCESS_TOKEN", "")
        )
        # Auto-enable mock when no credentials are configured
        if not self._has_credentials():
            logger.info(
                "SalesforceConnector[%s]: no credentials found, enabling mock mode",
                config.tenant_id,
            )
            self.config.mock_mode = True

    def name(self) -> str:
        return "salesforce"

    # ------------------------------------------------------------------
    # Health
    # ------------------------------------------------------------------

    @circuit_breaker("salesforce")
    def health(self) -> dict[str, Any]:
        if self.config.mock_mode:
            return {"status": "ok", "latency_ms": 0, "source": "salesforce_mock"}

        import time
        import httpx

        start = time.monotonic()
        try:
            resp = httpx.get(
                f"{self._instance_url}/services/data/v58.0/limits",
                headers={"Authorization": f"Bearer {self._access_token}"},
                timeout=10.0,
            )
            resp.raise_for_status()
            elapsed = int((time.monotonic() - start) * 1000)
            return {"status": "ok", "latency_ms": elapsed, "source": "salesforce"}
        except Exception as exc:
            elapsed = int((time.monotonic() - start) * 1000)
            logger.warning("Salesforce health check failed: %s", exc)
            return {"status": "down", "latency_ms": elapsed, "error": str(exc)}

    # ------------------------------------------------------------------
    # CRM methods
    # ------------------------------------------------------------------

    def get_customers(self) -> list[dict[str, Any]]:
        if self.config.mock_mode:
            return [
                self._add_metadata(c, "salesforce_mock")
                for c in _MOCK_CUSTOMERS
            ]

        try:
            return self._fetch_all("/services/data/v58.0/query", _build_customer_query())
        except Exception as exc:
            logger.error("Salesforce get_customers failed: %s", exc)
            return [self._error_result("salesforce", error=str(exc))]

    def get_opportunities(self) -> list[dict[str, Any]]:
        if self.config.mock_mode:
            return [
                self._add_metadata(o, "salesforce_mock")
                for o in _MOCK_OPPORTUNITIES
            ]

        try:
            return self._fetch_all("/services/data/v58.0/query", _build_opportunity_query())
        except Exception as exc:
            logger.error("Salesforce get_opportunities failed: %s", exc)
            return [self._error_result("salesforce", error=str(exc))]

    def get_deals(self) -> list[dict[str, Any]]:
        if self.config.mock_mode:
            return [
                self._add_metadata(d, "salesforce_mock")
                for d in _MOCK_DEALS
            ]

        try:
            return self._fetch_all("/services/data/v58.0/query", _build_deal_query())
        except Exception as exc:
            logger.error("Salesforce get_deals failed: %s", exc)
            return [self._error_result("salesforce", error=str(exc))]

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _has_credentials(self) -> bool:
        return bool(self._instance_url and self._access_token)

    @circuit_breaker("salesforce_query")
    def _run_soql(self, soql: str) -> list[dict[str, Any]]:
        """Execute a SOQL query and return all records (handles pagination)."""
        import httpx

        url = f"{self._instance_url}/services/data/v58.0/query"
        params: dict[str, str] = {"q": soql}
        headers = {"Authorization": f"Bearer {self._access_token}"}
        records: list[dict[str, Any]] = []

        while url:
            resp = httpx.get(url, params=params if url == f"{self._instance_url}/services/data/v58.0/query" else None,
                             headers=headers, timeout=30.0)
            resp.raise_for_status()
            data = resp.json()
            records.extend(data.get("records", []))
            url = data.get("nextRecordsUrl")

        return records

    def _fetch_all(self, path: str, soql: str) -> list[dict[str, Any]]:
        raw = self._run_soql(soql)
        return [self._add_metadata(self._clean(r), "salesforce") for r in raw]

    @staticmethod
    def _clean(record: dict[str, Any]) -> dict[str, Any]:
        """Strip Salesforce system attributes from a record."""
        return {k: v for k, v in record.items() if not k.startswith("attributes")}


# ---------------------------------------------------------------------------
# SOQL query builders
# ---------------------------------------------------------------------------


def _build_customer_query() -> str:
    return (
        "SELECT Id, Name, Email__c, Status__c, Type "
        "FROM Account "
        "WHERE Status__c = 'active' "
        "ORDER BY CreatedDate DESC "
        "LIMIT 500"
    )


def _build_opportunity_query() -> str:
    return (
        "SELECT Id, Name, StageName, Amount, Probability "
        "FROM Opportunity "
        "WHERE IsClosed = false "
        "ORDER BY CreatedDate DESC "
        "LIMIT 500"
    )


def _build_deal_query() -> str:
    return (
        "SELECT Id, Name, Amount, StageName, CloseDate "
        "FROM Opportunity "
        "WHERE IsClosed = true "
        "ORDER BY CloseDate DESC "
        "LIMIT 500"
    )

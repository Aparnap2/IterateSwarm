"""
QuickBooks Online Accounting Connector — capability implementation of
:class:`AccountingConnector`.

Provides invoice and transaction data from QuickBooks Online via the
QuickBooks REST API v3.  Supports mock mode for development.

Environment Variables (production mode):
    QUICKBOOKS_CLIENT_ID: QuickBooks OAuth2 client ID
    QUICKBOOKS_ACCESS_TOKEN: QuickBooks OAuth2 access token
    QUICKBOOKS_COMPANY_ID: QuickBooks company / realm ID
    QUICKBOOKS_API_URL: Base URL (default: ``https://quickbooks.api.intuit.com``)
"""

from __future__ import annotations

import logging
import os
from datetime import datetime, timedelta
from typing import Any

import httpx

from .accounting import AccountingConnector
from .base import ConnectorConfig
from ..integrations.retry import circuit_breaker

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Mock seed data
# ---------------------------------------------------------------------------

_MOCK_INVOICES: list[dict[str, Any]] = [
    {
        "id": "QB-INV-001",
        "customer": "Acme Corp",
        "total_cents": 1500000,
        "balance_cents": 500000,
        "status": "unpaid",
        "due_date": "2026-08-15",
    },
    {
        "id": "QB-INV-002",
        "customer": "Globex Inc",
        "total_cents": 3200000,
        "balance_cents": 0,
        "status": "paid",
        "due_date": "2026-07-01",
    },
    {
        "id": "QB-INV-003",
        "customer": "Initech",
        "total_cents": 850000,
        "balance_cents": 850000,
        "status": "overdue",
        "due_date": "2026-06-15",
    },
    {
        "id": "QB-INV-004",
        "customer": "Stark Industries",
        "total_cents": 5000000,
        "balance_cents": 2500000,
        "status": "partly_paid",
        "due_date": "2026-08-01",
    },
]

_MOCK_TRANSACTIONS: list[dict[str, Any]] = [
    {
        "id": "QB-TXN-001",
        "description": "Platform subscription - Acme Corp",
        "amount_cents": 1250000,
        "type": "income",
        "date": "2026-07-20",
    },
    {
        "id": "QB-TXN-002",
        "description": "Cloud infrastructure - AWS",
        "amount_cents": -450000,
        "type": "expense",
        "date": "2026-07-19",
    },
    {
        "id": "QB-TXN-003",
        "description": "Consulting - Globex Inc",
        "amount_cents": 800000,
        "type": "income",
        "date": "2026-07-18",
    },
]


class QuickBooksConnector(AccountingConnector):
    """QuickBooks Online accounting connector.

    Parameters
    ----------
    config: ConnectorConfig
        If ``config.mock_mode`` is *True* or QuickBooks credentials are not
        fully configured, returns realistic seed data.

    Usage::

        config = ConnectorConfig(tenant_id="startup_abc", mock_mode=True)
        qb = QuickBooksConnector(config)
        invoices = qb.get_invoices()
    """

    def __init__(self, config: ConnectorConfig) -> None:
        super().__init__(config)
        self._client_id = config.credentials.get(
            "client_id", os.getenv("QUICKBOOKS_CLIENT_ID", "")
        )
        self._access_token = config.credentials.get(
            "access_token", os.getenv("QUICKBOOKS_ACCESS_TOKEN", "")
        )
        self._company_id = config.credentials.get(
            "company_id", os.getenv("QUICKBOOKS_COMPANY_ID", "")
        )
        self._api_url = config.credentials.get(
            "api_url",
            os.getenv("QUICKBOOKS_API_URL", "https://quickbooks.api.intuit.com"),
        )
        # Auto-enable mock when credentials are missing
        if not self._has_credentials():
            logger.info(
                "QuickBooksConnector[%s]: no credentials, enabling mock mode",
                config.tenant_id,
            )
            self.config.mock_mode = True

    def name(self) -> str:
        return "quickbooks"

    # ------------------------------------------------------------------
    # Health
    # ------------------------------------------------------------------

    @circuit_breaker("quickbooks")
    def health(self) -> dict[str, Any]:
        if self.config.mock_mode:
            return {"status": "ok", "latency_ms": 0, "source": "quickbooks_mock"}

        import time

        start = time.monotonic()
        try:
            resp = httpx.get(
                f"{self._api_url}/v3/company/{self._company_id}/companyinfo/{self._company_id}",
                headers=self._headers(),
                timeout=10.0,
            )
            resp.raise_for_status()
            elapsed = int((time.monotonic() - start) * 1000)
            return {"status": "ok", "latency_ms": elapsed, "source": "quickbooks"}
        except Exception as exc:
            elapsed = int((time.monotonic() - start) * 1000)
            logger.warning("QuickBooks health check failed: %s", exc)
            return {"status": "down", "latency_ms": elapsed, "error": str(exc)}

    # ------------------------------------------------------------------
    # Accounting methods
    # ------------------------------------------------------------------

    def get_invoices(self) -> list[dict[str, Any]]:
        if self.config.mock_mode:
            return [self._add_metadata(inv, "quickbooks_mock") for inv in _MOCK_INVOICES]

        try:
            raw = self._run_query("select * from Invoice STARTPOSITION 1 MAXRESULTS 1000")
            invoices = []
            for inv in raw.get("QueryResponse", {}).get("Invoice", []):
                invoices.append(self._add_metadata({
                    "id": inv.get("Id", ""),
                    "customer": inv.get("CustomerRef", {}).get("name", ""),
                    "total_cents": self._parse_amount(inv.get("TotalAmt")),
                    "balance_cents": self._parse_amount(inv.get("Balance")),
                    "status": self._resolve_invoice_status(inv),
                    "due_date": (inv.get("DueDate", "") or "")[:10],
                }, "quickbooks"))
            return invoices
        except Exception as exc:
            logger.error("QuickBooks get_invoices failed: %s", exc)
            return [self._error_result("quickbooks", error=str(exc))]

    def get_transactions(self) -> list[dict[str, Any]]:
        if self.config.mock_mode:
            return [self._add_metadata(txn, "quickbooks_mock") for txn in _MOCK_TRANSACTIONS]

        try:
            # Pull recent transactions from the JournalEntry and Purchase endpoints
            raw = self._run_query(
                "select * from JournalEntry STARTPOSITION 1 MAXRESULTS 200"
            )
            transactions = []
            for entry in raw.get("QueryResponse", {}).get("JournalEntry", []):
                txn_date = (entry.get("TxnDate", "") or "")[:10]
                # Try to derive a meaningful description
                desc = entry.get("PrivateNote", "") or f"Journal Entry {entry.get('Id', '')}"
                total = self._parse_amount(entry.get("TotalAmt", 0))
                transactions.append(self._add_metadata({
                    "id": entry.get("Id", ""),
                    "description": desc,
                    "amount_cents": total,
                    "type": "income" if total >= 0 else "expense",
                    "date": txn_date,
                }, "quickbooks"))
            return transactions
        except Exception as exc:
            logger.error("QuickBooks get_transactions failed: %s", exc)
            return [self._error_result("quickbooks", error=str(exc))]

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _has_credentials(self) -> bool:
        return bool(self._client_id and self._access_token and self._company_id)

    def _headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self._access_token}",
            "Accept": "application/json",
            "Content-Type": "application/text",
        }

    @circuit_breaker("quickbooks_query")
    def _run_query(self, query: str) -> dict[str, Any]:
        url = f"{self._api_url}/v3/company/{self._company_id}/query"
        params = {"query": query}
        resp = httpx.get(url, params=params, headers=self._headers(), timeout=30.0)
        resp.raise_for_status()
        return resp.json()

    @staticmethod
    def _parse_amount(value: Any) -> int:
        if value is None:
            return 0
        try:
            return int(float(value) * 100)
        except (ValueError, TypeError):
            return 0

    @staticmethod
    def _resolve_invoice_status(inv: dict[str, Any]) -> str:
        """Map QuickBooks invoice state to a canonical status string."""
        balance = inv.get("Balance", 0)
        due_date_str = inv.get("DueDate", "")
        if balance is None:
            balance = 0
        try:
            balance = float(balance)
        except (ValueError, TypeError):
            balance = 0

        if balance <= 0:
            return "paid"

        # Check if overdue
        if due_date_str:
            try:
                due_date = datetime.fromisoformat(due_date_str).replace(tzinfo=None)
                if due_date < datetime.utcnow():
                    return "overdue"
            except (ValueError, TypeError):
                pass

        total = inv.get("TotalAmt", 0)
        try:
            total = float(total)
        except (ValueError, TypeError):
            total = 0

        if balance < total:
            return "partly_paid"

        return "unpaid"

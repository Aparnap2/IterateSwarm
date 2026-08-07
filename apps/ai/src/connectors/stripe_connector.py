"""
Stripe Accounting Connector — capability implementation of :class:`AccountingConnector`.

Provides invoice and transaction data through the Stripe REST API.
Supports mock mode for development.

Environment Variables (production mode):
    STRIPE_API_KEY: Stripe secret key (``sk_live_...`` or ``sk_test_...``)
    STRIPE_API_URL: Optional custom API URL (defaults to ``https://api.stripe.com``)
"""

from __future__ import annotations

import logging
import os
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
        "id": "in_mock_001",
        "customer": "Acme Corp",
        "total_cents": 299000,
        "balance_cents": 0,
        "status": "paid",
        "due_date": "2026-07-15",
    },
    {
        "id": "in_mock_002",
        "customer": "Globex Inc",
        "total_cents": 499000,
        "balance_cents": 499000,
        "status": "unpaid",
        "due_date": "2026-08-01",
    },
    {
        "id": "in_mock_003",
        "customer": "Stark Industries",
        "total_cents": 999000,
        "balance_cents": 999000,
        "status": "overdue",
        "due_date": "2026-06-30",
    },
    {
        "id": "in_mock_004",
        "customer": "Acme Corp",
        "total_cents": 299000,
        "balance_cents": 100000,
        "status": "partly_paid",
        "due_date": "2026-07-20",
    },
]

_MOCK_TRANSACTIONS: list[dict[str, Any]] = [
    {
        "id": "txn_mock_001",
        "description": "Subscription - Acme Corp (monthly)",
        "amount_cents": 299000,
        "type": "income",
        "date": "2026-07-20",
    },
    {
        "id": "txn_mock_002",
        "description": "Refund - Globex Inc overcharge",
        "amount_cents": -50000,
        "type": "expense",
        "date": "2026-07-19",
    },
    {
        "id": "txn_mock_003",
        "description": "Payout - Stripe transfer to bank",
        "amount_cents": -1500000,
        "type": "expense",
        "date": "2026-07-18",
    },
    {
        "id": "txn_mock_004",
        "description": "Invoice payment - Stark Industries",
        "amount_cents": 999000,
        "type": "income",
        "date": "2026-07-17",
    },
]


class StripeConnector(AccountingConnector):
    """Stripe accounting connector.

    Parameters
    ----------
    config: ConnectorConfig
        If ``config.mock_mode`` is *True* or no Stripe API key is configured,
        returns realistic seed data.

    Usage::

        config = ConnectorConfig(tenant_id="startup_abc", mock_mode=True)
        stripe = StripeConnector(config)
        invoices = stripe.get_invoices()
    """

    def __init__(self, config: ConnectorConfig) -> None:
        super().__init__(config)
        self._api_key = config.credentials.get(
            "api_key", os.getenv("STRIPE_API_KEY", "")
        )
        self._api_url = config.credentials.get(
            "api_url", os.getenv("STRIPE_API_URL", "https://api.stripe.com")
        )
        # Auto-enable mock when no API key is configured
        if not self._api_key:
            logger.info(
                "StripeConnector[%s]: no API key found, enabling mock mode",
                config.tenant_id,
            )
            self.config.mock_mode = True

    def name(self) -> str:
        return "stripe"

    # ------------------------------------------------------------------
    # Health
    # ------------------------------------------------------------------

    @circuit_breaker("stripe")
    def health(self) -> dict[str, Any]:
        if self.config.mock_mode:
            return {"status": "ok", "latency_ms": 0, "source": "stripe_mock"}

        import time

        start = time.monotonic()
        try:
            # Use the balance endpoint as a lightweight connectivity check
            resp = httpx.get(
                f"{self._api_url}/v1/balance",
                headers=self._headers(),
                timeout=10.0,
            )
            resp.raise_for_status()
            elapsed = int((time.monotonic() - start) * 1000)
            return {"status": "ok", "latency_ms": elapsed, "source": "stripe"}
        except Exception as exc:
            elapsed = int((time.monotonic() - start) * 1000)
            logger.warning("Stripe health check failed: %s", exc)
            return {"status": "down", "latency_ms": elapsed, "error": str(exc)}

    # ------------------------------------------------------------------
    # Accounting methods
    # ------------------------------------------------------------------

    def get_invoices(self) -> list[dict[str, Any]]:
        if self.config.mock_mode:
            return [self._add_metadata(inv, "stripe_mock") for inv in _MOCK_INVOICES]

        try:
            raw = self._list_resource("invoices", limit=100)
            invoices = []
            for inv in raw.get("data", []):
                invoices.append(self._add_metadata({
                    "id": inv.get("id", ""),
                    "customer": self._customer_name(inv.get("customer", "")),
                    "total_cents": inv.get("total", 0),
                    "balance_cents": max(0, inv.get("total", 0) - inv.get("amount_paid", 0)),
                    "status": self._resolve_invoice_status(inv),
                    "due_date": (inv.get("due_date", "") or "")[:10],
                }, "stripe"))
            return invoices
        except Exception as exc:
            logger.error("Stripe get_invoices failed: %s", exc)
            return [self._error_result("stripe", error=str(exc))]

    def get_transactions(self) -> list[dict[str, Any]]:
        if self.config.mock_mode:
            return [self._add_metadata(txn, "stripe_mock") for txn in _MOCK_TRANSACTIONS]

        try:
            raw = self._list_resource("balance_transactions", limit=100)
            transactions = []
            for txn in raw.get("data", []):
                amount = txn.get("amount", 0)
                transactions.append(self._add_metadata({
                    "id": txn.get("id", ""),
                    "description": txn.get("description", "") or txn.get("source", ""),
                    "amount_cents": amount,
                    "type": "income" if amount > 0 else "expense",
                    "date": self._timestamp_to_date(txn.get("created", 0)),
                }, "stripe"))
            return transactions
        except Exception as exc:
            logger.error("Stripe get_transactions failed: %s", exc)
            return [self._error_result("stripe", error=str(exc))]

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self._api_key}",
            "Stripe-Version": "2023-10-16",
            "Content-Type": "application/x-www-form-urlencoded",
        }

    @circuit_breaker("stripe_query")
    def _list_resource(self, resource: str, limit: int = 100) -> dict[str, Any]:
        """List a Stripe API resource with pagination."""
        url = f"{self._api_url}/v1/{resource}"
        params = {"limit": str(min(limit, 100))}
        resp = httpx.get(url, params=params, headers=self._headers(), timeout=30.0)
        resp.raise_for_status()
        return resp.json()

    def _customer_name(self, customer_id: str) -> str:
        """Resolve a customer ID to a display name (best-effort)."""
        if not customer_id or not self._api_key:
            return customer_id or ""
        try:
            resp = httpx.get(
                f"{self._api_url}/v1/customers/{customer_id}",
                headers=self._headers(),
                timeout=10.0,
            )
            if resp.status_code == 200:
                data = resp.json()
                return data.get("name", "") or data.get("email", "") or customer_id
        except Exception:
            pass
        return customer_id

    @staticmethod
    def _resolve_invoice_status(inv: dict[str, Any]) -> str:
        """Map Stripe invoice status to canonical status string."""
        status = inv.get("status", "unknown")
        if status == "paid":
            return "paid"
        if status == "draft":
            return "unpaid"
        if status in ("open", "uncollectible"):
            # Check if overdue
            import datetime

            due_date = inv.get("due_date", 0)
            if due_date and isinstance(due_date, (int, float)):
                due_dt = datetime.datetime.fromtimestamp(due_date, tz=datetime.timezone.utc)
                if due_dt < datetime.datetime.now(datetime.timezone.utc):
                    return "overdue"

            # Check if partially paid
            total = inv.get("total", 0)
            paid = inv.get("amount_paid", 0)
            if paid > 0 and paid < total:
                return "partly_paid"
            return "unpaid"
        return status

    @staticmethod
    def _timestamp_to_date(ts: int) -> str:
        """Convert a Unix timestamp to ISO date string."""
        import datetime

        if not ts:
            return ""
        dt = datetime.datetime.fromtimestamp(ts, tz=datetime.timezone.utc)
        return dt.strftime("%Y-%m-%d")

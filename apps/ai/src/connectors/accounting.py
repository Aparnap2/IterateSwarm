"""
Accounting Connector ABC — capability interface for financial data.

Concrete implementations:

* :class:`connectors.quickbooks_connector.QuickBooksConnector`
* :class:`connectors.stripe_connector.StripeConnector`
"""

from __future__ import annotations

from abc import abstractmethod
from typing import Any

from .base import Connector


class AccountingConnector(Connector):
    """Capability interface for accounting / financial data sources.

    Every accounting connector must implement the methods below.  Return
    values are ``list[dict]`` or ``dict`` collections with ``source`` and
    ``fetched_at`` metadata.
    """

    def capability(self) -> str:
        return "accounting"

    # ------------------------------------------------------------------
    # Required accounting methods
    # ------------------------------------------------------------------

    @abstractmethod
    def get_invoices(self) -> list[dict[str, Any]]:
        """Return outstanding / recent invoices.

        Each entry should contain at minimum:

        .. code-block:: python

            {
                "id": "INV-001",
                "customer": "Acme Corp",
                "total_cents": 1500000,
                "balance_cents": 500000,
                "status": "paid" | "unpaid" | "overdue" | "partly_paid",
                "due_date": "2026-07-15",
                "source": "quickbooks",
                "fetched_at": "2026-07-26T12:00:00Z",
            }
        """
        ...

    @abstractmethod
    def get_transactions(self) -> list[dict[str, Any]]:
        """Return recent financial transactions.

        Each entry should contain at minimum:

        .. code-block:: python

            {
                "id": "txn_001",
                "description": "Platform subscription - Acme",
                "amount_cents": 500000,
                "type": "income" | "expense",
                "date": "2026-07-20",
                "source": "quickbooks",
                "fetched_at": "2026-07-26T12:00:00Z",
            }
        """
        ...

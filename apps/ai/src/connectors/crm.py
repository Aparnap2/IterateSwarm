"""
CRM Connector ABC — capability interface for Customer Relationship Management.

Concrete implementations:

* :class:`connectors.salesforce.SalesforceConnector`

Planned implementations:

* :class:`connectors.hubspot_connector.HubSpotConnector` (future)
"""

from __future__ import annotations

from abc import abstractmethod
from typing import Any

from .base import Connector


class CRMConnector(Connector):
    """Capability interface for CRM data sources.

    Every CRM connector must implement the methods below.  Return values are
    ``dict`` (single entity) or ``list[dict]`` (collections), each dict
    carrying ``source`` and ``fetched_at`` metadata (added automatically by
    :meth:`Connector._add_metadata`).
    """

    def capability(self) -> str:
        return "crm"

    # ------------------------------------------------------------------
    # Required CRM methods
    # ------------------------------------------------------------------

    @abstractmethod
    def get_customers(self) -> list[dict[str, Any]]:
        """Return all active customers.

        Each entry should contain at minimum:

        .. code-block:: python

            {
                "id": "cus_001",
                "name": "Acme Corp",
                "email": "billing@acme.com",
                "status": "active",
                "source": "salesforce",
                "fetched_at": "2026-07-26T12:00:00Z",
            }
        """
        ...

    @abstractmethod
    def get_opportunities(self) -> list[dict[str, Any]]:
        """Return open sales opportunities.

        Each entry should contain at minimum:

        .. code-block:: python

            {
                "id": "opp_001",
                "name": "Enterprise Deal Q3",
                "stage": "negotiation",
                "amount_cents": 50000000,
                "probability_pct": 60,
                "source": "salesforce",
                "fetched_at": "2026-07-26T12:00:00Z",
            }
        """
        ...

    @abstractmethod
    def get_deals(self) -> list[dict[str, Any]]:
        """Return won/lost deals (closed-won and closed-lost).

        Each entry should contain at minimum:

        .. code-block:: python

            {
                "id": "deal_001",
                "name": "Acme Corp - Platform Subscription",
                "amount_cents": 12000000,
                "stage": "closed_won",
                "closed_at": "2026-06-15",
                "source": "salesforce",
                "fetched_at": "2026-07-26T12:00:00Z",
            }
        """
        ...

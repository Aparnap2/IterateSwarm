"""
ERP Connector ABC — capability interface for Enterprise Resource Planning.

Concrete implementations:

* :class:`connectors.erpnext_connector.ERPNextConnector`
"""

from __future__ import annotations

from abc import abstractmethod
from typing import Any

from .base import Connector


class ERPConnector(Connector):
    """Capability interface for ERP data sources.

    Every ERP connector must implement the methods below.  Return values are
    ``list[dict]`` collections with ``source`` and ``fetched_at`` metadata.
    """

    def capability(self) -> str:
        return "erp"

    # ------------------------------------------------------------------
    # Required ERP methods
    # ------------------------------------------------------------------

    @abstractmethod
    def get_orders(self) -> list[dict[str, Any]]:
        """Return active/open sales orders.

        Each entry should contain at minimum:

        .. code-block:: python

            {
                "id": "ORD-001",
                "customer": "Acme Corp",
                "total_cents": 500000,
                "status": "draft" | "submitted" | "overdue",
                "order_date": "2026-07-01",
                "source": "erpnext",
                "fetched_at": "2026-07-26T12:00:00Z",
            }
        """
        ...

    @abstractmethod
    def get_inventory(self) -> list[dict[str, Any]]:
        """Return current inventory / stock levels.

        Each entry should contain at minimum:

        .. code-block:: python

            {
                "item": "Widget A",
                "quantity": 150,
                "warehouse": "Main Storage",
                "source": "erpnext",
                "fetched_at": "2026-07-26T12:00:00Z",
            }
        """
        ...

    @abstractmethod
    def get_suppliers(self) -> list[dict[str, Any]]:
        """Return active supplier records.

        Each entry should contain at minimum:

        .. code-block:: python

            {
                "id": "SUP-001",
                "name": "PartsCo Ltd",
                "status": "active",
                "source": "erpnext",
                "fetched_at": "2026-07-26T12:00:00Z",
            }
        """
        ...

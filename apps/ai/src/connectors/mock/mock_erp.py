"""
Mock ERP Connector — returns seed data without network calls.

Activated by setting ``config.mock_mode = True`` on a :class:`ConnectorConfig`
or by requesting capability ``"erp_mock"`` from the registry.

Provides sample orders, inventory, and suppliers for development and
integration testing.
"""

from __future__ import annotations

import logging
from typing import Any

from ..base import ConnectorConfig
from ..erp import ERPConnector

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Realistic mock seed data
# ---------------------------------------------------------------------------

_MOCK_ORDERS: list[dict[str, Any]] = [
    {
        "id": "ORD-MOCK-001",
        "customer": "Acme Corp",
        "items": [
            {"sku": "WGT-A", "name": "Widget A", "qty": 10, "unit_price_cents": 25000},
        ],
        "total_cents": 250000,
        "status": "submitted",
        "ordered_at": "2026-07-20T09:15:00Z",
    },
    {
        "id": "ORD-MOCK-002",
        "customer": "Globex Inc",
        "items": [
            {"sku": "WGT-B", "name": "Widget B", "qty": 25, "unit_price_cents": 48000},
            {"sku": "GDG-X", "name": "Gadget X", "qty": 5, "unit_price_cents": 120000},
        ],
        "total_cents": 1800000,
        "status": "draft",
        "ordered_at": "2026-07-22T14:30:00Z",
    },
    {
        "id": "ORD-MOCK-003",
        "customer": "Initech",
        "items": [
            {"sku": "CMP-Y", "name": "Component Y", "qty": 100, "unit_price_cents": 3500},
        ],
        "total_cents": 350000,
        "status": "overdue",
        "ordered_at": "2026-06-01T08:00:00Z",
    },
]

_MOCK_INVENTORY: list[dict[str, Any]] = [
    {"sku": "WGT-A", "name": "Widget A", "quantity": 150, "reorder_point": 50, "unit_price_cents": 25000},
    {"sku": "WGT-B", "name": "Widget B", "quantity": 42, "reorder_point": 30, "unit_price_cents": 48000},
    {"sku": "GDG-X", "name": "Gadget X", "quantity": 8, "reorder_point": 10, "unit_price_cents": 120000},
    {"sku": "CMP-Y", "name": "Component Y", "quantity": 500, "reorder_point": 200, "unit_price_cents": 3500},
    {"sku": "RAW-Z", "name": "Raw Material Z", "quantity": 1000, "reorder_point": 500, "unit_price_cents": 1200},
]

_MOCK_SUPPLIERS: list[dict[str, Any]] = [
    {
        "id": "SUP-MOCK-001",
        "name": "PartsCo Ltd",
        "contact_email": "orders@partsco.com",
        "lead_time_days": 14,
        "status": "active",
    },
    {
        "id": "SUP-MOCK-002",
        "name": "RawMaterial Inc",
        "contact_email": "supply@rawmat.io",
        "lead_time_days": 7,
        "status": "active",
    },
]


class MockERPConnector(ERPConnector):
    """ERP connector that returns realistic seed data with zero network calls.

    Parameters
    ----------
    config: ConnectorConfig
        The ``mock_mode`` flag is ignored — this connector is *always* mock.

    Usage::

        config = ConnectorConfig(tenant_id="test", mock_mode=True)
        erp = MockERPConnector(config)
        orders = erp.get_orders()
    """

    def __init__(self, config: ConnectorConfig) -> None:
        super().__init__(config)
        self.config.mock_mode = True  # always mock

    def name(self) -> str:
        return "mock_erp"

    # ------------------------------------------------------------------
    # Health
    # ------------------------------------------------------------------

    def health(self) -> dict[str, Any]:
        return {"status": "ok", "latency_ms": 3, "mock": True, "source": "mock_erp"}

    # ------------------------------------------------------------------
    # ERP methods
    # ------------------------------------------------------------------

    def get_orders(self) -> list[dict[str, Any]]:
        return [self._add_metadata(o, "mock_erp") for o in _MOCK_ORDERS]

    def get_inventory(self) -> list[dict[str, Any]]:
        return [self._add_metadata(i, "mock_erp") for i in _MOCK_INVENTORY]

    def get_suppliers(self) -> list[dict[str, Any]]:
        return [self._add_metadata(s, "mock_erp") for s in _MOCK_SUPPLIERS]

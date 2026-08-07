"""
Mock connector implementations for development and testing.

Each mock connector returns realistic seed data without any network calls,
activated by setting ``config.mock_mode = True`` on the ``ConnectorConfig``.

Usage::

    from connectors import get_connector, ConnectorConfig

    config = ConnectorConfig(tenant_id="test", mock_mode=True)
    crm = get_connector("crm", config)
    customers = crm.get_customers()  # returns seed data, no network

Available mocks
---------------
* :class:`mock_crm.MockCRMConnector` — returns sample customers, opps, deals
* :class:`mock_erp.MockERPConnector` — returns sample orders, inventory, suppliers
"""

from .mock_crm import MockCRMConnector
from .mock_erp import MockERPConnector

__all__ = [
    "MockCRMConnector",
    "MockERPConnector",
]

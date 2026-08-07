"""
CRM Connector ABC — capability interface for Customer Relationship Management.

Concrete implementations:

* :class:`connectors.mock.mock_crm.MockCRMConnector`

All production CRM connectors (Salesforce, HubSpot) have been replaced by
V6 equivalents. This ABC is retained because ``MockCRMConnector`` (used in
tests and mock mode) still inherits from it.
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
        ...

    @abstractmethod
    def get_opportunities(self) -> list[dict[str, Any]]:
        ...

    @abstractmethod
    def get_deals(self) -> list[dict[str, Any]]:
        ...

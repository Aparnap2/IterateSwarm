"""Capability Runtime — operational capabilities for AI Employees.

Wraps the connector registry layer with a clean interface that employees
consume. Employees NEVER call connectors directly — they call capabilities.

Capabilities:
- CRM (Salesforce)
- Project (Jira)
- Communication (Slack)
- Knowledge (Notion)
- ERP (NetSuite/QuickBooks)

Each capability produces EvidenceRecords and accepts ExecutionCommands.
"""
from __future__ import annotations

import logging
from typing import Any, Protocol, runtime_checkable

from src.connectors import get_connector, register_connector, ConnectorConfig

logger = logging.getLogger(__name__)


@runtime_checkable
class Capability(Protocol):
    """A domain-specific capability that employees invoke."""

    capability: str

    def observe(self, tenant_id: str, **filters) -> list[dict[str, Any]]:
        """Read data from the underlying system as raw evidence."""
        ...

    def execute(self, command: str, payload: dict[str, Any], tenant_id: str) -> dict[str, Any]:
        """Execute a write command through the capability."""
        ...


class BaseCapability:
    """Shared infrastructure for all capabilities."""

    def __init__(self, connector: Connector, tenant_id: str = "default"):
        self.connector = connector
        self.tenant_id = tenant_id
        self.capability = connector.capability

    def observe(self, **filters) -> list[dict[str, Any]]:
        return self.connector.observe(**filters)

    def execute(self, command: str, payload: dict[str, Any]) -> dict[str, Any]:
        return self.connector.execute(command, payload)


class CRMCapability(BaseCapability):
    """CRM capability (Salesforce).

    Methods map directly to Salesforce entity operations.
    """

    @property
    def capability(self) -> str:
        return "crm"

    def get_customers(self) -> list[dict[str, Any]]:
        return self.connector.get_customers()

    def get_deals(self) -> list[dict[str, Any]]:
        return self.connector.get_deals()

    def update_deal(self, deal_id: str, fields: dict[str, Any]) -> dict[str, Any]:
        return self.connector.update_deal(deal_id, fields)

    def create_customer(self, data: dict[str, Any]) -> str:
        return self.connector.create_customer(data)


class ProjectCapability(BaseCapability):
    """Project capability (Jira)."""

    @property
    def capability(self) -> str:
        return "project"

    def get_issues(self, **filters) -> list[dict[str, Any]]:
        return self.connector.get_issues(**filters)

    def create_issue(self, data: dict[str, Any]) -> str:
        return self.connector.create_issue(data)

    def update_issue(self, issue_id: str, fields: dict[str, Any]) -> dict[str, Any]:
        return self.connector.update_issue(issue_id, fields)


class CommunicationCapability(BaseCapability):
    """Communication capability (Slack)."""

    @property
    def capability(self) -> str:
        return "messaging"

    def send_message(self, channel: str, text: str) -> dict[str, Any]:
        return self.connector.send_message(channel, text)

    def get_messages(self, channel: str, **filters) -> list[dict[str, Any]]:
        return self.connector.get_messages(channel, **filters)


class KnowledgeCapability(BaseCapability):
    """Knowledge capability (Notion)."""

    @property
    def capability(self) -> str:
        return "knowledge"

    def get_pages(self, **filters) -> list[dict[str, Any]]:
        return self.connector.get_pages(**filters)

    def create_page(self, data: dict[str, Any]) -> str:
        return self.connector.create_page(data)

    def update_page(self, page_id: str, data: dict[str, Any]) -> dict[str, Any]:
        return self.connector.update_page(page_id, data)


class CapabilityRegistry:
    """Factory for capability instances.

    Maps capability names to capability classes, backed by the connector registry.
    """

    _capability_map: dict[str, type[BaseCapability]] = {
        "crm": CRMCapability,
        "project": ProjectCapability,
        "messaging": CommunicationCapability,
        "knowledge": KnowledgeCapability,
    }

    # Note: Real connector subclasses (e.g. SalesforceV6Connector) must be
    # registered by the application. The abstract base classes (CRMConnector,
    # etc.) are NOT registered here — concrete subclasses must register themselves.
    pass

    @classmethod
    def get_capability(cls, capability: str, config: ConnectorConfig) -> BaseCapability:
        """Get a capability instance for the given capability name."""
        connector = get_connector(capability, config)
        cap_cls = cls._capability_map.get(capability, BaseCapability)
        return cap_cls(connector=connector, tenant_id=config.tenant_id)

    @classmethod
    def list_capabilities(cls) -> list[str]:
        return list(cls._capability_map.keys())

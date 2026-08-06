"""V6 Connector Contract — Protocol + Manifest for all data connectors.

Per ADR-001, every connector exposes exactly three async methods:
``connect``, ``fetch``, and ``health``.  Connectors never mutate state,
write to Neo4j, or generate artifacts — they are pure adapters.

Example
-------
Implementing a connector::

    from src.connectors.v6_contract import V6Connector, ConnectorManifest

    class MyConnector:
        async def connect(self) -> ConnectorManifest: ...
        async def fetch(self, since=None) -> list[EvidenceRecord]: ...
        async def health(self) -> dict: ...
        async def close(self) -> None: ...

Using a connector::

    async with get_connector(...) as conn:
        manifest = await conn.connect()
        records = await conn.fetch(since=last_sync)
"""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Protocol, runtime_checkable

from pydantic import BaseModel

from src.entities.models import EvidenceRecord


# ── Enums ───────────────────────────────────────────────────────────────


class SyncStrategy(str, Enum):
    """How a connector synchronises data from its source."""

    POLLING = "polling"
    WEBHOOK = "webhook"
    BOTH = "both"


class ConnectorCapability(str, Enum):
    """High-level capability category a connector belongs to."""

    MESSAGING = "messaging"
    CRM = "crm"
    DOCUMENTATION = "documentation"
    PROJECT_MGMT = "project_management"


# ── Manifest ────────────────────────────────────────────────────────────


class ConnectorManifest(BaseModel):
    """Describes a connector's identity, capabilities, and constraints.

    Returned by ``V6Connector.connect()`` so the runtime can schedule
    the connector appropriately (which queue, rate limits, etc.).
    """

    name: str
    version: str
    capabilities: list[ConnectorCapability]
    supported_objects: list[str]  # e.g. ["messages", "channels", "users"]
    sync_strategy: SyncStrategy
    supports_webhook: bool
    supports_polling: bool
    rate_limit_per_minute: int
    auth_type: str  # "oauth2", "api_key", "basic"
    supports_incremental_sync: bool
    deletion_strategy: str  # "soft_delete", "hard_delete", "ignore"


# ── Protocol ────────────────────────────────────────────────────────────


@runtime_checkable
class V6Connector(Protocol):
    """The three-method contract every V6 connector must satisfy.

    *Connectors are pure adapters* — no side effects, no state mutation.
    """

    async def connect(self) -> ConnectorManifest:
        """Establish a connection to the source and return its manifest.

        This may perform authentication, handshake, or capability
        negotiation.  Implementations should be idempotent.
        """
        ...

    async def fetch(self, since: datetime | None = None) -> list[EvidenceRecord]:
        """Retrieve all evidence records created since *since*.

        Returns an empty list if there is no new data.  The caller
        (pipeline stage 1) owns dedup via the ``hash`` field.
        """
        ...

    async def health(self) -> dict:
        """Return current connector health.

        Returns a dict with at minimum::

            {"status": "healthy" | "degraded" | "disconnected",
             "latency_ms": <int>}
        """
        ...

    async def close(self) -> None:
        """Tear down the connection and release resources.

        Called by the runtime when the connector is no longer needed.
        Implementations should be idempotent.
        """
        ...

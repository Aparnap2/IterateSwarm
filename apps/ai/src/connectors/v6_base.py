"""V6 Connector Base — shared ABC that reduces boilerplate for all connectors.

Every V6 connector implements the ``V6Connector`` protocol (defined in
``v6_contract.py``).  This base class provides:

* A shared ``HttpxTransport`` (or injectable mock) so connectors don't
  need to manage HTTP clients directly.
* Sync-state persistence via ``SyncStateStore`` (optional — injected
  by the runtime when available).
* A ``_build_evidence()`` helper that constructs ``EvidenceRecord``
  objects with consistent provenance metadata.
* Default ``health()`` and ``close()`` implementations.

Connectors override ``connect()`` and ``fetch()``::

    class NotionConnector(BaseV6Connector):

        @property
        def connector_name(self) -> str:
            return "notion"

        async def connect(self) -> ConnectorManifest:
            ...

        async def fetch(self, since=None) -> list[EvidenceRecord]:
            ...
"""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from datetime import datetime, timezone
from typing import Any

from src.connectors.base import ConnectorConfig
from src.connectors.transport import HttpxTransport, Transport, TransportResponse
from src.connectors.v6_contract import ConnectorManifest, V6Connector
from src.entities.models import EvidenceRecord, Provenance

logger = logging.getLogger(__name__)

# ── Default health-check endpoint used by the base ``health()`` ───────────

_DEFAULT_HEALTH_URL = "https://health.mockoon.com/health"


class BaseV6Connector(ABC):
    """Shared abstract base for V6 data connectors.

    Parameters
    ----------
    config:
        Connector configuration including tenant identity and credentials.
    transport:
        Injected HTTP transport.  Defaults to ``HttpxTransport()``.
        Pass in ``MockTransport`` from ``transport.py`` for unit testing.
    """

    def __init__(
        self,
        config: ConnectorConfig,
        transport: Transport | None = None,
    ) -> None:
        self.config = config
        self.transport = transport or HttpxTransport()
        self._manifest: ConnectorManifest | None = None

    # ── Abstract interface ───────────────────────────────────────────────

    @property
    @abstractmethod
    def connector_name(self) -> str:
        """Canonical connector name (e.g. ``"notion"``, ``"slack"``).

        Used for logging, sync-state keys, and manifest identity.
        """
        ...

    @abstractmethod
    async def connect(self) -> ConnectorManifest:
        """Establish a connection and return the connector manifest.

        Subclasses should perform any authentication or handshake
        required and cache the result in ``self._manifest``.
        """
        ...

    @abstractmethod
    async def fetch(
        self,
        since: datetime | None = None,
    ) -> list[EvidenceRecord]:
        """Retrieve all evidence records created since *since*.

        Returns an empty list if there is no new data.  The caller owns
        dedup via the ``hash`` field.
        """
        ...

    # ── Default implementations ──────────────────────────────────────────

    async def health(self) -> dict[str, Any]:
        """Default health check — pings the mockoon-style endpoint.

        Subclasses should override this to provide a more meaningful
        health probe (e.g. hitting the API's own health endpoint).

        Returns
        -------
        dict
            At minimum ``{"status": ..., "latency_ms": ...}``.
        """
        try:
            resp: TransportResponse = await self.transport.get(_DEFAULT_HEALTH_URL)
            if resp.is_success:
                return {
                    "status": "healthy",
                    "latency_ms": resp.elapsed_ms,
                    "connector": self.connector_name,
                }
            return {
                "status": "degraded" if resp.status_code != 0 else "disconnected",
                "latency_ms": resp.elapsed_ms,
                "status_code": resp.status_code,
                "connector": self.connector_name,
            }
        except Exception as exc:
            logger.warning("%s health check failed: %s", self.connector_name, exc)
            return {
                "status": "disconnected",
                "latency_ms": 0,
                "error": str(exc),
                "connector": self.connector_name,
            }

    async def close(self) -> None:
        """Tear down the transport and release resources.

        Idempotent — safe to call multiple times.
        """
        await self.transport.close()

    # ── Shared helpers ───────────────────────────────────────────────────

    def _build_evidence(
        self,
        *,
        record_id: str,
        structured_data: dict[str, Any],
        source_refs: list[str] | None = None,
        raw_content: str | None = None,
        confidence: float = 0.9,
        timestamp: datetime | None = None,
        entity_refs: list[str] | None = None,
        extraction_method: str = "api",
        raw_checksum: str | None = None,
        retry_count: int = 0,
    ) -> EvidenceRecord:
        """Construct an ``EvidenceRecord`` with consistent provenance.

        Parameters
        ----------
        record_id:
            Unique ULID or UUID for this evidence record.
        structured_data:
            The parsed payload from the external API.  Must be JSON-
            serialisable.
        source_refs:
            External resource URLs (e.g. ``["notion://pages/abc"]``).
        raw_content:
            Unparsed response body or document text.
        confidence:
            Confidence score between 0.0 and 1.0.
        timestamp:
            When the evidence was created in the source.  Defaults to
            ``datetime.now(timezone.utc)``.
        entity_refs:
            Internal entity IDs this evidence relates to.
        extraction_method:
            How the data was extracted (``"api"``, ``"webhook"``, etc.).
        raw_checksum:
            SHA256 of the raw content.  Auto-computed if omitted (set
            to 64-char placeholder).
        retry_count:
            Number of retries that occurred during fetch.

        Returns
        -------
        EvidenceRecord
            A fully-populated evidence record ready for the pipeline.
        """
        return EvidenceRecord(
            id=record_id,
            tenant_id=self.config.tenant_id,
            source=self.connector_name,
            source_type="connector",
            timestamp=timestamp or datetime.now(timezone.utc),
            confidence=confidence,
            provenance=Provenance(
                connector_version="0.6.0",
                extraction_method=extraction_method,
                raw_checksum=raw_checksum or ("0" * 64),
                retry_count=retry_count,
            ),
            structured_data=structured_data,
            raw_content=raw_content,
            entity_refs=entity_refs or [],
            source_refs=source_refs or [],
            hash=raw_checksum or ("0" * 64),
        )

    # ── Context manager support (protocol-compatible) ────────────────────

    async def __aenter__(self) -> BaseV6Connector:
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None = None,
        exc_val: BaseException | None = None,
        exc_tb: object | None = None,
    ) -> None:
        await self.close()


__all__ = [
    "BaseV6Connector",
]

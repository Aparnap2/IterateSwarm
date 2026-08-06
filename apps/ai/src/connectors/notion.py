"""Notion Connector — V6 OntologyAI reference implementation.

Fetches pages from a Notion-like REST API (or Mockoon mock on
``http://localhost:3001``) and returns each page as a canonical
``EvidenceRecord`` with SHA256-deduplicated hashes.

Usage
-----
Production::

    from src.connectors.base import ConnectorConfig
    from src.connectors.notion import NotionConnector

    config = ConnectorConfig(
        tenant_id="tenant-abc",
        credentials={"base_url": "http://notion.example.com", "api_token": "..."},
    )
    async with NotionConnector(config) as conn:
        manifest = await conn.connect()
        records = await conn.fetch(since=datetime(2026, 7, 1, tzinfo=UTC))

Testing with MockTransport::

    from src.connectors.transport import MockTransport, TransportResponse

    transport = MockTransport({
        "GET /pages": [TransportResponse(status_code=200, json={"results": [...]})],
    })
    connector = NotionConnector(config, transport=transport)
"""

from __future__ import annotations

import hashlib
import json
import logging
from datetime import datetime, timezone
from typing import Any

import ulid

from src.connectors.base import ConnectorConfig
from src.connectors.transport import Transport, TransportResponse
from src.connectors.v6_base import BaseV6Connector
from src.connectors.v6_contract import (
    ConnectorCapability,
    ConnectorManifest,
    SyncStrategy,
)
from src.entities.models import EvidenceRecord

logger = logging.getLogger(__name__)

# ── Constants ──────────────────────────────────────────────────────────────

_NOTION_VERSION = "2022-06-28"
_DEFAULT_BASE_URL = "http://localhost:3001"
_DEFAULT_API_TOKEN = "mock-token"
_PAGE_SIZE = 10
_CONFIDENCE_DEFAULT = 0.9


class NotionConnector(BaseV6Connector):
    """V6 connector that fetches pages from a Notion-compatible API.

    Talks to a Notion-like REST endpoint (e.g. Mockoon on ``localhost:3001``)
    and returns each page as a canonical ``EvidenceRecord``.

    Parameters
    ----------
    config:
        Connector configuration.  ``credentials`` may include:
        - ``base_url``  — API base URL (default ``http://localhost:3001``)
        - ``api_token`` — Bearer token  (default ``mock-token``)
    transport:
        Injected HTTP transport.  Defaults to ``HttpxTransport()``.
        Pass ``MockTransport`` from ``transport.py`` for unit testing.
    """

    connector_name = "notion"

    def __init__(
        self,
        config: ConnectorConfig,
        transport: Transport | None = None,
    ) -> None:
        super().__init__(config, transport)
        self.base_url: str = config.credentials.get("base_url", _DEFAULT_BASE_URL)
        self.api_token: str = config.credentials.get("api_token", _DEFAULT_API_TOKEN)

    # ── Internal helpers ──────────────────────────────────────────────────

    def _auth_headers(self) -> dict[str, str]:
        """Build standard headers with Bearer auth and Notion version."""
        return {
            "Authorization": f"Bearer {self.api_token}",
            "Content-Type": "application/json",
            "Notion-Version": _NOTION_VERSION,
        }

    def _compute_hash(
        self,
        structured_data: dict[str, Any],
    ) -> str:
        """Return SHA256 hex digest of ``tenant_id + structured_data``.

        The canonical JSON is sorted by key and has no whitespace so that
        identical data always produces the same hash (exact dedup).
        """
        canonical = json.dumps(
            {
                "tenant_id": self.config.tenant_id,
                "structured_data": structured_data,
            },
            sort_keys=True,
            separators=(",", ":"),
        )
        return hashlib.sha256(canonical.encode()).hexdigest()

    def _page_to_evidence(
        self,
        page: dict[str, Any],
    ) -> EvidenceRecord | None:
        """Convert a raw Notion page dict into an ``EvidenceRecord``.

        Parameters
        ----------
        page:
            A single page object from the ``GET /pages`` response.

        Returns
        -------
        EvidenceRecord | None
            ``None`` if the page is missing mandatory fields (``id``, ``title``).
        """
        page_id: str | None = page.get("id")
        title: str | None = page.get("title")
        last_edited_raw: str | None = page.get("last_edited_time")

        if not page_id or not title:
            logger.debug("Skipping page with missing id or title: %s", page_id)
            return None

        # Parse ISO-8601 timestamp (handle trailing "Z").
        if last_edited_raw:
            try:
                ts: datetime = datetime.fromisoformat(
                    last_edited_raw.replace("Z", "+00:00"),
                )
            except (ValueError, TypeError):
                logger.warning(
                    "Unparseable last_edited_time '%s' on page %s — using now",
                    last_edited_raw,
                    page_id,
                )
                ts = datetime.now(timezone.utc)
        else:
            ts = datetime.now(timezone.utc)

        # Extract properties with sensible defaults.
        props: dict[str, Any] = page.get("properties", {})
        status: str = props.get("status", "unknown")
        owner: str = props.get("owner", "unknown")
        tags: list[str] = props.get("tags", [])

        # Build the structured payload (canonical shape for the OntologyAI).
        structured_data: dict[str, Any] = {
            "record_type": "page",
            "external_id": page_id,
            "title": title,
            "tags": tags,
            "status": status,
            "owner": owner,
        }

        # SHA256 for exact dedup.
        checksum: str = self._compute_hash(structured_data)

        # Notion resource URIs used as source references.
        source_refs: list[str] = [f"notion://pages/{page_id}"]

        return self._build_evidence(
            record_id=str(ulid.new()),
            structured_data=structured_data,
            source_refs=source_refs,
            confidence=_CONFIDENCE_DEFAULT,
            timestamp=ts,
            raw_checksum=checksum,
        )

    # ── Protocol implementation ───────────────────────────────────────────

    async def connect(self) -> ConnectorManifest:
        """Verify API reachability and return the connector manifest.

        Performs a lightweight probe by fetching a single page.  The
        returned manifest advertises documentation capability, polling-only
        sync, and incremental-sync support.

        Returns
        -------
        ConnectorManifest
            Identity and capability metadata.
        """
        resp: TransportResponse = await self.transport.get(
            f"{self.base_url}/pages",
            params={"page_size": "1"},
            headers=self._auth_headers(),
        )

        if resp.is_success:
            logger.info(
                "Notion API reachable — %s ms",
                resp.elapsed_ms,
            )
        else:
            logger.warning(
                "Notion connect health-check failed: %s %s",
                resp.status_code,
                resp.text[:200],
            )

        self._manifest = ConnectorManifest(
            name=self.connector_name,
            version="0.6.0",
            capabilities=[ConnectorCapability.DOCUMENTATION],
            supported_objects=["pages"],
            sync_strategy=SyncStrategy.POLLING,
            supports_webhook=False,
            supports_polling=True,
            rate_limit_per_minute=30,
            auth_type="api_key",
            supports_incremental_sync=True,
            deletion_strategy="ignore",
        )
        return self._manifest

    async def fetch(
        self,
        since: datetime | None = None,
    ) -> list[EvidenceRecord]:
        """Fetch all pages, with optional ``since`` filter.

        Paginates through ``GET /pages`` (using ``next_cursor`` / ``start_cursor``)
        and converts each page into a canonical ``EvidenceRecord``.  The
        ``hash`` field is the SHA256 of ``tenant_id + structured_data`` and
        can be used by the caller for exact dedup.

        Parameters
        ----------
        since:
            If provided, only pages whose ``last_edited_time`` is strictly
            greater than *since* are returned.

        Returns
        -------
        list[EvidenceRecord]
            Canonical evidence records (may be empty on error).
        """
        records: list[EvidenceRecord] = []
        cursor: str | None = None

        while True:
            params: dict[str, str] = {"page_size": str(_PAGE_SIZE)}
            if cursor:
                params["start_cursor"] = cursor

            resp: TransportResponse = await self.transport.get(
                f"{self.base_url}/pages",
                params=params,
                headers=self._auth_headers(),
            )

            # ── Error handling ────────────────────────────────────────
            if resp.status_code == 401:
                logger.error(
                    "Notion API returned 401 — token may be invalid or revoked",
                )
                return []

            if not resp.is_success:
                logger.warning(
                    "Notion GET /pages returned %s — %s",
                    resp.status_code,
                    resp.text[:200],
                )
                return []

            # ── Parse body ────────────────────────────────────────────
            body: dict[str, Any] | list[Any] | None = resp.json
            if not isinstance(body, dict):
                logger.warning("Notion API returned non-dict response body")
                return []

            results: list[dict[str, Any]] = body.get("results", [])
            next_cursor: str | None = body.get("next_cursor")
            has_more: bool = body.get("has_more", False)

            for raw_page in results:
                record = self._page_to_evidence(raw_page)
                if record is None:
                    continue

                # Apply incremental-sync filter.
                if since is not None and record.timestamp <= since:
                    continue

                records.append(record)

            # ── Pagination ────────────────────────────────────────────
            if not has_more or not next_cursor:
                break
            cursor = next_cursor

        logger.info(
            "Notion fetch returned %s evidence record(s)%s",
            len(records),
            f" (since {since.isoformat()})" if since else "",
        )
        return records

    async def search(
        self,
        query: str,
        *,
        sort: str | None = None,
        direction: str = "descending",
    ) -> list[EvidenceRecord]:
        """Perform a full-text search via ``POST /search``.

        This is an optional convenience method for manual / ad-hoc syncs.
        It uses the same ``POST /search`` endpoint exposed by the Notion API.

        Parameters
        ----------
        query:
            Free-text search query.
        sort:
            Sort property (``"last_edited_time"`` or ``None``).
        direction:
            ``"ascending"`` or ``"descending"`` (default).

        Returns
        -------
        list[EvidenceRecord]
            Matching pages as evidence records (may be empty).
        """
        payload: dict[str, Any] = {"query": query}
        if sort:
            payload["sort"] = {"property": sort, "direction": direction}

        resp: TransportResponse = await self.transport.post(
            f"{self.base_url}/search",
            json=payload,
            headers=self._auth_headers(),
        )

        if not resp.is_success:
            logger.warning(
                "Notion POST /search returned %s — %s",
                resp.status_code,
                resp.text[:200],
            )
            return []

        body = resp.json
        if not isinstance(body, dict):
            return []

        records: list[EvidenceRecord] = []
        for raw_page in body.get("results", []):
            record = self._page_to_evidence(raw_page)
            if record is not None:
                records.append(record)

        logger.info(
            "Notion search for '%s' returned %s result(s)",
            query,
            len(records),
        )
        return records


__all__ = [
    "NotionConnector",
]

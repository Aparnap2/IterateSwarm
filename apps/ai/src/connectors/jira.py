"""Jira Connector — V6 OntologyAI connector for Jira Cloud REST API.

Fetches issues from a Jira-compatible API (or Mockoon mock on
``http://localhost:3003``) and returns each issue as a canonical
``EvidenceRecord`` with SHA256-deduplicated hashes.

Usage
-----
Production (pointed at the Mockoon mock for development)::

    from src.connectors.base import ConnectorConfig
    from src.connectors.jira import JiraConnector

    config = ConnectorConfig(
        tenant_id="tenant-abc",
        credentials={
            "base_url": "http://localhost:3003",
            "username": "admin",
            "api_token": "mock-token",
        },
    )
    async with JiraConnector(config) as conn:
        manifest = await conn.connect()
        records = await conn.fetch(since=datetime(2026, 7, 1, tzinfo=UTC))

Testing with MockTransport::

    from src.connectors.transport import MockTransport, TransportResponse

    transport = MockTransport({
        "GET /rest/api/3/search": [TransportResponse(status_code=200, json={...})],
    })
    connector = JiraConnector(config, transport=transport)
"""

from __future__ import annotations

import base64
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

_DEFAULT_BASE_URL = "http://localhost:3003"
_CONFIDENCE_DEFAULT = 0.95
_PAGINATION_MAX_RESULTS = 50


class JiraConnector(BaseV6Connector):
    """V6 connector that fetches issues from a Jira-compatible API.

    Talks to a Jira Cloud REST endpoint (e.g. Mockoon on ``localhost:3003``)
    and returns each issue as a canonical ``EvidenceRecord``.

    Parameters
    ----------
    config:
        Connector configuration.  ``credentials`` may include:
        - ``base_url``  — API base URL (default ``http://localhost:3003``)
        - ``username``  — Jira username for Basic auth
        - ``api_token`` — Jira API token for Basic auth
    transport:
        Injected HTTP transport.  Defaults to ``HttpxTransport()``.
        Pass ``MockTransport`` from ``transport.py`` for unit testing.
    """

    connector_name = "jira"

    def __init__(
        self,
        config: ConnectorConfig,
        transport: Transport | None = None,
    ) -> None:
        super().__init__(config, transport)
        self.base_url: str = config.credentials.get(
            "base_url", _DEFAULT_BASE_URL
        ).rstrip("/")
        self._username: str = config.credentials.get("username", "")
        self._api_token: str = config.credentials.get("api_token", "")

    # ── Internal helpers ──────────────────────────────────────────────────

    def _auth_headers(self) -> dict[str, str]:
        """Build standard headers with Basic auth for Jira API."""
        headers: dict[str, str] = {
            "Accept": "application/json",
        }
        if self._username and self._api_token:
            raw = f"{self._username}:{self._api_token}"
            encoded = base64.b64encode(raw.encode()).decode()
            headers["Authorization"] = f"Basic {encoded}"
        return headers

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

    def _issue_to_evidence(
        self,
        issue: dict[str, Any],
    ) -> EvidenceRecord | None:
        """Convert a raw Jira issue dict into an ``EvidenceRecord``.

        Parameters
        ----------
        issue:
            A single issue object from the ``GET /rest/api/3/search`` response.

        Returns
        -------
        EvidenceRecord | None
            ``None`` if the issue is missing its ``key`` field.
        """
        key: str | None = issue.get("key")
        if not key:
            logger.debug("Skipping issue with missing key")
            return None

        fields: dict[str, Any] = issue.get("fields", {}) or {}

        project: dict[str, Any] = fields.get("project", {}) or {}
        project_key: str = project.get("key", "")
        project_name: str = project.get("name", "")

        status: dict[str, Any] = fields.get("status", {}) or {}
        priority: dict[str, Any] = fields.get("priority", {}) or {}
        assignee: dict[str, Any] | None = fields.get("assignee")
        issuetype: dict[str, Any] = fields.get("issuetype", {}) or {}
        parent: dict[str, Any] | None = fields.get("parent")

        created_raw: str | None = fields.get("created")

        # Parse ISO-8601 timestamp (handle trailing "Z").
        if created_raw:
            try:
                ts: datetime = datetime.fromisoformat(
                    created_raw.replace("Z", "+00:00"),
                )
            except (ValueError, TypeError):
                logger.warning(
                    "Unparseable created '%s' on issue %s — using now",
                    created_raw,
                    key,
                )
                ts = datetime.now(timezone.utc)
        else:
            ts = datetime.now(timezone.utc)

        # Build the structured payload (canonical shape for OntologyAI).
        structured_data: dict[str, Any] = {
            "record_type": "issue",
            "key": key,
            "project": project_key,
            "project_name": project_name,
            "summary": fields.get("summary", ""),
            "description": fields.get("description", ""),
            "status": status.get("name", ""),
            "priority": priority.get("name", ""),
            "assignee": assignee.get("displayName", "") if assignee else "",
            "labels": fields.get("labels", []),
            "issue_type": issuetype.get("name", ""),
            "parent_key": parent.get("key") if parent else None,
            "created": created_raw or "",
        }

        # SHA256 for exact dedup.
        checksum: str = self._compute_hash(structured_data)

        # Jira resource URI used as source reference.
        source_refs: list[str] = [f"jira://rest/api/3/issue/{key}"]

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

        Performs a lightweight probe by fetching project list.  The
        returned manifest advertises project-management capability,
        polling sync, and incremental-sync support.

        Returns
        -------
        ConnectorManifest
            Identity and capability metadata.
        """
        resp: TransportResponse = await self.transport.get(
            f"{self.base_url}/rest/api/3/project",
            headers=self._auth_headers(),
        )

        if resp.is_success:
            logger.info(
                "Jira API reachable — %s ms",
                resp.elapsed_ms,
            )
        else:
            logger.warning(
                "Jira connect health-check failed: %s %s",
                resp.status_code,
                resp.text[:200],
            )

        self._manifest = ConnectorManifest(
            name=self.connector_name,
            version="1.0.0",
            capabilities=[ConnectorCapability.PROJECT_MGMT],
            supported_objects=["issues", "projects"],
            sync_strategy=SyncStrategy.POLLING,
            supports_webhook=True,
            supports_polling=True,
            rate_limit_per_minute=100,
            auth_type="basic",
            supports_incremental_sync=True,
            deletion_strategy="soft_delete",
        )
        return self._manifest

    async def fetch(
        self,
        since: datetime | None = None,
    ) -> list[EvidenceRecord]:
        """Fetch all issues, with optional ``since`` filter.

        Paginates through ``GET /rest/api/3/search`` (using ``startAt`` /
        ``maxResults``) and converts each issue into a canonical
        ``EvidenceRecord``.  The ``hash`` field is the SHA256 of
        ``tenant_id + structured_data`` and can be used by the caller for
        exact dedup.

        Parameters
        ----------
        since:
            If provided, only issues whose ``created`` timestamp is strictly
            greater than *since* are returned.

        Returns
        -------
        list[EvidenceRecord]
            Canonical evidence records (may be empty on error).
        """
        records: list[EvidenceRecord] = []
        start_at: int = 0
        total: int | None = None

        while total is None or start_at < total:
            params: dict[str, str] = {
                "startAt": str(start_at),
                "maxResults": str(_PAGINATION_MAX_RESULTS),
            }

            resp: TransportResponse = await self.transport.get(
                f"{self.base_url}/rest/api/3/search",
                params=params,
                headers=self._auth_headers(),
            )

            # ── Error handling ────────────────────────────────────────
            if resp.status_code == 400:
                logger.warning(
                    "Jira bad request at startAt=%s: %s",
                    start_at,
                    resp.text[:200],
                )
                break

            if resp.status_code == 401:
                logger.error(
                    "Jira API returned 401 — credentials may be invalid or revoked",
                )
                break

            if not resp.is_success:
                logger.warning(
                    "Jira GET /rest/api/3/search returned %s at startAt=%s — %s",
                    resp.status_code,
                    start_at,
                    resp.text[:200],
                )
                break

            # ── Parse body ────────────────────────────────────────────
            body: dict | list | None = resp.json
            if not isinstance(body, dict):
                logger.warning("Jira API returned non-dict response body")
                break

            if total is None:
                total = body.get("total", 0)
                if total == 0:
                    logger.info("Jira search returned 0 total issues")
                    break

            issues: list[dict[str, Any]] = body.get("issues", [])
            if not issues:
                break

            for raw_issue in issues:
                record = self._issue_to_evidence(raw_issue)
                if record is None:
                    continue

                # Apply incremental-sync filter (only on ``created``).
                if since is not None and record.timestamp < since:
                    continue

                records.append(record)

            # ── Pagination ────────────────────────────────────────────
            start_at += _PAGINATION_MAX_RESULTS

        logger.info(
            "Jira fetch returned %s evidence record(s)%s",
            len(records),
            f" (since {since.isoformat()})" if since else "",
        )
        return records


__all__ = [
    "JiraConnector",
]

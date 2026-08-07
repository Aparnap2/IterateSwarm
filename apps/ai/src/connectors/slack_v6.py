"""V6 Slack Connector — fetches messages from Slack channels as EvidenceRecords.

Uses the ``Transport`` abstraction (``v6_base.py``) to talk to the Slack Web API.
For V6 testing this connects to a Mockoon server at ``http://localhost:3002``
that simulates the Slack API.

Usage::

    from src.connectors.base import ConnectorConfig
    from src.connectors.slack_v6 import SlackV6Connector

    config = ConnectorConfig(tenant_id="my-tenant")
    async with SlackV6Connector(config) as conn:
        manifest = await conn.connect()
        records = await conn.fetch()
        print(f"Got {len(records)} evidence records")
"""

from __future__ import annotations

import hashlib
import json
import logging
from collections.abc import Callable
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

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_SLACK_BASE_URL = "http://localhost:3002"


# ---------------------------------------------------------------------------
# SlackV6Connector
# ---------------------------------------------------------------------------


class SlackV6Connector(BaseV6Connector):
    """V6 Slack connector that produces ``EvidenceRecord``\\ s from Slack messages.

    Parameters
    ----------
    config:
        Connector configuration including tenant identity.
    transport:
        Injected HTTP transport.  Defaults to ``HttpxTransport()``.
    base_url:
        Base URL for the Slack API (defaults to the Mockoon server at
        ``http://localhost:3002``).
    """

    connector_name = "slack"

    def __init__(
        self,
        config: ConnectorConfig,
        transport: Transport | None = None,
        base_url: str = _SLACK_BASE_URL,
    ) -> None:
        super().__init__(config, transport)
        self._base_url = base_url.rstrip("/")
        self._user_cache: dict[str, str] = {}

    # ── connect ──────────────────────────────────────────────────────────

    async def connect(self) -> ConnectorManifest:
        """Return the connector manifest without a live handshake.

        For the Mockoon-based V6 test setup there is no real OAuth flow;
        the manifest is returned directly.
        """
        manifest = ConnectorManifest(
            name="slack",
            version="1.0.0",
            capabilities=[ConnectorCapability.MESSAGING],
            supported_objects=["messages", "channels", "users"],
            sync_strategy=SyncStrategy.POLLING,
            supports_webhook=True,
            supports_polling=True,
            rate_limit_per_minute=50,
            auth_type="oauth2",
            supports_incremental_sync=True,
            deletion_strategy="ignore",
        )
        self._manifest = manifest
        return manifest

    # ── fetch ────────────────────────────────────────────────────────────

    async def fetch(
        self,
        since: datetime | None = None,
    ) -> list[EvidenceRecord]:
        """Fetch Slack messages as ``EvidenceRecord``\\ s.

        Steps
        -----
        1. Build a user ID → name cache from ``GET /users.list``.
        2. Paginate through ``GET /conversations.list`` for all channels.
        3. For each channel, paginate through ``GET /conversations.history``.
        4. Build one ``EvidenceRecord`` per message.
        5. Optionally filter by *since* timestamp.
        """
        records: list[EvidenceRecord] = []

        # 1. Resolve users
        await self._load_users()

        # 2. Fetch all channels (with pagination)
        channels = await self._paginate(
            "/conversations.list",
            params={"limit": "100"},
            extract_items=lambda data: data.get("channels", []),
        )

        # 3. For each channel, fetch messages
        for channel in channels:
            channel_id = channel.get("id", "")
            channel_name = channel.get("name", channel_id)
            messages = await self._paginate(
                "/conversations.history",
                params={"channel": channel_id, "limit": "100"},
                extract_items=lambda data: data.get("messages", []),
            )

            for msg in messages:
                records.append(self._message_to_record(msg, channel_id, channel_name))

        # 4. Filter by *since* timestamp
        if since is not None:
            since_ts = since.timestamp()
            records = [r for r in records if r.timestamp.timestamp() >= since_ts]

        logger.info(
            "SlackV6Connector.fetch: %d records from %d channels",
            len(records),
            len(channels),
        )
        return records

    # ── attach_replies (nice-to-have) ────────────────────────────────────

    async def attach_replies(
        self,
        records: list[EvidenceRecord],
    ) -> list[EvidenceRecord]:
        """Fetch thread replies for messages that have a ``thread_ts``.

        For each record whose ``structured_data`` contains a ``thread_ts``,
        fetch replies via ``GET /conversations.replies`` and append them as
        new evidence records linked via ``entity_refs``.

        Parameters
        ----------
        records:
            The list of evidence records to scan for threaded messages.

        Returns
        -------
        list[EvidenceRecord]
            The original *records* list with reply evidence records appended.
        """
        reply_records: list[EvidenceRecord] = []

        for record in records:
            sd = record.structured_data
            thread_ts = sd.get("thread_ts")
            channel_id = sd.get("channel_id")
            if not thread_ts or not channel_id:
                continue

            replies = await self._paginate(
                "/conversations.replies",
                params={"channel": channel_id, "ts": str(thread_ts), "limit": "100"},
                extract_items=lambda data: data.get("messages", []),
            )

            for reply in replies:
                # The parent message is the first reply — skip it
                if reply.get("ts") == str(thread_ts):
                    continue
                rec = self._message_to_record(
                    reply, channel_id, sd.get("channel", channel_id)
                )
                rec.entity_refs = list(set(rec.entity_refs) | {record.id})
                reply_records.append(rec)

        records.extend(reply_records)
        return records

    # ── health ───────────────────────────────────────────────────────────

    async def health(self) -> dict[str, Any]:
        """Ping the Mockoon Slack API to check connectivity.

        Returns
        -------
        dict
            At minimum ``{"status": …, "latency_ms": …}``.
        """
        try:
            resp: TransportResponse = await self.transport.get(
                f"{self._base_url}/conversations.list",
                params={"limit": "1"},
            )
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

    # ── Internal helpers ─────────────────────────────────────────────────

    async def _load_users(self) -> None:
        """Build a user ID → display name cache from ``GET /users.list``."""
        if self._user_cache:
            return

        users = await self._paginate(
            "/users.list",
            params={"limit": "100"},
            extract_items=lambda data: data.get("members", []),
        )

        for user in users:
            uid = user.get("id", "")
            name = (
                user.get("real_name")
                or user.get("name")
                or user.get("profile", {}).get("email", "")
                or uid
            )
            self._user_cache[uid] = name

        logger.debug("Loaded %d users into cache", len(self._user_cache))

    def _resolve_user(self, user_id: str) -> str:
        """Return the display name for *user_id*, falling back to the raw ID."""
        return self._user_cache.get(user_id, user_id)

    def _message_to_record(
        self,
        msg: dict[str, Any],
        channel_id: str,
        channel_name: str,
    ) -> EvidenceRecord:
        """Convert a Slack message dict into an ``EvidenceRecord``.

        Parameters
        ----------
        msg:
            Raw Slack message object from the API.
        channel_id:
            The Slack channel ID (e.g. ``"C001"``).
        channel_name:
            The human-readable channel name (e.g. ``"engineering"``).

        Returns
        -------
        EvidenceRecord
            A fully populated evidence record ready for the pipeline.
        """
        ts_str = msg.get("ts", "0")
        ts_float = float(ts_str)
        timestamp = datetime.fromtimestamp(ts_float, tz=timezone.utc)
        user_id = msg.get("user", "unknown")
        user_name = self._resolve_user(user_id)
        text = msg.get("text", "")

        structured_data: dict[str, Any] = {
            "record_type": "message",
            "channel": channel_name,
            "channel_id": channel_id,
            "user": user_name,
            "text": text,
            "ts": ts_str,
            "reactions": [
                {"name": r["name"], "count": r["count"]}
                for r in msg.get("reactions", [])
            ],
            "reply_count": msg.get("reply_count", 0),
            "thread_ts": msg.get("thread_ts"),
        }

        # Build canonical hash: SHA256 of JSON(tenant_id + structured_data)
        canonical_json = json.dumps(
            [self.config.tenant_id, structured_data],
            sort_keys=True,
            ensure_ascii=False,
            default=str,
        )
        content_hash = hashlib.sha256(canonical_json.encode("utf-8")).hexdigest()

        source_refs = [f"slack://channels/{channel_id}/messages/{ts_str}"]

        return self._build_evidence(
            record_id=str(ulid.new()),
            structured_data=structured_data,
            source_refs=source_refs,
            confidence=0.95,
            timestamp=timestamp,
            raw_checksum=content_hash,
        )

    async def _paginate(
        self,
        path: str,
        params: dict[str, str],
        extract_items: Callable[[dict[str, Any]], list[dict[str, Any]]],
    ) -> list[dict[str, Any]]:
        """Paginate through a Slack API endpoint.

        Iterates through pages using ``response_metadata.next_cursor``
        until the cursor is null or empty.

        Parameters
        ----------
        path:
            API path (e.g. ``"/conversations.list"``).
        params:
            Query parameters sent on every request.
        extract_items:
            Callback that extracts the item list from a response dict.

        Returns
        -------
        list[dict]
            Aggregated items from all pages.
        """
        items: list[dict[str, Any]] = []
        cursor: str | None = None

        while True:
            request_params = dict(params)
            if cursor:
                request_params["cursor"] = cursor

            resp: TransportResponse = await self.transport.get(
                f"{self._base_url}{path}",
                params=request_params,
            )

            if not resp.is_success:
                logger.warning(
                    "Slack API error %s on %s: %s",
                    resp.status_code,
                    path,
                    (resp.text or "")[:200],
                )
                break

            if not resp.json or not isinstance(resp.json, dict):
                break

            data: dict[str, Any] = resp.json
            batch = extract_items(data)
            items.extend(batch)

            # Check for next page cursor
            metadata = data.get("response_metadata") or {}
            next_cursor = metadata.get("next_cursor")
            if not next_cursor:
                break
            cursor = str(next_cursor)

        return items


__all__ = [
    "SlackV6Connector",
]

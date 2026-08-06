"""V6 Salesforce Connector — OntologyAI CRM adapter.

Fetches Accounts, Opportunities, and Cases via the Salesforce SOQL API
(``/services/data/v58.0/query``).  Uses the V6 connector protocol defined
in ``v6_contract.py`` and the shared base from ``v6_base.py``.

Usage against Mockoon (default)::

    from src.connectors.base import ConnectorConfig
    from src.connectors.salesforce_v6 import SalesforceV6Connector

    config = ConnectorConfig(tenant_id="test-tenant")
    async with SalesforceV6Connector(config) as sf:
        manifest = await sf.connect()
        records = await sf.fetch()
        print(f"Fetched {len(records)} records")

Environment variables / credentials::

    config = ConnectorConfig(
        tenant_id="startup_abc",
        credentials={
            "instance_url": "https://your-instance.salesforce.com",
            "access_token": "00D...",
        },
    )
"""

from __future__ import annotations

import hashlib
import json
import logging
from datetime import datetime, timezone
from typing import Any

from src.connectors.base import ConnectorConfig
from src.connectors.transport import Transport
from src.connectors.v6_base import BaseV6Connector
from src.connectors.v6_contract import (
    ConnectorCapability,
    ConnectorManifest,
    SyncStrategy,
)
from src.entities.models import EvidenceRecord

logger = logging.getLogger(__name__)

# ── Field-name mappers (Salesforce API key → friendly key) ──────────────
# These translate Salesforce's camelCase and __c-suffixed field names into
# clean snake_case keys that the OntologyAI pipeline can work with.

_ACCOUNT_FIELD_MAP: dict[str, str] = {
    "Id": "id",
    "Name": "name",
    "Type": "type",
    "Status__c": "status",
}

_OPPORTUNITY_FIELD_MAP: dict[str, str] = {
    "Id": "id",
    "Name": "name",
    "StageName": "stage",
    "Amount": "amount",
    "CloseDate": "close_date",
}

_CASE_FIELD_MAP: dict[str, str] = {
    "Id": "id",
    "Subject": "subject",
    "Status": "status",
    "Priority": "priority",
    "AccountId": "account_id",
}


class SalesforceV6Connector(BaseV6Connector):
    """V6 Salesforce connector — fetches CRM objects via SOQL.

    Implements the ``V6Connector`` protocol from ``v6_contract.py``.

    Parameters
    ----------
    config:
        Connector configuration.  Set ``credentials["instance_url"]``
        to override the default Mockoon endpoint (``http://localhost:3004``).
        Set ``credentials["access_token"]`` for authenticated requests.
    transport:
        Injectable HTTP transport (defaults to ``HttpxTransport``).
        Pass ``MockTransport`` from ``transport.py`` for unit testing.
    """

    connector_name = "salesforce"

    def __init__(
        self,
        config: ConnectorConfig,
        transport: Transport | None = None,
    ) -> None:
        super().__init__(config, transport)
        self._base_url: str = config.credentials.get(
            "instance_url",
            "http://localhost:3004",
        )
        self._access_token: str = config.credentials.get("access_token", "")
        self._api_version: str = "v58.0"

    # ── Connector lifecycle ───────────────────────────────────────────────

    async def connect(self) -> ConnectorManifest:
        """Return the connector manifest.

        In production this would perform an OAuth2 handshake or verify the
        existing session token.  For the MVP we return the manifest directly
        and rely on HttpxTransport to handle retries.
        """
        manifest = ConnectorManifest(
            name="salesforce",
            version="1.0.0",
            capabilities=[ConnectorCapability.CRM],
            supported_objects=["accounts", "opportunities", "cases"],
            sync_strategy=SyncStrategy.POLLING,
            supports_webhook=True,
            supports_polling=True,
            rate_limit_per_minute=100,
            auth_type="oauth2",
            supports_incremental_sync=True,
            deletion_strategy="soft_delete",
        )
        self._manifest = manifest
        logger.info(
            "SalesforceV6Connector[%s]: connected, manifest=%s",
            self.config.tenant_id,
            manifest.name,
        )
        return manifest

    async def fetch(
        self,
        since: datetime | None = None,
    ) -> list[EvidenceRecord]:
        """Fetch Accounts, Opportunities, and Cases from Salesforce.

        Runs three SOQL queries sequentially and returns the merged results.
        The caller (pipeline stage 1) owns dedup via the ``hash`` field.

        Parameters
        ----------
        since:
            Ignored for MVP — the caller dedups by hash.
        """
        records: list[EvidenceRecord] = []

        soql_queries: list[tuple[str, str, float, dict[str, str]]] = [
            (
                "SELECT Id, Name, Type, Status__c FROM Account",
                "account",
                0.90,
                _ACCOUNT_FIELD_MAP,
            ),
            (
                "SELECT Id, Name, StageName, Amount, CloseDate FROM Opportunity",
                "opportunity",
                0.85,
                _OPPORTUNITY_FIELD_MAP,
            ),
            (
                "SELECT Id, Subject, Status, Priority, AccountId FROM Case",
                "case",
                0.95,
                _CASE_FIELD_MAP,
            ),
        ]

        for soql, object_type, confidence, field_map in soql_queries:
            try:
                object_records = await self._query_soql(
                    soql=soql,
                    object_type=object_type,
                    confidence=confidence,
                    field_map=field_map,
                )
                records.extend(object_records)
            except Exception:
                logger.exception(
                    "SalesforceV6Connector[%s]: failed to fetch %s",
                    self.config.tenant_id,
                    object_type,
                )

        return records

    # ── Internal helpers ─────────────────────────────────────────────────

    async def _query_soql(
        self,
        soql: str,
        object_type: str,
        confidence: float,
        field_map: dict[str, str],
    ) -> list[EvidenceRecord]:
        """Execute a SOQL query and return evidence records.

        Handles Salesforce SOQL pagination (``nextRecordsUrl`` / ``done``
        fields) so the connector is production-ready even though the Mockoon
        mock always returns ``done: true``.

        Error handling
        --------------
        * **400** — malformed SOQL; log and return empty.
        * **401** — expired / invalid session; log and return empty.
        * **429** — handled transparently by ``HttpxTransport`` (retry with
          exponential backoff).
        * **5xx** — handled by ``HttpxTransport`` (retry up to 3 times).
        """
        headers = self._build_headers()
        records: list[EvidenceRecord] = []

        query_url = f"{self._base_url}/services/data/{self._api_version}/query"
        params: dict[str, str] = {"q": soql}
        next_url: str | None = None

        while True:
            if next_url:
                url = f"{self._base_url}{next_url}"
                req_params: dict[str, str] | None = None
            else:
                url = query_url
                req_params = params

            resp = await self.transport.get(
                url,
                params=req_params,
                headers=headers,
            )

            if resp.status_code == 400:
                logger.warning(
                    "SalesforceV6Connector[%s]: bad SOQL for %s — %s",
                    self.config.tenant_id,
                    object_type,
                    resp.text[:300],
                )
                return []

            if resp.status_code == 401:
                logger.warning(
                    "SalesforceV6Connector[%s]: auth error fetching %s — %s",
                    self.config.tenant_id,
                    object_type,
                    resp.text[:300],
                )
                return []

            if not resp.is_success:
                logger.error(
                    "SalesforceV6Connector[%s]: HTTP %s fetching %s — %s",
                    self.config.tenant_id,
                    resp.status_code,
                    object_type,
                    resp.text[:200],
                )
                return []

            body = resp.json
            if not isinstance(body, dict):
                logger.warning(
                    "SalesforceV6Connector[%s]: non-dict response for %s",
                    self.config.tenant_id,
                    object_type,
                )
                return []

            raw_records: list[dict[str, Any]] = body.get("records", [])
            for raw in raw_records:
                record = self._build_evidence_record(
                    raw=raw,
                    object_type=object_type,
                    confidence=confidence,
                    field_map=field_map,
                )
                records.append(record)

            # Check for next page — Salesforce sets done=false when there
            # are more records and provides a nextRecordsUrl to follow.
            next_url = body.get("nextRecordsUrl")
            if not next_url or body.get("done", True):
                break

        return records

    def _build_evidence_record(
        self,
        raw: dict[str, Any],
        object_type: str,
        confidence: float,
        field_map: dict[str, str],
    ) -> EvidenceRecord:
        """Build a single ``EvidenceRecord`` from a raw Salesforce record.

        Steps
        -----
        1. Strip Salesforce ``attributes`` metadata.
        2. Map Salesforce field names → friendly keys via *field_map*.
        3. Build ``source_refs`` (``salesforce://{object_type}/{Id}``).
        4. Compute ``hash`` = SHA256 of canonical JSON(tenant_id + data).
        5. Assemble the ``EvidenceRecord`` via ``_build_evidence()``.
        """
        # Remove Salesforce system attributes
        clean = {k: v for k, v in raw.items() if not k.startswith("attributes")}

        # Map to friendly keys
        structured_data: dict[str, Any] = {"record_type": object_type}
        for sf_key, friendly_key in field_map.items():
            if sf_key in clean:
                structured_data[friendly_key] = clean[sf_key]

        sf_id: str = clean.get("Id", "")
        source_refs: list[str] = [f"salesforce://{object_type}/{sf_id}"]

        # Compute hash: SHA256 of canonical JSON(tenant_id + structured_data)
        canonical = json.dumps(
            {"tenant_id": self.config.tenant_id, "data": structured_data},
            sort_keys=True,
            separators=(",", ":"),
        )
        record_hash = hashlib.sha256(canonical.encode()).hexdigest()

        # Build via the shared helper, then patch the hash
        record = self._build_evidence(
            record_id=sf_id or f"sf-{object_type}-unknown",
            structured_data=structured_data,
            source_refs=source_refs,
            timestamp=datetime.now(timezone.utc),
            confidence=confidence,
        )
        record.hash = record_hash

        return record

    def _build_headers(self) -> dict[str, str]:
        """Build HTTP headers with optional bearer-token auth."""
        headers: dict[str, str] = {
            "Content-Type": "application/json",
        }
        if self._access_token:
            headers["Authorization"] = f"Bearer {self._access_token}"
        return headers

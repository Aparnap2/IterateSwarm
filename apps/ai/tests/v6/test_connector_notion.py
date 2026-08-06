"""Smoke tests for ``NotionConnector`` against the live Mockoon server.

These tests require the Mockoon container on ``http://localhost:3001``
to be running (see ``docker-compose.yml``).  They exercise the full
``connect()`` → ``fetch()`` → ``close()`` lifecycle and verify that
records are canonical ``EvidenceRecord`` instances.
"""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from src.connectors.base import ConnectorConfig
from src.connectors.notion import NotionConnector
from src.connectors.transport import HttpxTransport
from src.entities.models import EvidenceRecord


@pytest.fixture
def notion_config() -> ConnectorConfig:
    """Return a ``ConnectorConfig`` pointed at the Mockoon server."""
    return ConnectorConfig(
        tenant_id="test-tenant",
        credentials={
            "base_url": "http://localhost:3001",
            "api_token": "mock-token",
        },
        mock_mode=False,
    )


@pytest.fixture
async def notion_connector(notion_config: ConnectorConfig) -> NotionConnector:
    """Return an open ``NotionConnector`` ready for testing."""
    connector = NotionConnector(notion_config, transport=HttpxTransport())
    yield connector
    await connector.close()


# ── connect() ─────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_notion_connector_connect(notion_connector: NotionConnector) -> None:
    """``connect()`` returns a manifest with correct identity."""
    manifest = await notion_connector.connect()

    assert manifest.name == "notion"
    assert manifest.version == "0.6.0"
    assert "pages" in manifest.supported_objects
    assert manifest.supports_incremental_sync is True
    assert manifest.supports_polling is True
    assert manifest.supports_webhook is False
    assert manifest.auth_type == "api_key"


# ── fetch() — happy path ──────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_notion_connector_fetch_all(notion_connector: NotionConnector) -> None:
    """``fetch()`` returns 6 records (all pages in the mock server)."""
    await notion_connector.connect()
    records = await notion_connector.fetch()

    assert len(records) == 6, f"Expected 6 records, got {len(records)}"

    for r in records:
        assert isinstance(r, EvidenceRecord)
        assert r.source == "notion"
        assert r.tenant_id == "test-tenant"
        assert r.structured_data["record_type"] == "page"
        # Every record must have a non-trivial SHA256 hash.
        assert len(r.hash) == 64
        assert r.hash != "0" * 64


@pytest.mark.asyncio
async def test_notion_connector_fetch_structure(
    notion_connector: NotionConnector,
) -> None:
    """Each evidence record has the expected fields."""
    await notion_connector.connect()
    records = await notion_connector.fetch()

    for r in records:
        sd = r.structured_data
        assert "external_id" in sd
        assert "title" in sd
        assert "tags" in sd
        assert isinstance(sd["tags"], list)
        assert "status" in sd
        assert "owner" in sd
        assert len(r.source_refs) == 1
        assert r.source_refs[0].startswith("notion://pages/")


# ── fetch() — incremental sync ────────────────────────────────────────────


@pytest.mark.asyncio
async def test_notion_connector_fetch_with_since(
    notion_connector: NotionConnector,
) -> None:
    """``fetch(since=...)`` filters pages edited after the given timestamp.

    Mock server timestamps range from 2026-07-18 to 2026-07-25.
    """
    await notion_connector.connect()

    # Only pages edited on or after July 23.
    since = datetime(2026, 7, 23, tzinfo=timezone.utc)
    records = await notion_connector.fetch(since=since)

    # Only "Q3 OKRs" (2026-07-25) should pass the filter.
    assert len(records) == 1, f"Expected 1 record since {since}, got {len(records)}"
    assert records[0].structured_data["title"] == "Q3 OKRs"


@pytest.mark.asyncio
async def test_notion_connector_fetch_with_since_no_results(
    notion_connector: NotionConnector,
) -> None:
    """``fetch(since=...)`` returns empty when all pages are older."""
    await notion_connector.connect()

    # Well past all mock timestamps.
    since = datetime(2026, 7, 31, tzinfo=timezone.utc)
    records = await notion_connector.fetch(since=since)

    assert len(records) == 0


# ── search() ──────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_notion_connector_search(notion_connector: NotionConnector) -> None:
    """``search()`` returns matching results from ``POST /search``."""
    await notion_connector.connect()
    records = await notion_connector.search("engineering")

    # The mock /search returns all pages; at least 1 should be present.
    assert len(records) >= 1
    # All returned records must still be valid evidence.
    for r in records:
        assert isinstance(r, EvidenceRecord)


# ── health() ──────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_notion_connector_health(notion_connector: NotionConnector) -> None:
    """``health()`` returns a status dict with required keys."""
    status = await notion_connector.health()

    assert "status" in status
    assert "latency_ms" in status
    assert status.get("connector") == "notion"
    # The default health() pings a mockoon endpoint; accept any valid status.
    assert status["status"] in ("healthy", "degraded", "disconnected")


# ── close() ───────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_notion_connector_close(notion_config: ConnectorConfig) -> None:
    """``close()`` is idempotent and does not error on double close."""
    connector = NotionConnector(notion_config, transport=HttpxTransport())
    await connector.close()  # first call
    await connector.close()  # idempotent


# ── Error handling ────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_notion_connector_connection_error_returns_empty() -> None:
    """A connection error triggers an empty list (graceful degradation)."""
    bad_config = ConnectorConfig(
        tenant_id="test-tenant",
        credentials={
            "base_url": "http://localhost:9999",  # nothing listening here
            "api_token": "mock-token",
        },
    )
    connector = NotionConnector(bad_config, transport=HttpxTransport())
    await connector.connect()
    records = await connector.fetch()
    assert records == []
    await connector.close()

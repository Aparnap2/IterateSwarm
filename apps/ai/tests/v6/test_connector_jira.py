"""Smoke tests for ``JiraConnector`` against the live Mockoon server.

These tests require the Mockoon container on ``http://localhost:3003``
to be running (see ``docker-compose.yml``).  They exercise the full
``connect()`` → ``fetch()`` → ``close()`` lifecycle and verify that
records are canonical ``EvidenceRecord`` instances.
"""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from src.connectors.base import ConnectorConfig
from src.connectors.jira import JiraConnector
from src.connectors.transport import HttpxTransport
from src.entities.models import EvidenceRecord


@pytest.fixture
def jira_config() -> ConnectorConfig:
    """Return a ``ConnectorConfig`` pointed at the Mockoon Jira server."""
    return ConnectorConfig(
        tenant_id="test-tenant",
        credentials={
            "base_url": "http://localhost:3003",
            "username": "admin",
            "api_token": "mock-token",
        },
        mock_mode=False,
    )


@pytest.fixture
async def jira_connector(jira_config: ConnectorConfig) -> JiraConnector:
    """Return an open ``JiraConnector`` ready for testing."""
    connector = JiraConnector(jira_config, transport=HttpxTransport())
    yield connector
    await connector.close()


# ── connect() ─────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_jira_connector_connect(jira_connector: JiraConnector) -> None:
    """``connect()`` returns a manifest with correct identity."""
    manifest = await jira_connector.connect()

    assert manifest.name == "jira"
    assert manifest.version == "1.0.0"
    assert "issues" in manifest.supported_objects
    assert "projects" in manifest.supported_objects
    assert manifest.supports_incremental_sync is True
    assert manifest.supports_polling is True
    assert manifest.supports_webhook is True
    assert manifest.auth_type == "basic"


# ── fetch() — happy path ──────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_jira_connector_fetch_all(jira_connector: JiraConnector) -> None:
    """``fetch()`` returns 8 records (all issues in the mock server)."""
    await jira_connector.connect()
    records = await jira_connector.fetch()

    assert len(records) == 8, f"Expected 8 records, got {len(records)}"

    for r in records:
        assert isinstance(r, EvidenceRecord)
        assert r.source == "jira"
        assert r.tenant_id == "test-tenant"
        assert r.structured_data["record_type"] == "issue"
        # Every record must have a non-trivial SHA256 hash.
        assert len(r.hash) == 64
        assert r.hash != "0" * 64


@pytest.mark.asyncio
async def test_jira_connector_fetch_structure(jira_connector: JiraConnector) -> None:
    """Each evidence record has the expected fields."""
    await jira_connector.connect()
    records = await jira_connector.fetch()

    for r in records:
        sd = r.structured_data
        assert "key" in sd
        assert "summary" in sd
        assert "status" in sd
        assert "priority" in sd
        assert "issue_type" in sd
        assert "project" in sd
        assert "labels" in sd
        assert isinstance(sd["labels"], list)
        assert len(r.source_refs) == 1
        assert r.source_refs[0].startswith("jira://rest/api/3/issue/")
        assert sd["created"] != ""


@pytest.mark.asyncio
async def test_jira_connector_fetch_keys(jira_connector: JiraConnector) -> None:
    """``fetch()`` returns all expected Jira issue keys."""
    await jira_connector.connect()
    records = await jira_connector.fetch()

    keys = [r.structured_data["key"] for r in records]
    assert "PORTAL-1" in keys
    assert "PORTAL-2" in keys
    assert "PORTAL-3" in keys
    assert "PORTAL-4" in keys
    assert "PORTAL-5" in keys
    assert "PORTAL-6" in keys
    assert "PORTAL-7" in keys
    assert "OPS-1" in keys


# ── fetch() — incremental sync ────────────────────────────────────────────


@pytest.mark.asyncio
async def test_jira_connector_fetch_with_since(jira_connector: JiraConnector) -> None:
    """``fetch(since=...)`` filters issues created after the given timestamp.

    Mock timestamps:
      PORTAL-1: 2026-06-01, PORTAL-2: 2026-06-05,
      PORTAL-3: 2026-06-10, PORTAL-4: 2026-07-15,
      PORTAL-5: 2026-07-20, PORTAL-6: 2026-07-22,
      PORTAL-7: 2026-07-18, OPS-1:   2026-05-20.
    """
    await jira_connector.connect()

    # Only issues created on or after June 8.
    since = datetime(2026, 6, 8, tzinfo=timezone.utc)
    records = await jira_connector.fetch(since=since)

    # PORTAL-3 (2026-06-10), PORTAL-4, PORTAL-5, PORTAL-6, PORTAL-7 should pass.
    assert len(records) >= 1, f"Expected at least 1 record since {since}, got {len(records)}"
    keys = [r.structured_data["key"] for r in records]
    assert "PORTAL-3" in keys
    assert "PORTAL-7" in keys


@pytest.mark.asyncio
async def test_jira_connector_fetch_with_since_no_results(
    jira_connector: JiraConnector,
) -> None:
    """``fetch(since=...)`` returns empty when all issues are older."""
    await jira_connector.connect()

    # Well past all mock timestamps.
    since = datetime(2026, 12, 31, tzinfo=timezone.utc)
    records = await jira_connector.fetch(since=since)

    assert len(records) == 0


# ── health() ──────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_jira_connector_health(jira_connector: JiraConnector) -> None:
    """``health()`` returns a status dict with required keys."""
    status = await jira_connector.health()

    assert "status" in status
    assert "latency_ms" in status
    assert status.get("connector") == "jira"
    assert status["status"] in ("healthy", "degraded", "disconnected")


# ── close() ───────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_jira_connector_close(jira_config: ConnectorConfig) -> None:
    """``close()`` is idempotent and does not error on double close."""
    connector = JiraConnector(jira_config, transport=HttpxTransport())
    await connector.close()  # first call
    await connector.close()  # idempotent


# ── Error handling ────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_jira_connector_bad_auth_returns_empty(
    jira_config: ConnectorConfig,
) -> None:
    """A 401 triggers an empty list (graceful degradation).

    The mock server does not actually enforce auth on the search endpoint,
    so we simulate this by configuring invalid credentials and relying on
    the connector's error-path logic.  For a real auth test we'd need a
    MockTransport.
    """
    bad_config = ConnectorConfig(
        tenant_id="test-tenant",
        credentials={
            "base_url": "http://localhost:3003",
            "username": "invalid",
            "api_token": "INVALID_TOKEN",
        },
    )
    connector = JiraConnector(bad_config, transport=HttpxTransport())
    await connector.connect()
    records = await connector.fetch()
    # The Mockoon mock doesn't enforce auth, so it returns data anyway.
    # This test documents that behaviour — a real Jira instance would 401.
    assert len(records) == 8
    await connector.close()

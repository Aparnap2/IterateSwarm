"""Smoke tests for SlackV6Connector — runs against the real Mockoon server.

Usage::

    uv run pytest tests/v6/test_connector_slack.py -x -v 2>&1 | tail -30
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from src.connectors.base import ConnectorConfig
from src.connectors.slack_v6 import SlackV6Connector


# ── Fixtures ──────────────────────────────────────────────────────────────


@pytest.fixture
def connector() -> SlackV6Connector:
    """Return a SlackV6Connector pointed at the Mockoon server."""
    config = ConnectorConfig(tenant_id="test-tenant")
    return SlackV6Connector(config)


# ── Tests ─────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_slack_connector_fetch(connector: SlackV6Connector) -> None:
    """Fetch should return EvidenceRecords for every Slack message."""
    records = await connector.fetch()

    assert len(records) > 0, "Expected at least one evidence record"
    assert all(r.source == "slack" for r in records), "All sources must be 'slack'"
    assert all(r.structured_data["record_type"] == "message" for r in records), (
        "All records must be of record_type 'message'"
    )
    assert all(r.source_type == "connector" for r in records), (
        "All source_type must be 'connector'"
    )


@pytest.mark.asyncio
async def test_slack_connector_fetch_since(connector: SlackV6Connector) -> None:
    """Fetch with ``since`` should filter out older messages."""
    # Use a timestamp far in the future — should return zero records
    far_future = datetime.now(timezone.utc) + timedelta(days=365)
    records = await connector.fetch(since=far_future)

    assert len(records) == 0, "Expected no records with a future 'since' timestamp"


@pytest.mark.asyncio
async def test_slack_connector_fetch_hashes_unique(connector: SlackV6Connector) -> None:
    """Every evidence record should have a unique SHA256 hash."""
    records = await connector.fetch()
    hashes = [r.hash for r in records]

    assert len(hashes) == len(set(hashes)), "Duplicate hashes detected"


@pytest.mark.asyncio
async def test_slack_connector_fetch_source_refs(connector: SlackV6Connector) -> None:
    """Every record should have a valid ``slack://`` source_ref."""
    records = await connector.fetch()

    for r in records:
        assert len(r.source_refs) > 0, "Expected at least one source_ref"
        ref = r.source_refs[0]
        assert ref.startswith("slack://"), (
            f"source_ref must start with slack://, got {ref}"
        )
        assert "messages" in ref, f"source_ref must contain 'messages', got {ref}"


@pytest.mark.asyncio
async def test_slack_connector_connect(connector: SlackV6Connector) -> None:
    """connect() should return the expected manifest."""
    manifest = await connector.connect()

    assert manifest.name == "slack"
    assert manifest.version == "1.0.0"
    assert "messages" in manifest.supported_objects
    assert "channels" in manifest.supported_objects
    assert "users" in manifest.supported_objects
    assert manifest.rate_limit_per_minute == 50
    assert manifest.auth_type == "oauth2"
    assert manifest.supports_incremental_sync is True


@pytest.mark.asyncio
async def test_slack_connector_health(connector: SlackV6Connector) -> None:
    """health() should return 'healthy' against the Mockoon server."""
    result = await connector.health()

    assert result["status"] == "healthy"
    assert result["latency_ms"] >= 0
    assert result["connector"] == "slack"


@pytest.mark.asyncio
async def test_slack_connector_fetch_users_resolved(
    connector: SlackV6Connector,
) -> None:
    """User IDs in messages should be resolved to real names."""
    records = await connector.fetch()

    for r in records:
        user = r.structured_data.get("user", "")
        # User should be a resolved name, not a raw "U001" style ID
        assert not user.startswith("U00"), f"User appears unresolved: {user!r}"
        assert user, "User field should not be empty"


@pytest.mark.asyncio
async def test_slack_connector_close(connector: SlackV6Connector) -> None:
    """close() should be idempotent and not raise."""
    # close twice to prove idempotency
    await connector.close()
    await connector.close()

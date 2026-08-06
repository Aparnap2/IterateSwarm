"""Smoke tests for SalesforceV6Connector against the Mockoon mock server.

Prerequisites
-------------
* Mockoon Salesforce mock must be running on ``http://localhost:3004``
  (started via Docker compose).
* No Salesforce credentials are needed — the connector defaults to the
  Mockoon endpoint when ``instance_url`` is not provided.

Run::

    uv run pytest tests/v6/test_connector_salesforce.py -x -v 2>&1 | tail -30
"""

from __future__ import annotations

import pytest

from src.connectors.base import ConnectorConfig
from src.connectors.salesforce_v6 import SalesforceV6Connector


@pytest.mark.asyncio
async def test_salesforce_connector_fetch() -> None:
    """Connect to Mockoon and verify all 3 object types are returned.

    Asserts
    -------
    * At least one evidence record is returned.
    * Every record has ``source == "salesforce"``.
    * The three expected ``record_type`` values are present: account,
      opportunity, case.
    """
    config = ConnectorConfig(tenant_id="test-tenant")
    connector = SalesforceV6Connector(config)
    records = await connector.fetch()

    assert len(records) > 0, "Expected at least one evidence record"

    all_salesforce = all(r.source == "salesforce" for r in records)
    assert all_salesforce, "All records must have source='salesforce'"

    types = {r.structured_data["record_type"] for r in records}
    assert "account" in types, "Expected account records"
    assert "opportunity" in types, "Expected opportunity records"
    assert "case" in types, "Expected case records"

    await connector.close()


@pytest.mark.asyncio
async def test_salesforce_connector_connect() -> None:
    """Verify the manifest returned by ``connect()``.

    Asserts
    -------
    * ``name == "salesforce"`` and ``version == "1.0.0"``.
    * CRM capability is present.
    * All 3 supported objects are listed.
    * Polling and webhook flags are set correctly.
    """
    config = ConnectorConfig(tenant_id="test-tenant")
    connector = SalesforceV6Connector(config)
    manifest = await connector.connect()

    assert manifest.name == "salesforce"
    assert manifest.version == "1.0.0"
    capabilities = {c.value for c in manifest.capabilities}
    assert "crm" in capabilities, "Expected CRM capability"
    assert "accounts" in manifest.supported_objects
    assert "opportunities" in manifest.supported_objects
    assert "cases" in manifest.supported_objects
    assert manifest.supports_polling is True
    assert manifest.supports_webhook is True
    assert manifest.auth_type == "oauth2"
    assert manifest.rate_limit_per_minute == 100

    await connector.close()


@pytest.mark.asyncio
async def test_salesforce_connector_evidence_structure() -> None:
    """Verify structural integrity of every evidence record.

    Asserts
    -------
    * ``hash`` is a real SHA256 (not the all-zeros placeholder).
    * ``source_refs`` are non-empty and use the ``salesforce://`` scheme.
    * ``confidence`` is in [0.0, 1.0].
    * ``structured_data`` contains the ``record_type`` key.
    """
    config = ConnectorConfig(tenant_id="test-tenant")
    connector = SalesforceV6Connector(config)
    records = await connector.fetch()

    for record in records:
        # Hash must be properly computed (not the base default placeholder)
        assert record.hash, "Hash must not be empty"
        assert record.hash != "0" * 64, (
            "Hash should be a real SHA256, not the base-class placeholder"
        )
        assert len(record.hash) == 64, "Hash must be 64 hex chars (SHA256)"

        # Source refs
        assert len(record.source_refs) > 0, "Expected at least one source_ref"
        assert record.source_refs[0].startswith("salesforce://"), (
            "source_ref must use salesforce:// scheme"
        )

        # Confidence in valid range
        assert 0.0 <= record.confidence <= 1.0, (
            f"Confidence {record.confidence} out of [0, 1] range"
        )

        # structured_data must contain record_type
        assert "record_type" in record.structured_data, (
            "structured_data must contain record_type"
        )

    await connector.close()


@pytest.mark.asyncio
async def test_salesforce_connector_count_breakdown() -> None:
    """Verify expected record counts per object type.

    The Mockoon mock returns:
    * 5 accounts
    * 7 opportunities
    * 5 cases
    """
    config = ConnectorConfig(tenant_id="test-tenant")
    connector = SalesforceV6Connector(config)
    records = await connector.fetch()

    accounts = [r for r in records if r.structured_data["record_type"] == "account"]
    opportunities = [
        r for r in records if r.structured_data["record_type"] == "opportunity"
    ]
    cases = [r for r in records if r.structured_data["record_type"] == "case"]

    assert len(accounts) >= 5, f"Expected >=5 accounts, got {len(accounts)}"
    assert len(opportunities) >= 7, (
        f"Expected >=7 opportunities, got {len(opportunities)}"
    )
    assert len(cases) >= 5, f"Expected >=5 cases, got {len(cases)}"


@pytest.mark.asyncio
async def test_salesforce_connector_field_mapping() -> None:
    """Verify Salesforce field names are mapped to friendly keys.

    Account ``Status__c`` → ``status``
    Opportunity ``StageName`` → ``stage``
    Case ``AccountId`` → ``account_id``
    """
    config = ConnectorConfig(tenant_id="test-tenant")
    connector = SalesforceV6Connector(config)
    records = await connector.fetch()

    for record in records:
        sd = record.structured_data
        rtype = sd.get("record_type")
        if rtype == "account":
            # Status__c should be mapped to "status"
            assert "status" in sd, "Account should have mapped 'status' field"
            assert sd.get("id"), "Account should have an 'id' field"
        elif rtype == "opportunity":
            # StageName should be mapped to "stage"
            assert "stage" in sd, "Opportunity should have mapped 'stage' field"
            assert "amount" in sd, "Opportunity should have 'amount' field"
        elif rtype == "case":
            # AccountId should be mapped to "account_id"
            assert "account_id" in sd, "Case should have mapped 'account_id' field"
            assert "subject" in sd, "Case should have 'subject' field"

    await connector.close()

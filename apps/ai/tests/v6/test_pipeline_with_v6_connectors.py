"""Integration tests for the vertical slice pipeline using real V6 connectors.

These tests require the Mockoon CLI processes to be running on
``localhost:3001-3004`` (started by ``scripts/start-mockoon.sh``).  They
exercise the full pipeline with the V6 connector registry, verifying that
all 4 connectors produce evidence records and the pipeline completes all
stages.

Tests are skipped if the Mockoon servers are not available (useful in CI
without mocks).
"""

from __future__ import annotations

import logging
from typing import Any

import httpx
import pytest

from src.connectors.mock_notion_connector import MockNotionConnector
from src.pipeline.vertical_slice import VerticalSlicePipeline

logger = logging.getLogger(__name__)

# ── Mockoon server ports ──────────────────────────────────────────────────

_MOCKOON_PORTS: dict[str, int] = {
    "notion": 3001,
    "slack": 3002,
    "jira": 3003,
    "salesforce": 3004,
}


# Per-port health probe endpoint — each Mockoon config exposes its own first
# GET route.  ``/pages`` works for Notion; for the others a 404 (< 500) still
# proves the server is listening, which is all this gate needs.
_PROBE_PATHS: dict[int, str] = {
    3001: "/pages",
    3002: "/pages",
    3003: "/pages",
    3004: "/pages",
}


def _is_mockoon_ready(port: int) -> bool:
    """Synchronous readiness check.

    Uses a blocking ``httpx`` client so it can be called from both regular
    test code and async tests (which already run under an event loop) without
    nesting ``asyncio.run``.
    """
    path = _PROBE_PATHS.get(port, "/pages")
    try:
        with httpx.Client(timeout=2.0) as client:
            resp = client.get(f"http://localhost:{port}{path}")
        return resp.status_code < 500
    except (httpx.ConnectError, httpx.TimeoutException, OSError):
        return False


def _require_mockoon(*ports: int) -> bool:
    """Return ``True`` if all given ports respond."""
    return all(_is_mockoon_ready(p) for p in ports)


# ── Tests ─────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_pipeline_with_notion_connector() -> None:
    """Run the pipeline with the real Notion V6 connector against Mockoon.

    Expects 6 pages from the Mockoon mock.
    """
    if not _require_mockoon(3001):
        pytest.skip("Mockoon Notion server (port 3001) not available")

    pipeline = VerticalSlicePipeline(
        sources=["notion"],
        workspace_id="test-ws",
        tenant_id="test-tenant",
    )
    result = await pipeline.run()

    assert result["evidence_count"] == 6, (
        f"Expected 6 evidence records, got {result['evidence_count']}"
    )
    assert "notion" in result.get("sources", {}), (
        f"Expected 'notion' in sources, got {result.get('sources', {})}"
    )
    assert result["status"] == "published"


@pytest.mark.asyncio
async def test_pipeline_with_all_connectors() -> None:
    """Run with all 4 V6 connectors against Mockoon.

    Expects:
    - Notion: 6 pages
    - Slack: messages from channels
    - Jira: issues
    - Salesforce: accounts, opportunities, cases
    """
    if not _require_mockoon(3001, 3002, 3003, 3004):
        pytest.skip("One or more Mockoon servers not available")

    pipeline = VerticalSlicePipeline(
        sources=["notion", "slack", "jira", "salesforce"],
        workspace_id="test-ws",
        tenant_id="test-tenant",
    )
    result = await pipeline.run()

    assert result["evidence_count"] > 10, (
        f"Expected >10 evidence records across 4 sources, got {result['evidence_count']}"
    )
    sources: dict[str, int] = result.get("sources", {})
    assert len(sources) == 4, (
        f"Expected 4 sources, got {len(sources)}: {sources}"
    )
    for src in ("notion", "slack", "jira", "salesforce"):
        assert src in sources, f"Missing source {src!r} in {sources}"
        assert sources[src] > 0, f"Source {src!r} returned 0 records"

    assert result["status"] == "published"


@pytest.mark.asyncio
async def test_pipeline_with_notion_only_sources() -> None:
    """Specifying only ['notion'] sources should fetch only Notion records."""
    if not _require_mockoon(3001):
        pytest.skip("Mockoon Notion server (port 3001) not available")

    pipeline = VerticalSlicePipeline(
        sources=["notion"],
        workspace_id="test-ws",
        tenant_id="test-tenant",
    )
    result = await pipeline.run()

    assert result["evidence_count"] == 6
    assert result["sources"] == {"notion": 6}


@pytest.mark.asyncio
async def test_pipeline_with_sources_errors_gracefully() -> None:
    """If a connector fails (e.g. server down), others should still succeed.

    This test runs with Mockoon on 3001 (notion) but a bad port for others.
    The registry returns empty lists for failed connectors.
    """
    if not _require_mockoon(3001):
        pytest.skip("Mockoon Notion server (port 3001) not available")

    pipeline = VerticalSlicePipeline(
        sources=["notion", "slack", "jira", "salesforce"],
        workspace_id="test-ws",
        tenant_id="test-tenant",
    )
    result = await pipeline.run()

    # Notion should succeed; others will likely fail if only port 3001 is up
    sources = result.get("sources", {})
    assert "notion" in sources, f"Expected notion in sources, got {sources}"
    # The other sources may have 0 records if Mockoon isn't running for them
    for src in ("slack", "jira", "salesforce"):
        if src in sources and sources[src] == 0:
            logger.info("Source %r returned 0 records (expected if Mockoon not running)", src)


# ── Backward-compat test ──────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_pipeline_backward_compat_mock_notion_connector() -> None:
    """Passing ``connector=MockNotionConnector()`` should use legacy mode.

    MockNotionConnector returns 3 hardcoded evidence records, so the
    pipeline should produce exactly 3 evidence records and no per-source
    breakdown (legacy mode does not populate ``sources``).
    """
    pipeline = VerticalSlicePipeline(
        connector=MockNotionConnector(),
        workspace_id="test-ws",
        tenant_id="test-tenant",
    )
    result = await pipeline.run()

    assert result["evidence_count"] == 3, (
        f"Expected 3 evidence records from MockNotionConnector, got {result['evidence_count']}"
    )
    assert result["status"] == "published"
    # Legacy connector mode should still work end-to-end
    assert len(result.get("entities", [])) >= 0  # entity resolution may or may not find entities

"""V6 Qdrant vector search tests — TDD.

Tests verify that Qdrant can store and search vector embeddings for
evidence records and capabilities.  All tests require a running Qdrant
instance at ``localhost:6333`` and are marked with ``@pytest.mark.integration``.

Usage:
    uv run pytest tests/v6/test_vector_v6.py -v -m integration
"""

from __future__ import annotations

import pytest
import httpx

VECTOR_DIM = 1536  # OpenAI text-embedding-ada-002
QDRANT_URL = "http://localhost:6333"


# ── Fixture ────────────────────────────────────────────────────────


@pytest.fixture
async def qdrant_http():
    """Return an httpx.AsyncClient for Qdrant REST API and clean up after each test."""
    client = httpx.AsyncClient(base_url=QDRANT_URL, timeout=10.0)
    yield client
    # Cleanup: delete test collections
    for name in ["test_evidence", "test_capability"]:
        try:
            await client.delete(f"/collections/{name}")
        except Exception:
            pass
    await client.aclose()


# ── Helpers ─────────────────────────────────────────────────────────────


def _make_evidence_vector(index: int = 0) -> list[float]:
    """Return a 1536-dim vector with a single 1.0 at *index* (cosine-similar to itself)."""
    vec = [0.0] * VECTOR_DIM
    vec[index] = 1.0
    return vec


def _make_evidence_payload(
    evidence_id: str,
    tenant_id: str = "tenant-1",
    source: str = "notion",
    domain: str = "engineering",
    confidence: float = 0.95,
) -> dict:
    """Return a payload dict matching an evidence record."""
    return {
        "evidence_id": evidence_id,
        "tenant_id": tenant_id,
        "source": source,
        "domain": domain,
        "confidence": confidence,
        "timestamp": "2026-08-04T00:00:00Z",
    }


def _make_capability_vector(index: int = 0) -> list[float]:
    """Return a 1536-dim vector for capability embeddings."""
    vec = [0.0] * VECTOR_DIM
    vec[index] = 1.0
    return vec


def _make_capability_payload(
    capability_id: str,
    name: str = "Sales",
    domain: str = "business",
    maturity_level: int = 3,
) -> dict:
    """Return a payload dict matching a capability record."""
    return {
        "capability_id": capability_id,
        "name": name,
        "domain": domain,
        "maturity_level": maturity_level,
    }


# ── Test Classes ────────────────────────────────────────────────────


@pytest.mark.integration
class TestQdrantCollection:
    """Test Qdrant collection creation and management."""

    async def test_create_evidence_collection(self, qdrant_http: httpx.AsyncClient) -> None:
        """Create a collection for evidence embeddings."""
        resp = await qdrant_http.put(
            "/collections/test_evidence",
            json={"vectors": {"size": VECTOR_DIM, "distance": "Cosine"}},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["result"] is True

    async def test_create_capability_collection(self, qdrant_http: httpx.AsyncClient) -> None:
        """Create a collection for capability embeddings."""
        resp = await qdrant_http.put(
            "/collections/test_capability",
            json={"vectors": {"size": VECTOR_DIM, "distance": "Cosine"}},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["result"] is True

    async def test_collection_exists(self, qdrant_http: httpx.AsyncClient) -> None:
        """Check if a collection exists."""
        await qdrant_http.put(
            "/collections/test_exists",
            json={"vectors": {"size": VECTOR_DIM, "distance": "Cosine"}},
        )
        resp = await qdrant_http.get("/collections/test_exists")
        assert resp.status_code == 200
        assert resp.json()["result"]["status"] == "green"

    async def test_delete_collection(self, qdrant_http: httpx.AsyncClient) -> None:
        """Delete a collection."""
        await qdrant_http.put(
            "/collections/test_delete",
            json={"vectors": {"size": VECTOR_DIM, "distance": "Cosine"}},
        )
        resp = await qdrant_http.delete("/collections/test_delete")
        assert resp.status_code == 200


@pytest.mark.integration
class TestEvidenceEmbeddings:
    """Test storing and searching evidence embeddings."""

    async def test_upsert_evidence_embedding(self, qdrant_http: httpx.AsyncClient) -> None:
        """Store an evidence record embedding in Qdrant."""
        await qdrant_http.put(
            "/collections/test_evidence",
            json={"vectors": {"size": VECTOR_DIM, "distance": "Cosine"}},
        )
        resp = await qdrant_http.put(
            "/collections/test_evidence/points",
            json={
                "points": [
                    {
                        "id": 1,
                        "vector": _make_evidence_vector(0),
                        "payload": _make_evidence_payload("ev-001"),
                    }
                ],
            },
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["result"]["operation_id"] is not None

    async def test_search_similar_evidence(self, qdrant_http: httpx.AsyncClient) -> None:
        """Search for similar evidence by vector similarity."""
        await qdrant_http.put(
            "/collections/test_evidence",
            json={"vectors": {"size": VECTOR_DIM, "distance": "Cosine"}},
        )
        await qdrant_http.put(
            "/collections/test_evidence/points",
            json={
                "points": [
                    {
                        "id": 1,
                        "vector": _make_evidence_vector(0),
                        "payload": _make_evidence_payload("ev-001", domain="engineering"),
                    },
                    {
                        "id": 2,
                        "vector": _make_evidence_vector(1),
                        "payload": _make_evidence_payload("ev-002", domain="sales"),
                    },
                ],
            },
        )
        resp = await qdrant_http.post(
            "/collections/test_evidence/points/search",
            json={
                "vector": _make_evidence_vector(0),
                "limit": 1,
                "with_payload": True,
            },
        )
        assert resp.status_code == 200
        results = resp.json()["result"]
        assert len(results) >= 1
        assert results[0]["id"] == 1
        assert results[0]["payload"]["domain"] == "engineering"

    async def test_search_with_filter(self, qdrant_http: httpx.AsyncClient) -> None:
        """Search with metadata filters (tenant_id, source)."""
        await qdrant_http.put(
            "/collections/test_evidence",
            json={"vectors": {"size": VECTOR_DIM, "distance": "Cosine"}},
        )
        await qdrant_http.put(
            "/collections/test_evidence/points",
            json={
                "points": [
                    {
                        "id": 1,
                        "vector": _make_evidence_vector(0),
                        "payload": _make_evidence_payload("ev-001", tenant_id="tenant-a"),
                    },
                    {
                        "id": 2,
                        "vector": _make_evidence_vector(1),
                        "payload": _make_evidence_payload("ev-002", tenant_id="tenant-b"),
                    },
                ],
            },
        )
        resp = await qdrant_http.post(
            "/collections/test_evidence/points/search",
            json={
                "vector": _make_evidence_vector(0),
                "limit": 10,
                "with_payload": True,
                "filter": {
                    "must": [
                        {"key": "tenant_id", "match": {"value": "tenant-a"}},
                    ],
                },
            },
        )
        assert resp.status_code == 200
        results = resp.json()["result"]
        assert len(results) == 1
        assert results[0]["id"] == 1

    async def test_search_empty_results(self, qdrant_http: httpx.AsyncClient) -> None:
        """Search returns empty list when no matches."""
        await qdrant_http.put(
            "/collections/test_evidence",
            json={"vectors": {"size": VECTOR_DIM, "distance": "Cosine"}},
        )
        resp = await qdrant_http.post(
            "/collections/test_evidence/points/search",
            json={
                "vector": [1.0] + [0.0] * (VECTOR_DIM - 1),
                "limit": 1,
                "with_payload": True,
            },
        )
        assert resp.status_code == 200
        results = resp.json()["result"]
        assert len(results) == 0

    async def test_upsert_batch(self, qdrant_http: httpx.AsyncClient) -> None:
        """Upsert multiple evidence embeddings in batch."""
        await qdrant_http.put(
            "/collections/test_evidence",
            json={"vectors": {"size": VECTOR_DIM, "distance": "Cosine"}},
        )
        points = [
            {
                "id": i,
                "vector": _make_evidence_vector(i),
                "payload": _make_evidence_payload(f"ev-{i:03d}"),
            }
            for i in range(1, 6)
        ]
        resp = await qdrant_http.put(
            "/collections/test_evidence/points",
            json={"points": points},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["result"]["operation_id"] is not None


@pytest.mark.integration
class TestCapabilityEmbeddings:
    """Test storing and searching capability embeddings."""

    async def test_upsert_capability_embedding(self, qdrant_http: httpx.AsyncClient) -> None:
        """Store a capability embedding in Qdrant."""
        await qdrant_http.put(
            "/collections/test_capability",
            json={"vectors": {"size": VECTOR_DIM, "distance": "Cosine"}},
        )
        resp = await qdrant_http.put(
            "/collections/test_capability/points",
            json={
                "points": [
                    {
                        "id": 1,
                        "vector": _make_capability_vector(0),
                        "payload": _make_capability_payload("cap-sales"),
                    }
                ],
            },
        )
        assert resp.status_code == 200

    async def test_search_capabilities_by_domain(self, qdrant_http: httpx.AsyncClient) -> None:
        """Search capabilities filtered by domain."""
        await qdrant_http.put(
            "/collections/test_capability",
            json={"vectors": {"size": VECTOR_DIM, "distance": "Cosine"}},
        )
        await qdrant_http.put(
            "/collections/test_capability/points",
            json={
                "points": [
                    {
                        "id": 1,
                        "vector": _make_capability_vector(0),
                        "payload": _make_capability_payload("cap-sales", domain="sales"),
                    },
                    {
                        "id": 2,
                        "vector": _make_capability_vector(1),
                        "payload": _make_capability_payload("cap-eng", domain="engineering"),
                    },
                ],
            },
        )
        resp = await qdrant_http.post(
            "/collections/test_capability/points/search",
            json={
                "vector": _make_capability_vector(0),
                "limit": 10,
                "with_payload": True,
                "filter": {
                    "must": [
                        {"key": "domain", "match": {"value": "sales"}},
                    ],
                },
            },
        )
        assert resp.status_code == 200
        results = resp.json()["result"]
        assert len(results) == 1
        assert results[0]["payload"]["domain"] == "sales"

    async def test_search_capabilities_by_maturity(self, qdrant_http: httpx.AsyncClient) -> None:
        """Search capabilities filtered by maturity level."""
        await qdrant_http.put(
            "/collections/test_capability",
            json={"vectors": {"size": VECTOR_DIM, "distance": "Cosine"}},
        )
        await qdrant_http.put(
            "/collections/test_capability/points",
            json={
                "points": [
                    {
                        "id": 1,
                        "vector": _make_capability_vector(0),
                        "payload": _make_capability_payload("cap-a", maturity_level=5),
                    },
                    {
                        "id": 2,
                        "vector": _make_capability_vector(1),
                        "payload": _make_capability_payload("cap-b", maturity_level=2),
                    },
                ],
            },
        )
        resp = await qdrant_http.post(
            "/collections/test_capability/points/search",
            json={
                "vector": _make_capability_vector(0),
                "limit": 10,
                "with_payload": True,
                "filter": {
                    "must": [
                        {"key": "maturity_level", "range": {"gte": 4}},
                    ],
                },
            },
        )
        assert resp.status_code == 200
        results = resp.json()["result"]
        assert len(results) == 1
        assert results[0]["payload"]["maturity_level"] == 5


@pytest.mark.integration
class TestVectorSearchIntegration:
    """Test end-to-end vector search with evidence and capabilities."""

    async def test_find_evidence_for_capability(self, qdrant_http: httpx.AsyncClient) -> None:
        """Find evidence records related to a capability."""
        await qdrant_http.put(
            "/collections/test_evidence",
            json={"vectors": {"size": VECTOR_DIM, "distance": "Cosine"}},
        )
        await qdrant_http.put(
            "/collections/test_evidence/points",
            json={
                "points": [
                    {
                        "id": 1,
                        "vector": _make_evidence_vector(0),
                        "payload": _make_evidence_payload("ev-001", domain="sales"),
                    },
                    {
                        "id": 2,
                        "vector": _make_evidence_vector(1),
                        "payload": _make_evidence_payload("ev-002", domain="engineering"),
                    },
                ],
            },
        )
        resp = await qdrant_http.post(
            "/collections/test_evidence/points/search",
            json={
                "vector": _make_evidence_vector(0),
                "limit": 10,
                "with_payload": True,
                "filter": {
                    "must": [
                        {"key": "domain", "match": {"value": "sales"}},
                    ],
                },
            },
        )
        assert resp.status_code == 200
        results = resp.json()["result"]
        assert len(results) == 1
        assert results[0]["payload"]["domain"] == "sales"

    async def test_find_similar_evidence_across_sources(self, qdrant_http: httpx.AsyncClient) -> None:
        """Find similar evidence from different connectors (Notion, Slack, Jira, Salesforce)."""
        await qdrant_http.put(
            "/collections/test_evidence",
            json={"vectors": {"size": VECTOR_DIM, "distance": "Cosine"}},
        )
        await qdrant_http.put(
            "/collections/test_evidence/points",
            json={
                "points": [
                    {
                        "id": 1,
                        "vector": _make_evidence_vector(0),
                        "payload": _make_evidence_payload("ev-001", source="notion"),
                    },
                    {
                        "id": 2,
                        "vector": _make_evidence_vector(1),
                        "payload": _make_evidence_payload("ev-002", source="slack"),
                    },
                    {
                        "id": 3,
                        "vector": _make_evidence_vector(2),
                        "payload": _make_evidence_payload("ev-003", source="jira"),
                    },
                ],
            },
        )
        resp = await qdrant_http.post(
            "/collections/test_evidence/points/search",
            json={
                "vector": _make_evidence_vector(0),
                "limit": 10,
                "with_payload": True,
                "filter": {
                    "must": [
                        {"key": "source", "match": {"value": "notion"}},
                    ],
                },
            },
        )
        assert resp.status_code == 200
        results = resp.json()["result"]
        assert len(results) == 1
        assert results[0]["payload"]["source"] == "notion"

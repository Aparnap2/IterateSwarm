"""Qdrant collection setup and vector operations for OntologyAI V6.

Evidence embeddings use 1536-dimensional vectors (OpenAI ``text-embedding-ada-002``)
with cosine distance.  The collection is named ``v6_evidence_embeddings`` and
is scoped by ``tenant_id`` for multi-tenant isolation.
"""

from __future__ import annotations

import logging
from typing import Any

from src.entities.models import EvidenceRecord

logger = logging.getLogger(__name__)

# ── Collection constants ────────────────────────────────────────────────

EVIDENCE_COLLECTION = "v6_evidence_embeddings"
EMBEDDING_DIMENSION = 1536  # OpenAI ada-002
DISTANCE_METRIC = "Cosine"  # Qdrant-compatible metric name


# ── Collection management ───────────────────────────────────────────────


async def ensure_evidence_collection(client: Any) -> None:
    """Idempotently create the ``v6_evidence_embeddings`` collection.

    If the collection already exists with matching configuration this
    function is a no-op.  If it exists with different settings an
    appropriate warning is logged but no destructive action is taken.

    Parameters
    ----------
    client:
        An initialised ``qdrant_client.AsyncQdrantClient`` (or compatible
        duck-typed client with ``collection_exists``, ``create_collection``,
        and ``get_collection`` methods).
    """
    raise NotImplementedError(
        "Qdrant client not wired — implement with: "
        "client.collection_exists, client.create_collection"
    )


# ── Vector upsert ───────────────────────────────────────────────────────


async def upsert_evidence_vectors(
    client: Any,
    evidence_records: list[EvidenceRecord],
) -> int:
    """Batch-upsert evidence embeddings into Qdrant.

    Only records with non-``None`` embeddings are upserted.  The payload
    includes ``id``, ``tenant_id``, ``source``, ``timestamp``,
    ``confidence``, and ``hash`` for filtering and display.

    Parameters
    ----------
    client:
        An initialised ``qdrant_client.AsyncQdrantClient``.
    evidence_records:
        Evidence records with pre-computed embeddings.

    Returns
    -------
    int
        Number of vectors successfully upserted.
    """
    raise NotImplementedError(
        "Implement with: client.upsert(collection_name, points=[...])"
    )


# ── Similarity search ───────────────────────────────────────────────────


async def search_similar_evidence(
    client: Any,
    vector: list[float],
    tenant_id: str,
    limit: int = 10,
    score_threshold: float = 0.85,
) -> list[dict[str, Any]]:
    """Search for evidence similar to *vector* within *tenant_id*'s scope.

    Results are filtered by ``tenant_id`` and include only points whose
    cosine similarity >= *score_threshold*.

    Parameters
    ----------
    client:
        An initialised ``qdrant_client.AsyncQdrantClient``.
    vector:
        Query vector (1536 floats).
    tenant_id:
        Tenant scope filter.
    limit:
        Maximum number of results (default 10).
    score_threshold:
        Minimum cosine similarity (default 0.85).

    Returns
    -------
    list[dict[str, Any]]
        Each entry: ``{"id": str, "score": float, "payload": dict}``.
    """
    raise NotImplementedError(
        "Implement with: client.search(collection_name, query_vector=vector, "
        "query_filter=Filter(must=[FieldCondition(key='tenant_id', match=MatchValue(value=tenant_id))]), "
        "limit=limit, score_threshold=score_threshold)"
    )

"""Async Neo4j client wrapper for OntologyAI V6.

Provides an async context manager that encapsulates connection lifecycle,
query execution, and entity-graph traversal.

Per ADR-006, Neo4j stores **only**: entity nodes (all 24 types),
relationship edges, evidence links, and the decision graph.
Everything else stays in PostgreSQL.
"""

from __future__ import annotations

import logging
from types import TracebackType
from typing import Any

from src.entities.models import OntologyBaseModel

logger = logging.getLogger(__name__)


class Neo4jClient:
    """Async Neo4j client with context-manager support.

    Usage::

        async with Neo4jClient() as client:
            await client.connect(uri, user, password)
            result = await client.run_query("MATCH (n) RETURN n LIMIT 10")
    """

    def __init__(self) -> None:
        self._driver: Any = None  # neo4j.AsyncDriver (avoid hard dep at import)

    # ── Async context manager ───────────────────────────────────────────

    async def __aenter__(self) -> Neo4jClient:
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: TracebackType | None,
    ) -> None:
        await self.close()

    # ── Connection lifecycle ────────────────────────────────────────────

    async def connect(self, uri: str, user: str, password: str) -> None:
        """Open a connection to the Neo4j database.

        Parameters
        ----------
        uri:
            Bolt or Neo4j URI (e.g. ``bolt://localhost:7687``).
        user:
            Database user name.
        password:
            Database user password.
        """
        raise NotImplementedError(
            "Neo4j driver not wired — provide neo4j wheel at runtime."
        )

    async def close(self) -> None:
        """Gracefully close the driver and release all connections."""
        if self._driver is not None:
            await self._driver.close()  # type: ignore[union-attr]
            self._driver = None

    # ── Query execution ─────────────────────────────────────────────────

    async def run_query(
        self,
        query: str,
        params: dict[str, Any] | None = None,
    ) -> list[dict[str, Any]]:
        """Execute a Cypher query and return the result as a list of dicts.

        Parameters
        ----------
        query:
            Cypher query string.
        params:
            Named parameters for the query.

        Returns
        -------
        list[dict[str, Any]]
            Each dict represents a record with keys as field names.
        """
        raise NotImplementedError(
            "Neo4j driver not wired — implement with async session."
        )

    # ── Entity operations ───────────────────────────────────────────────

    async def create_entity_node(
        self,
        entity: OntologyBaseModel,
        labels: list[str] | None = None,
    ) -> dict[str, Any]:
        """Create a labelled node from an entity model.

        All public fields of *entity* are written as node properties.
        The ``id`` property is used for the Neo4j ``id`` property (not
        the internal node id).

        Parameters
        ----------
        entity:
            Any V6 entity model instance.
        labels:
            Additional Neo4j labels beyond the entity class name.
            The entity's class name is always included as a label.

        Returns
        -------
        dict[str, Any]
            The created node's properties (including the internal element id).
        """
        raise NotImplementedError("Implement with CREATE (n:Label $props) RETURN n")

    async def create_relationship(
        self,
        source_id: str,
        target_id: str,
        rel_type: str,
        properties: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Create a typed, directed relationship between two nodes.

        Parameters
        ----------
        source_id:
            ``id`` property of the source entity node.
        target_id:
            ``id`` property of the target entity node.
        rel_type:
            Relationship type (e.g. ``"DEPENDS_ON"``, ``"OWNED_BY"``).
        properties:
            Optional edge properties (confidence, strength, etc.).

        Returns
        -------
        dict[str, Any]
            The created relationship's properties.
        """
        raise NotImplementedError(
            "Implement with MATCH (a {id: $sid}), (b {id: $tid}) "
            "CREATE (a)-[r:`{rel_type}` $props]->(b) RETURN r"
        )

    async def find_entity_by_id(self, entity_id: str) -> dict[str, Any] | None:
        """Look up a single entity node by its ``id`` property.

        Returns the node properties as a dict, or ``None`` if not found.
        """
        raise NotImplementedError("Implement with MATCH (n {id: $id}) RETURN n")

    async def get_entity_graph(
        self,
        entity_id: str,
        max_hops: int = 3,
    ) -> list[dict[str, Any]]:
        """Traverse the neighbourhood of an entity up to *max_hops* deep.

        Returns a list of dicts with keys ``node`` and ``relationship``
        describing the sub-graph.  The traversal is breadth-first and
        bounded by *max_hops*.

        Parameters
        ----------
        entity_id:
            Starting entity's ``id`` property.
        max_hops:
            Maximum traversal depth (default 3).

        Returns
        -------
        list[dict[str, Any]]
            Each entry: ``{"node": {...}, "relationship": {...}}``.
        """
        raise NotImplementedError(
            "Implement with MATCH (start {id: $id})-[*1..$max_hops]-(neighbor) "
            "RETURN start, neighbor"
        )

    # ── Batch operations ────────────────────────────────────────────────

    async def batch_create_nodes(
        self,
        entities: list[OntologyBaseModel],
        batch_size: int = 100,
    ) -> int:
        """Insert multiple entity nodes in a single transaction.

        Parameters
        ----------
        entities:
            List of entity model instances to create.
        batch_size:
            Number of nodes to create per Cypher ``UNWIND`` batch.

        Returns
        -------
        int
            Total number of nodes created.
        """
        raise NotImplementedError(
            "Implement with UNWIND $batch AS row CREATE (n:Label) SET n = row"
        )

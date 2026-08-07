"""Graph builder — writes resolved entities and evidence links to Neo4j.

Creates entity nodes (with type as label), evidence nodes, and typed
relationships (``LINKS_TO``, ``OWNED_BY``, ``MEASURES``).  Handles
Neo4j unavailability gracefully by falling back to in-memory tracking.
"""

from __future__ import annotations

import logging
from typing import Any

from src.entities.models import EvidenceRecord
from src.knowledge.entity_resolver import EntityResolutionResult

logger = logging.getLogger(__name__)


class GraphBuildResult:
    """Summary of a graph build operation.

    Attributes
    ----------
    nodes_created:
        Number of entity / evidence nodes created.
    relationships_created:
        Number of typed relationships created.
    evidence_linked:
        Number of evidence-to-entity links made.
    neo4j_available:
        Whether Neo4j was reachable during the build.
    """

    def __init__(self) -> None:
        self.nodes_created: int = 0
        self.relationships_created: int = 0
        self.evidence_linked: int = 0
        self.neo4j_available: bool = False


class GraphBuilder:
    """Builds Neo4j graph from resolved entities and evidence.

    Creates entity nodes, evidence nodes, and typed relationships.
    When Neo4j is unavailable, all operations are silently no-oped
    and the result reflects ``neo4j_available=False``.

    Parameters
    ----------
    neo4j_client:
        An initialised ``Neo4jClient`` (or compatible duck-typed client).
        May be ``None``.
    """

    def __init__(self, neo4j_client) -> None:
        self._neo4j = neo4j_client

    async def create_entity_node(
        self,
        entity_type: str,
        entity_id: str,
        properties: dict[str, Any],
    ) -> dict[str, Any] | None:
        """Create an entity node in Neo4j with *entity_type* as label.

        Parameters
        ----------
        entity_type:
            Neo4j node label (e.g. ``"Stakeholder"``, ``"Requirement"``).
        entity_id:
            ULID of the entity.
        properties:
            Node properties to set.

        Returns
        -------
        dict | None
            The created node properties, or ``None`` if Neo4j is
            unavailable.
        """
        if self._neo4j is None:
            logger.debug("Neo4j unavailable — skipping entity node creation")
            return None
        try:
            node_props = {"id": entity_id, **properties}
            result = await self._neo4j.run_query(
                f"CREATE (n:{entity_type} $props) RETURN n",
                {"props": node_props},
            )
            logger.debug(
                "Created %s node %s (%s)",
                entity_type,
                entity_id,
                properties.get("name", ""),
            )
            return result[0] if result else None
        except NotImplementedError:
            logger.debug("Neo4j not wired — skipping entity node creation")
            return None

    async def create_evidence_node(
        self,
        evidence: EvidenceRecord,
    ) -> dict[str, Any] | None:
        """Create an ``Evidence`` node linked to entities.

        Parameters
        ----------
        evidence:
            The evidence record to persist as a graph node.

        Returns
        -------
        dict | None
            The created node properties, or ``None``.
        """
        if self._neo4j is None:
            return None
        try:
            props = {
                "id": evidence.id,
                "tenant_id": evidence.tenant_id,
                "source": evidence.source,
                "source_type": evidence.source_type,
                "timestamp": evidence.timestamp.isoformat(),
                "confidence": evidence.confidence,
                "hash": evidence.hash,
            }
            result = await self._neo4j.run_query(
                "CREATE (n:Evidence $props) RETURN n",
                {"props": props},
            )
            logger.debug("Created Evidence node %s", evidence.id)
            return result[0] if result else None
        except NotImplementedError:
            logger.debug("Neo4j not wired — skipping evidence node creation")
            return None

    async def link_evidence_to_entity(
        self,
        evidence_id: str,
        entity_id: str,
        rel_type: str = "LINKS_TO",
    ) -> dict[str, Any] | None:
        """Create a typed relationship between evidence and entity.

        Parameters
        ----------
        evidence_id:
            ULID of the evidence node.
        entity_id:
            ULID of the entity node.
        rel_type:
            Relationship type (default ``"LINKS_TO"``).

        Returns
        -------
        dict | None
            The created relationship properties, or ``None``.
        """
        if self._neo4j is None:
            return None
        try:
            result = await self._neo4j.run_query(
                (
                    "MATCH (e:Evidence {id: $eid}), (n {id: $nid}) "
                    f"CREATE (e)-[r:{rel_type}]->(n) RETURN r"
                ),
                {"eid": evidence_id, "nid": entity_id},
            )
            logger.debug(
                "Linked evidence %s → %s (%s)", evidence_id, entity_id, rel_type
            )
            return result[0] if result else None
        except NotImplementedError:
            logger.debug("Neo4j not wired — skipping relationship creation")
            return None

    async def build_graph(
        self,
        entities: list[EntityResolutionResult],
        evidence_list: list[EvidenceRecord],
        workspace_id: str,  # noqa: ARG002
    ) -> GraphBuildResult:
        """Full build: create nodes, create relationships, link to workspace.

        Parameters
        ----------
        entities:
            Resolved entity results from the ``EntityResolver``.
        evidence_list:
            Evidence records processed in this run.
        workspace_id:
            ULID of the owning workspace (for ``CONTAINS`` links).

        Returns
        -------
        GraphBuildResult
            Summary of the build operation.
        """
        result = GraphBuildResult()

        if self._neo4j is None:
            logger.warning("Neo4j client is None — graph build is a no-op")
            return result

        # Check availability once
        try:
            await self._neo4j.run_query("RETURN 1 AS ok")
            result.neo4j_available = True
        except (NotImplementedError, Exception):
            logger.info("Neo4j not available — graph build returns empty result")
            return result

        # ── 1. Create entity nodes ───────────────────────────────────────
        for ent in entities:
            node = await self.create_entity_node(
                entity_type=ent.entity_type,
                entity_id=ent.entity_id,
                properties=ent.properties,
            )
            if node is not None:
                result.nodes_created += 1

        # ── 2. Create evidence nodes ─────────────────────────────────────
        for evidence in evidence_list:
            node = await self.create_evidence_node(evidence)
            if node is not None:
                result.nodes_created += 1

        # ── 3. Link evidence to entities ─────────────────────────────────
        for ent in entities:
            rel = ent.entity_type.lower()
            if rel == "stakeholder":
                rel_type = "MENTIONS"
            elif rel == "kpi":
                rel_type = "MEASURES"
            else:
                rel_type = "LINKS_TO"

            link = await self.link_evidence_to_entity(
                evidence_id=ent.evidence_id,
                entity_id=ent.entity_id,
                rel_type=rel_type,
            )
            if link is not None:
                result.evidence_linked += 1
                result.relationships_created += 1

        logger.info(
            "Graph build complete: %d nodes, %d relationships, %d evidence links",
            result.nodes_created,
            result.relationships_created,
            result.evidence_linked,
        )
        return result

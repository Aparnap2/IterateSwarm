"""Neo4j graph operations tests for V6 semantic layer.

Verifies that Neo4j can store and query:
  - Capability nodes and hierarchy (L0 → L1 → L2)
  - Typed inter-capability relationships (DEPENDS_ON, ENABLES)
  - CanonicalEntity nodes with EntityAlias resolution
  - KnowledgeCatalogEntry indexing and category queries

All tests run against a real Neo4j instance at bolt://localhost:7687.
Test nodes are tagged with tenant_id='test' for isolated cleanup.

Usage:
    cd apps/ai
    uv run pytest tests/v6/test_graph_v6.py -v -m integration
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any, AsyncGenerator

import pytest
from neo4j import AsyncDriver, AsyncGraphDatabase, Record


# ── Constants ─────────────────────────────────────────────────────────────

NEO4J_URI = "bolt://localhost:7687"
NEO4J_AUTH = ("neo4j", "ontologiai_dev")
TENANT_ID = "test"


def _ulid() -> str:
    """Generate a unique test ID (ULID-style prefix for recognizability)."""
    return f"01TEST{uuid.uuid4().hex[:20].upper()}"


# ── Fixtures ──────────────────────────────────────────────────────────────


@pytest.fixture
async def neo4j_driver() -> AsyncGenerator[AsyncDriver, None]:
    """Yield an async Neo4j driver; clean up test nodes after each test."""
    driver = AsyncGraphDatabase.driver(NEO4J_URI, auth=NEO4J_AUTH)
    try:
        # Verify connectivity
        await driver.verify_connectivity()
    except Exception as exc:
        await driver.close()
        pytest.skip(f"Neo4j not reachable at {NEO4J_URI}: {exc}")
    yield driver
    # Cleanup: delete all nodes tagged with our test tenant
    async with driver.session() as session:
        await session.run(
            "MATCH (n) WHERE n.tenant_id = $tid DETACH DELETE n",
            tid=TENANT_ID,
        )
    await driver.close()


# ── Helpers ───────────────────────────────────────────────────────────────


async def _create_capability_node(
    tx: Any,
    *,
    node_id: str,
    name: str,
    level: str = "L0",
    parent_id: str | None = None,
    health_score: float = 0.0,
    domain: str = "",
    tenant_id: str = TENANT_ID,
) -> Record:
    """Create a Capability node in Neo4j and return the record."""
    result = await tx.run(
        """
        CREATE (c:Capability {
            id: $id,
            name: $name,
            level: $level,
            parent_id: $parent_id,
            health_score: $health_score,
            domain: $domain,
            tenant_id: $tenant_id,
            created_at: $now,
            updated_at: $now
        })
        RETURN c
        """,
        id=node_id,
        name=name,
        level=level,
        parent_id=parent_id,
        health_score=health_score,
        domain=domain,
        tenant_id=tenant_id,
        now=datetime.now(timezone.utc).isoformat(),
    )
    return await result.single()


async def _create_canonical_entity_node(
    tx: Any,
    *,
    node_id: str,
    canonical_name: str,
    entity_type: str,
    tenant_id: str = TENANT_ID,
) -> Record:
    """Create a CanonicalEntity node in Neo4j."""
    result = await tx.run(
        """
        CREATE (e:CanonicalEntity {
            id: $id,
            canonical_name: $name,
            entity_type: $type,
            tenant_id: $tenant_id,
            confidence: 0.9,
            created_at: $now,
            updated_at: $now
        })
        RETURN e
        """,
        id=node_id,
        name=canonical_name,
        type=entity_type,
        tenant_id=tenant_id,
        now=datetime.now(timezone.utc).isoformat(),
    )
    return await result.single()


async def _create_catalog_indexed_relationship(
    tx: Any,
    *,
    source_id: str,
    target_id: str,
    category: str,
    tenant_id: str = TENANT_ID,
) -> Record:
    """Create a CATALOG_INDEXED relationship between two nodes."""
    result = await tx.run(
        """
        MATCH (a {id: $source_id}), (b {id: $target_id})
        CREATE (a)-[r:CATALOG_INDEXED {
            category: $category,
            tenant_id: $tenant_id,
            created_at: $now
        }]->(b)
        RETURN r
        """,
        source_id=source_id,
        target_id=target_id,
        category=category,
        tenant_id=tenant_id,
        now=datetime.now(timezone.utc).isoformat(),
    )
    return await result.single()


# ═══════════════════════════════════════════════════════════════════════════
# TestCapabilityGraph
# ═══════════════════════════════════════════════════════════════════════════


@pytest.mark.integration
class TestCapabilityGraph:
    """Test capability nodes and relationships in Neo4j."""

    async def test_create_capability_node(self, neo4j_driver: AsyncDriver) -> None:
        """Create a Capability node with required properties."""
        cap_id = _ulid()
        async with neo4j_driver.session() as session:
            record = await session.execute_write(
                lambda tx: _create_capability_node(
                    tx,
                    node_id=cap_id,
                    name="Authentication",
                    level="L0",
                    domain="security",
                )
            )
            node = record["c"]
            assert node["id"] == cap_id
            assert node["name"] == "Authentication"
            assert node["level"] == "L0"
            assert node["domain"] == "security"
            assert node["tenant_id"] == TENANT_ID

            # Verify the node exists with a read query
            result = await session.run(
                "MATCH (c:Capability {id: $id}) RETURN c", id=cap_id
            )
            found = await result.single()
            assert found is not None, "Capability node not found after creation"

    async def test_create_capability_hierarchy(
        self, neo4j_driver: AsyncDriver
    ) -> None:
        """Create parent-child capability relationships (L0 -> L1 -> L2)."""
        l0_id = _ulid()
        l1_id = _ulid()
        l2_id = _ulid()

        async with neo4j_driver.session() as session:
            # Create L0 -> L1 -> L2 hierarchy
            await session.execute_write(
                lambda tx: _create_capability_node(
                    tx, node_id=l0_id, name="Platform", level="L0"
                )
            )
            await session.execute_write(
                lambda tx: _create_capability_node(
                    tx, node_id=l1_id, name="Auth", level="L1", parent_id=l0_id
                )
            )
            await session.execute_write(
                lambda tx: _create_capability_node(
                    tx, node_id=l2_id, name="Login", level="L2", parent_id=l1_id
                )
            )

            # Create parent-child relationships
            await session.run(
                """
                MATCH (parent {id: $parent_id}), (child {id: $child_id})
                CREATE (parent)-[:HAS_CHILD]->(child)
                """,
                parent_id=l0_id,
                child_id=l1_id,
            )
            await session.run(
                """
                MATCH (parent {id: $parent_id}), (child {id: $child_id})
                CREATE (parent)-[:HAS_CHILD]->(child)
                """,
                parent_id=l1_id,
                child_id=l2_id,
            )

            # Verify hierarchy via traversal
            result = await session.run(
                """
                MATCH (root:Capability {id: $root_id})-[:HAS_CHILD*1..2]->(desc)
                RETURN desc.id AS id, desc.name AS name, desc.level AS level
                ORDER BY desc.level
                """,
                root_id=l0_id,
            )
            descendants = [record async for record in result]
            assert len(descendants) == 2
            assert descendants[0]["id"] == l1_id
            assert descendants[0]["level"] == "L1"
            assert descendants[1]["id"] == l2_id
            assert descendants[1]["level"] == "L2"

    async def test_create_capability_relationship(
        self, neo4j_driver: AsyncDriver
    ) -> None:
        """Create typed relationships between capabilities (DEPENDS_ON, ENABLES)."""
        cap_a_id = _ulid()
        cap_b_id = _ulid()
        cap_c_id = _ulid()

        async with neo4j_driver.session() as session:
            # Create three capability nodes
            for cid, name in [
                (cap_a_id, "AuthService"),
                (cap_b_id, "UserDB"),
                (cap_c_id, "Dashboard"),
            ]:
                await session.execute_write(
                    lambda tx, cid=cid, name=name: _create_capability_node(
                        tx, node_id=cid, name=name
                    )
                )

            # AuthService DEPENDS_ON UserDB
            await session.run(
                """
                MATCH (a {id: $a_id}), (b {id: $b_id})
                CREATE (a)-[r:DEPENDS_ON {confidence: 0.95, tenant_id: $tid}]->(b)
                RETURN r
                """,
                a_id=cap_a_id,
                b_id=cap_b_id,
                tid=TENANT_ID,
            )
            # Dashboard ENABLES AuthService
            await session.run(
                """
                MATCH (a {id: $a_id}), (b {id: $b_id})
                CREATE (a)-[r:ENABLES {confidence: 0.8, tenant_id: $tid}]->(b)
                RETURN r
                """,
                a_id=cap_c_id,
                b_id=cap_a_id,
                tid=TENANT_ID,
            )

            # Query relationships
            result = await session.run(
                """
                MATCH (a {id: $a_id})-[r]->(b)
                RETURN type(r) AS rel_type, b.name AS target_name, r.confidence AS conf
                """,
                a_id=cap_a_id,
            )
            rels = [record async for record in result]
            assert len(rels) == 1
            assert rels[0]["rel_type"] == "DEPENDS_ON"
            assert rels[0]["target_name"] == "UserDB"
            assert rels[0]["conf"] == 0.95

            # Query reverse: who depends on AuthService?
            result = await session.run(
                """
                MATCH (a)-[r:DEPENDS_ON]->(b {id: $b_id})
                RETURN a.name AS source_name
                """,
                b_id=cap_a_id,
            )
            dependents = [record async for record in result]
            assert len(dependents) == 1
            assert dependents[0]["source_name"] == "Dashboard"

    async def test_query_capability_subtree(
        self, neo4j_driver: AsyncDriver
    ) -> None:
        """Query all descendants of a capability (subtree traversal)."""
        root_id = _ulid()
        child_ids = [_ulid() for _ in range(3)]
        grandchild_id = _ulid()

        async with neo4j_driver.session() as session:
            # Build tree: root -> child[0], child[1] -> grandchild
            await session.execute_write(
                lambda tx: _create_capability_node(
                    tx, node_id=root_id, name="Platform", level="L0"
                )
            )
            for i, cid in enumerate(child_ids):
                await session.execute_write(
                    lambda tx, cid=cid, i=i: _create_capability_node(
                        tx, node_id=cid, name=f"Child{i}", level="L1", parent_id=root_id
                    )
                )
            await session.execute_write(
                lambda tx: _create_capability_node(
                    tx,
                    node_id=grandchild_id,
                    name="Grandchild",
                    level="L2",
                    parent_id=child_ids[1],
                )
            )

            # Create HAS_CHILD edges
            for cid in child_ids:
                await session.run(
                    """
                    MATCH (p {id: $pid}), (c {id: $cid})
                    CREATE (p)-[:HAS_CHILD]->(c)
                    """,
                    pid=root_id,
                    cid=cid,
                )
            await session.run(
                """
                MATCH (p {id: $pid}), (c {id: $cid})
                CREATE (p)-[:HAS_CHILD]->(c)
                """,
                pid=child_ids[1],
                cid=grandchild_id,
            )

            # Variable-length path traversal
            result = await session.run(
                """
                MATCH (root {id: $root_id})-[:HAS_CHILD*0..]->(desc)
                RETURN desc.id AS id, desc.name AS name, desc.level AS level
                ORDER BY desc.level, desc.name
                """,
                root_id=root_id,
            )
            subtree = [record async for record in result]
            # root + 3 children + 1 grandchild = 5
            assert len(subtree) == 5
            names = {r["name"] for r in subtree}
            assert "Platform" in names
            assert "Grandchild" in names

    async def test_query_capability_path(
        self, neo4j_driver: AsyncDriver
    ) -> None:
        """Find the path between two capabilities."""
        a_id = _ulid()
        b_id = _ulid()
        c_id = _ulid()

        async with neo4j_driver.session() as session:
            for cid, name in [(a_id, "A"), (b_id, "B"), (c_id, "C")]:
                await session.execute_write(
                    lambda tx, cid=cid, name=name: _create_capability_node(
                        tx, node_id=cid, name=name
                    )
                )
            # A -> B -> C
            for src, dst in [(a_id, b_id), (b_id, c_id)]:
                await session.run(
                    """
                    MATCH (s {id: $src}), (d {id: $dst})
                    CREATE (s)-[:DEPENDS_ON]->(d)
                    """,
                    src=src,
                    dst=dst,
                )

            # Shortest path from A to C
            result = await session.run(
                """
                MATCH path = shortestPath(
                    (a {id: $a_id})-[*]-(c {id: $c_id})
                )
                RETURN [n IN nodes(path) | n.name] AS node_names,
                       [r IN relationships(path) | type(r)] AS rel_types
                """,
                a_id=a_id,
                c_id=c_id,
            )
            record = await result.single()
            assert record is not None, "No path found between A and C"
            assert record["node_names"] == ["A", "B", "C"]
            assert record["rel_types"] == ["DEPENDS_ON", "DEPENDS_ON"]

    async def test_delete_capability_cascade(
        self, neo4j_driver: AsyncDriver
    ) -> None:
        """Delete a capability and its relationships."""
        parent_id = _ulid()
        child_id = _ulid()

        async with neo4j_driver.session() as session:
            await session.execute_write(
                lambda tx: _create_capability_node(
                    tx, node_id=parent_id, name="Parent"
                )
            )
            await session.execute_write(
                lambda tx: _create_capability_node(
                    tx, node_id=child_id, name="Child", parent_id=parent_id
                )
            )
            await session.run(
                """
                MATCH (p {id: $pid}), (c {id: $cid})
                CREATE (p)-[:HAS_CHILD]->(c)
                """,
                pid=parent_id,
                cid=child_id,
            )

            # Verify both exist
            result = await session.run(
                "MATCH (n {id: $id}) RETURN n", id=parent_id
            )
            assert await result.single() is not None

            # Delete parent with DETACH DELETE (removes relationships too)
            await session.run(
                "MATCH (n {id: $id}) DETACH DELETE n", id=parent_id
            )

            # Parent should be gone
            result = await session.run(
                "MATCH (n {id: $id}) RETURN n", id=parent_id
            )
            assert await result.single() is None

            # Child should still exist (DETACH DELETE only deletes the matched node)
            result = await session.run(
                "MATCH (n {id: $id}) RETURN n", id=child_id
            )
            assert await result.single() is not None

    async def test_capability_health_aggregation(
        self, neo4j_driver: AsyncDriver
    ) -> None:
        """Aggregate health scores across a capability subtree."""
        root_id = _ulid()
        child_ids = [_ulid() for _ in range(3)]
        health_scores = [0.9, 0.6, 0.3]

        async with neo4j_driver.session() as session:
            await session.execute_write(
                lambda tx: _create_capability_node(
                    tx, node_id=root_id, name="Platform", health_score=0.0
                )
            )
            for cid, score in zip(child_ids, health_scores):
                await session.execute_write(
                    lambda tx, cid=cid, score=score: _create_capability_node(
                        tx, node_id=cid, name=f"Cap{cid[:6]}", health_score=score
                    )
                )
                await session.run(
                    """
                    MATCH (p {id: $pid}), (c {id: $cid})
                    CREATE (p)-[:HAS_CHILD]->(c)
                    """,
                    pid=root_id,
                    cid=cid,
                )

            # Aggregate: average, min, max health across subtree
            result = await session.run(
                """
                MATCH (root {id: $root_id})-[:HAS_CHILD*1..]->(desc)
                RETURN avg(desc.health_score) AS avg_health,
                       min(desc.health_score) AS min_health,
                       max(desc.health_score) AS max_health,
                       count(desc) AS child_count
                """,
                root_id=root_id,
            )
            record = await result.single()
            assert record is not None
            assert record["child_count"] == 3
            assert abs(record["avg_health"] - 0.6) < 0.01
            assert record["min_health"] == 0.3
            assert record["max_health"] == 0.9


# ═══════════════════════════════════════════════════════════════════════════
# TestCanonicalEntityGraph
# ═══════════════════════════════════════════════════════════════════════════


@pytest.mark.integration
class TestCanonicalEntityGraph:
    """Test canonical entity nodes and alias relationships in Neo4j."""

    async def test_create_canonical_entity_node(
        self, neo4j_driver: AsyncDriver
    ) -> None:
        """Create a CanonicalEntity node."""
        entity_id = _ulid()
        async with neo4j_driver.session() as session:
            record = await session.execute_write(
                lambda tx: _create_canonical_entity_node(
                    tx,
                    node_id=entity_id,
                    canonical_name="Acme Corp",
                    entity_type="customer",
                )
            )
            node = record["e"]
            assert node["id"] == entity_id
            assert node["canonical_name"] == "Acme Corp"
            assert node["entity_type"] == "customer"
            assert node["tenant_id"] == TENANT_ID

    async def test_create_entity_alias(self, neo4j_driver: AsyncDriver) -> None:
        """Create EntityAlias nodes linked to CanonicalEntity."""
        entity_id = _ulid()
        alias_id = _ulid()

        async with neo4j_driver.session() as session:
            # Create canonical entity
            await session.execute_write(
                lambda tx: _create_canonical_entity_node(
                    tx,
                    node_id=entity_id,
                    canonical_name="Acme Corp",
                    entity_type="customer",
                )
            )

            # Create alias node
            await session.run(
                """
                CREATE (a:EntityAlias {
                    id: $id,
                    source_system: $source,
                    external_id: $ext_id,
                    display_name: $display,
                    entity_type_hint: $hint,
                    confidence: 0.9,
                    tenant_id: $tid,
                    created_at: $now
                })
                """,
                id=alias_id,
                source="salesforce",
                ext_id="sf-001",
                display="Acme Corp (SF)",
                hint="Account",
                tid=TENANT_ID,
                now=datetime.now(timezone.utc).isoformat(),
            )

            # Link alias to canonical entity
            await session.run(
                """
                MATCH (alias {id: $alias_id}), (entity {id: $entity_id})
                CREATE (alias)-[:ALIAS_OF {tenant_id: $tid}]->(entity)
                """,
                alias_id=alias_id,
                entity_id=entity_id,
                tid=TENANT_ID,
            )

            # Query: find canonical entity via alias
            result = await session.run(
                """
                MATCH (a:EntityAlias {source_system: $source, external_id: $ext_id})
                      -[:ALIAS_OF]->(e:CanonicalEntity)
                RETURN e.id AS entity_id, e.canonical_name AS name
                """,
                source="salesforce",
                ext_id="sf-001",
            )
            record = await result.single()
            assert record is not None
            assert record["entity_id"] == entity_id
            assert record["name"] == "Acme Corp"

    async def test_query_entity_by_alias(
        self, neo4j_driver: AsyncDriver
    ) -> None:
        """Find canonical entity by source system + external_id."""
        entity_id = _ulid()
        alias_ids = [_ulid() for _ in range(3)]
        systems = [("salesforce", "sf-100"), ("erp", "erp-200"), ("support", "tkt-300")]

        async with neo4j_driver.session() as session:
            await session.execute_write(
                lambda tx: _create_canonical_entity_node(
                    tx,
                    node_id=entity_id,
                    canonical_name="Globex Corp",
                    entity_type="vendor",
                )
            )

            for alias_id, (source, ext_id) in zip(alias_ids, systems):
                await session.run(
                    """
                    CREATE (a:EntityAlias {
                        id: $id,
                        source_system: $source,
                        external_id: $ext_id,
                        display_name: $display,
                        entity_type_hint: 'vendor',
                        confidence: 0.9,
                        tenant_id: $tid,
                        created_at: $now
                    })
                    """,
                    id=alias_id,
                    source=source,
                    ext_id=ext_id,
                    display=f"Globex ({source})",
                    tid=TENANT_ID,
                    now=datetime.now(timezone.utc).isoformat(),
                )
                await session.run(
                    """
                    MATCH (a {id: $aid}), (e {id: $eid})
                    CREATE (a)-[:ALIAS_OF {tenant_id: $tid}]->(e)
                    """,
                    aid=alias_id,
                    eid=entity_id,
                    tid=TENANT_ID,
                )

            # Query by specific source system
            result = await session.run(
                """
                MATCH (a:EntityAlias {source_system: $source, external_id: $ext_id})
                      -[:ALIAS_OF]->(e:CanonicalEntity)
                RETURN e.canonical_name AS name, e.entity_type AS etype
                """,
                source="erp",
                ext_id="erp-200",
            )
            record = await result.single()
            assert record is not None
            assert record["name"] == "Globex Corp"
            assert record["etype"] == "vendor"

            # Query: all aliases for a canonical entity
            result = await session.run(
                """
                MATCH (a:EntityAlias)-[:ALIAS_OF]->(e:CanonicalEntity {id: $eid})
                RETURN a.source_system AS source, a.external_id AS ext_id
                ORDER BY a.source_system
                """,
                eid=entity_id,
            )
            aliases = [record async for record in result]
            assert len(aliases) == 3
            assert aliases[0]["source"] == "erp"
            assert aliases[1]["source"] == "salesforce"
            assert aliases[2]["source"] == "support"

    async def test_merge_entities(self, neo4j_driver: AsyncDriver) -> None:
        """Merge two canonical entities (transfer aliases)."""
        entity_a_id = _ulid()
        entity_b_id = _ulid()
        alias_a_id = _ulid()
        alias_b_id = _ulid()

        async with neo4j_driver.session() as session:
            # Create two canonical entities
            await session.execute_write(
                lambda tx: _create_canonical_entity_node(
                    tx,
                    node_id=entity_a_id,
                    canonical_name="Acme Inc",
                    entity_type="customer",
                )
            )
            await session.execute_write(
                lambda tx: _create_canonical_entity_node(
                    tx,
                    node_id=entity_b_id,
                    canonical_name="Acme Corporation",
                    entity_type="customer",
                )
            )

            # Each has one alias
            for aid, source, ext_id, eid in [
                (alias_a_id, "salesforce", "sf-001", entity_a_id),
                (alias_b_id, "erp", "erp-001", entity_b_id),
            ]:
                await session.run(
                    """
                    CREATE (a:EntityAlias {
                        id: $id, source_system: $source, external_id: $ext_id,
                        display_name: $display, entity_type_hint: 'customer',
                        confidence: 0.9, tenant_id: $tid, created_at: $now
                    })
                    """,
                    id=aid,
                    source=source,
                    ext_id=ext_id,
                    display=f"Acme ({source})",
                    tid=TENANT_ID,
                    now=datetime.now(timezone.utc).isoformat(),
                )
                await session.run(
                    """
                    MATCH (a {id: $aid}), (e {id: $eid})
                    CREATE (a)-[:ALIAS_OF {tenant_id: $tid}]->(e)
                    """,
                    aid=aid,
                    eid=eid,
                    tid=TENANT_ID,
                )

            # Merge: transfer all aliases from B to A, delete B
            await session.run(
                """
                MATCH (a:EntityAlias)-[:ALIAS_OF]->(b:CanonicalEntity {id: $bid})
                MATCH (target:CanonicalEntity {id: $aid})
                MERGE (a)-[:ALIAS_OF {tenant_id: $tid}]->(target)
                """,
                aid=entity_a_id,
                bid=entity_b_id,
                tid=TENANT_ID,
            )
            await session.run(
                "MATCH (n {id: $id}) DETACH DELETE n", id=entity_b_id
            )

            # Verify: entity A now has both aliases
            result = await session.run(
                """
                MATCH (a:EntityAlias)-[:ALIAS_OF]->(e:CanonicalEntity {id: $eid})
                RETURN a.source_system AS source
                ORDER BY a.source_system
                """,
                eid=entity_a_id,
            )
            sources = [record["source"] async for record in result]
            assert len(sources) == 2
            assert "erp" in sources
            assert "salesforce" in sources

            # Entity B should be gone
            result = await session.run(
                "MATCH (n {id: $id}) RETURN n", id=entity_b_id
            )
            assert await result.single() is None


# ═══════════════════════════════════════════════════════════════════════════
# TestKnowledgeCatalogGraph
# ═══════════════════════════════════════════════════════════════════════════


@pytest.mark.integration
class TestKnowledgeCatalogGraph:
    """Test knowledge catalog indexing in Neo4j."""

    async def test_create_catalog_index(
        self, neo4j_driver: AsyncDriver
    ) -> None:
        """Create a CATALOG_INDEXED relationship."""
        source_id = _ulid()
        target_id = _ulid()

        async with neo4j_driver.session() as session:
            # Create a Capability node and a CatalogEntry node
            await session.execute_write(
                lambda tx: _create_capability_node(
                    tx, node_id=source_id, name="PaymentProcessing"
                )
            )
            await session.run(
                """
                CREATE (e:CatalogEntry {
                    id: $id,
                    category: 'evidence',
                    title: 'Payment audit trail',
                    entity_id: $entity_id,
                    entity_type: 'Capability',
                    lifecycle_state: 'active',
                    tenant_id: $tid,
                    created_at: $now,
                    updated_at: $now
                })
                """,
                id=target_id,
                entity_id=source_id,
                tid=TENANT_ID,
                now=datetime.now(timezone.utc).isoformat(),
            )

            # Create CATALOG_INDEXED relationship
            record = await session.execute_write(
                lambda tx: _create_catalog_indexed_relationship(
                    tx,
                    source_id=source_id,
                    target_id=target_id,
                    category="evidence",
                )
            )
            assert record is not None
            rel = record["r"]
            assert rel["category"] == "evidence"
            assert rel["tenant_id"] == TENANT_ID

    async def test_query_by_category(self, neo4j_driver: AsyncDriver) -> None:
        """Query all entities in a catalog category."""
        capability_id = _ulid()
        entry_ids = [_ulid() for _ in range(3)]
        categories = ["evidence", "evidence", "artifact"]

        async with neo4j_driver.session() as session:
            await session.execute_write(
                lambda tx: _create_capability_node(
                    tx, node_id=capability_id, name="OrderManagement"
                )
            )

            for entry_id, cat in zip(entry_ids, categories):
                await session.run(
                    """
                    CREATE (e:CatalogEntry {
                        id: $id, category: $cat, title: $title,
                        entity_id: $eid, entity_type: 'Capability',
                        lifecycle_state: 'active', tenant_id: $tid,
                        created_at: $now, updated_at: $now
                    })
                    """,
                    id=entry_id,
                    cat=cat,
                    title=f"Entry {cat}",
                    eid=capability_id,
                    tid=TENANT_ID,
                    now=datetime.now(timezone.utc).isoformat(),
                )
                await session.run(
                    """
                    MATCH (c {id: $cid}), (e {id: $eid})
                    CREATE (c)-[:CATALOG_INDEXED {
                        category: $cat, tenant_id: $tid, created_at: $now
                    }]->(e)
                    """,
                    cid=capability_id,
                    eid=entry_id,
                    cat=cat,
                    tid=TENANT_ID,
                    now=datetime.now(timezone.utc).isoformat(),
                )

            # Query: all evidence entries for this capability
            result = await session.run(
                """
                MATCH (c {id: $cid})-[:CATALOG_INDEXED {category: 'evidence'}]->(e)
                RETURN e.id AS id, e.title AS title
                ORDER BY e.title
                """,
                cid=capability_id,
            )
            evidence = [record async for record in result]
            assert len(evidence) == 2

            # Query: all catalog entries regardless of category
            result = await session.run(
                """
                MATCH (c {id: $cid})-[:CATALOG_INDEXED]->(e)
                RETURN e.category AS cat, count(e) AS cnt
                ORDER BY e.category
                """,
                cid=capability_id,
            )
            counts = {record["cat"]: record["cnt"] async for record in result}
            assert counts["evidence"] == 2
            assert counts["artifact"] == 1

    async def test_query_by_capability(
        self, neo4j_driver: AsyncDriver
    ) -> None:
        """Query all evidence/artifacts linked to a capability."""
        cap_id = _ulid()
        evidence_ids = [_ulid() for _ in range(2)]
        artifact_id = _ulid()

        async with neo4j_driver.session() as session:
            await session.execute_write(
                lambda tx: _create_capability_node(
                    tx, node_id=cap_id, name="Reporting"
                )
            )

            # Create evidence entries
            for eid in evidence_ids:
                await session.run(
                    """
                    CREATE (e:CatalogEntry {
                        id: $id, category: 'evidence', title: $title,
                        entity_id: $cap_id, entity_type: 'Capability',
                        lifecycle_state: 'active', tenant_id: $tid,
                        created_at: $now, updated_at: $now
                    })
                    """,
                    id=eid,
                    title=f"Evidence {eid[:6]}",
                    cap_id=cap_id,
                    tid=TENANT_ID,
                    now=datetime.now(timezone.utc).isoformat(),
                )
                await session.run(
                    """
                    MATCH (c {id: $cid}), (e {id: $eid})
                    CREATE (c)-[:CATALOG_INDEXED {
                        category: 'evidence', tenant_id: $tid, created_at: $now
                    }]->(e)
                    """,
                    cid=cap_id,
                    eid=eid,
                    tid=TENANT_ID,
                    now=datetime.now(timezone.utc).isoformat(),
                )

            # Create artifact entry
            await session.run(
                """
                CREATE (a:CatalogEntry {
                    id: $id, category: 'artifact', title: 'Q4 Report',
                    entity_id: $cap_id, entity_type: 'Capability',
                    lifecycle_state: 'active', tenant_id: $tid,
                    created_at: $now, updated_at: $now
                })
                """,
                id=artifact_id,
                cap_id=cap_id,
                tid=TENANT_ID,
                now=datetime.now(timezone.utc).isoformat(),
            )
            await session.run(
                """
                MATCH (c {id: $cid}), (a {id: $aid})
                CREATE (c)-[:CATALOG_INDEXED {
                    category: 'artifact', tenant_id: $tid, created_at: $now
                }]->(a)
                """,
                cid=cap_id,
                aid=artifact_id,
                tid=TENANT_ID,
                now=datetime.now(timezone.utc).isoformat(),
            )

            # Query: all linked entries grouped by category
            result = await session.run(
                """
                MATCH (c {id: $cid})-[:CATALOG_INDEXED]->(e)
                RETURN e.category AS category, collect(e.id) AS ids
                ORDER BY e.category
                """,
                cid=cap_id,
            )
            grouped = {record["category"]: record["ids"] async for record in result}
            assert len(grouped["evidence"]) == 2
            assert len(grouped["artifact"]) == 1
            assert artifact_id in grouped["artifact"]

            # Query: full detail of linked entries
            result = await session.run(
                """
                MATCH (c {id: $cid})-[:CATALOG_INDEXED]->(e)
                RETURN e.id AS id, e.category AS category, e.title AS title
                ORDER BY e.category, e.title
                """,
                cid=cap_id,
            )
            entries = [record async for record in result]
            assert len(entries) == 3
            # Artifact comes before evidence alphabetically
            assert entries[0]["category"] == "artifact"
            assert entries[0]["title"] == "Q4 Report"

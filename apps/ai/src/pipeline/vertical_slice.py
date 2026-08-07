#!/usr/bin/env python3
"""V6 OntologyAI — Vertical Slice Pipeline Orchestrator (Milestone 0.5).

Runs every architectural layer exactly once in a single async invocation:

 1. Connector fetch → Evidence
 2. Normalize (identity transform for mock)
 3. Entity resolution
 4. Graph build (Neo4j)
 5. Enterprise Knowledge Model write
 6. Decision engine
 7. Feasibility scoring
 8. Artifact projection
 9. Validation
10. Workspace publish

Usage
-----
Standalone::

    cd apps/ai && uv run python -m src.pipeline.vertical_slice

Or import and run programmatically::

    from src.pipeline.vertical_slice import VerticalSlicePipeline

    pipeline = VerticalSlicePipeline(neo4j_client=None, db_pool=None, qdrant_client=None)
    result = await pipeline.run()
"""

from __future__ import annotations

import asyncio
import logging
import sys
from typing import Any

from src.connectors.mock_notion_connector import MockNotionConnector
from src.connectors.registry import V6ConnectorRegistry
from src.entities.models import EvidenceRecord
from src.knowledge.entity_resolver import EntityResolver
from src.knowledge.enterprise_knowledge_model import EnterpriseKnowledgeModel
from src.knowledge.graph_builder import GraphBuilder
from src.pipeline.artifact_engine import ArtifactEngine
from src.pipeline.decision_engine import DecisionEngine
from src.pipeline.feasibility_engine import FeasibilityEngine
from src.pipeline.validation_engine import ValidationEngine

logger = logging.getLogger(__name__)

# ── Default workspace / tenant (overridable via constructor) ─────────────

DEFAULT_WORKSPACE_ID = "01J0X8X8X8X8X8X8X8X8X8X8X8WS"
DEFAULT_TENANT_ID = "tenant-v6-test"


class StageResult:
    """Captures the outcome of a single pipeline stage.

    Attributes
    ----------
    stage_name:
        Human-readable stage name.
    success:
        Whether the stage completed without error.
    data:
        Any data produced by the stage.
    error:
        Error message if the stage failed.
    """

    def __init__(
        self,
        stage_name: str,
        success: bool = True,
        data: Any = None,
        error: str = "",
    ) -> None:
        self.stage_name = stage_name
        self.success = success
        self.data = data
        self.error = error

    def __repr__(self) -> str:
        status = "✓" if self.success else "✗"
        return f"[{status}] {self.stage_name}"


class VerticalSlicePipeline:
    """End-to-end pipeline orchestrator for the vertical slice proof.

    Runs every architectural layer exactly once.  Each stage handles
    errors gracefully — if a stage fails, subsequent stages that depend
    on its output receive ``None`` and continue.  The final result
    includes a ``stage_results`` list with individual stage outcomes.

    Parameters
    ----------
    neo4j_client:
        An initialised ``Neo4jClient`` (or ``None`` if unavailable).
    db_pool:
        An ``asyncpg.Pool`` (or ``None`` if unavailable).
    qdrant_client:
        An ``AsyncQdrantClient`` (or ``None`` if unavailable).
    workspace_id:
        ULID of the workspace to operate on.
    tenant_id:
        ULID of the tenant.
    """

    def __init__(
        self,
        neo4j_client=None,
        db_pool=None,
        qdrant_client=None,
        workspace_id: str = DEFAULT_WORKSPACE_ID,
        tenant_id: str = DEFAULT_TENANT_ID,
        sources: list[str] | None = None,
        connector=None,
    ) -> None:
        self._neo4j = neo4j_client
        self._db = db_pool
        self._qdrant = qdrant_client
        self.workspace_id = workspace_id
        self.tenant_id = tenant_id

        # Connector — precedence: explicit connector > sources > MockNotionConnector (backward compat)
        if connector is not None:
            self.connector = connector
            self._sources: list[str] | None = None
        elif sources is not None:
            self.connector = None
            self._sources = sources
        else:
            self.connector = None
            self._sources = ["notion"]

        # Knowledge layer
        self.entity_resolver = EntityResolver(neo4j_client)
        self.graph_builder = GraphBuilder(neo4j_client)
        self.ekm = EnterpriseKnowledgeModel(db_pool)

        # Pipeline engines
        self.decision_engine = DecisionEngine(db_pool)
        self.feasibility_engine = FeasibilityEngine(db_pool)
        self.artifact_engine = ArtifactEngine(db_pool)
        self.validation_engine = ValidationEngine(db_pool)

        self.stage_results: list[StageResult] = []

    async def run(self) -> dict[str, Any]:
        """Execute the full 10-stage pipeline.

        Returns
        -------
        dict
            Result summary with all IDs and stage outcomes.
        """
        logger.info("=" * 60)
        logger.info("V6 Vertical Slice Pipeline — starting")
        logger.info("Workspace: %s  |  Tenant: %s", self.workspace_id, self.tenant_id)
        logger.info("=" * 60)

        results: dict[str, Any] = {
            "workspace_id": self.workspace_id,
            "tenant_id": self.tenant_id,
        }

        # ═══════════════════════════════════════════════════════════════
        # Stage 1: Ingest — Connector fetch
        # ═══════════════════════════════════════════════════════════════
        logger.info("── Stage 1: Ingest ──")
        evidence_list: list[EvidenceRecord] = []
        per_source_counts: dict[str, int] = {}
        try:
            if self.connector is not None:
                # Legacy mode: single connector (e.g. MockNotionConnector in tests)
                manifest = await self.connector.connect()
                logger.info("Connector manifest: %s v%s", manifest.name, manifest.version)
                evidence_list = await self.connector.fetch()
                per_source_counts[manifest.name] = len(evidence_list)
            else:
                # V6 registry mode: run all configured sources
                sources: list[str] = self._sources or ["notion"]
                per_source = await V6ConnectorRegistry.run_all(
                    tenant_id=self.tenant_id,
                    sources=sources,
                )
                per_source_counts = {src: len(recs) for src, recs in per_source.items()}
                for src_records in per_source.values():
                    evidence_list.extend(src_records)

            results["evidence_ids"] = [e.id for e in evidence_list]
            results["evidence_count"] = len(evidence_list)
            results["sources"] = per_source_counts
            self.stage_results.append(
                StageResult(
                    "1-ingest",
                    True,
                    {
                        "connector_mode": "connector" if self.connector is not None else "v6_registry",
                        "evidence_count": len(evidence_list),
                        "evidence_ids": results["evidence_ids"],
                        "sources": per_source_counts,
                    },
                )
            )
            logger.info("Ingested %d evidence records from %d source(s)", len(evidence_list), len(per_source_counts))
            for src, count in per_source_counts.items():
                logger.info("  %s: %d records", src, count)
        except Exception as exc:
            logger.exception("Stage 1 (Ingest) failed")
            results["evidence_ids"] = []
            results["evidence_count"] = 0
            results["sources"] = {}
            evidence_list = []
            self.stage_results.append(StageResult("1-ingest", False, error=str(exc)))

        # ═══════════════════════════════════════════════════════════════
        # Stage 2: Normalize
        # ═══════════════════════════════════════════════════════════════
        logger.info("── Stage 2: Normalize ──")
        # For mock data, evidence is already structured — identity transform
        normalized = evidence_list
        self.stage_results.append(
            StageResult("2-normalize", True, {"normalized_count": len(normalized)})
        )
        logger.info(
            "Normalized %d evidence records (identity transform)", len(normalized)
        )

        # ═══════════════════════════════════════════════════════════════
        # Stage 3: Entity Resolution
        # ═══════════════════════════════════════════════════════════════
        logger.info("── Stage 3: Entity Resolution ──")
        resolution_results = []
        try:
            if normalized:
                resolution_results = await self.entity_resolver.resolve_batch(
                    normalized, self.workspace_id
                )
            results["entities"] = [r.model_dump() for r in resolution_results]
            self.stage_results.append(
                StageResult(
                    "3-entity-resolution",
                    True,
                    {
                        "entity_count": len(resolution_results),
                        "entities": results["entities"],
                    },
                )
            )
            logger.info("Resolved %d entities", len(resolution_results))
            for r in resolution_results:
                logger.info(
                    "  %s %s (%s, confidence=%.2f)",
                    r.entity_type,
                    r.properties.get("name", ""),
                    r.merge_method,
                    r.confidence,
                )
        except Exception as exc:
            logger.exception("Stage 3 (Entity Resolution) failed")
            results["entities"] = []
            self.stage_results.append(
                StageResult("3-entity-resolution", False, error=str(exc))
            )

        # ═══════════════════════════════════════════════════════════════
        # Stage 4: Graph Build (Neo4j)
        # ═══════════════════════════════════════════════════════════════
        logger.info("── Stage 4: Graph Build ──")
        try:
            graph_result = await self.graph_builder.build_graph(
                resolution_results, normalized, self.workspace_id
            )
            results["graph"] = {
                "nodes_created": graph_result.nodes_created,
                "relationships_created": graph_result.relationships_created,
                "evidence_linked": graph_result.evidence_linked,
                "neo4j_available": graph_result.neo4j_available,
            }
            self.stage_results.append(
                StageResult("4-graph-build", True, results["graph"])
            )
            logger.info(
                "Graph build: %d nodes, %d relationships, %d links (Neo4j=%s)",
                graph_result.nodes_created,
                graph_result.relationships_created,
                graph_result.evidence_linked,
                graph_result.neo4j_available,
            )
        except Exception as exc:
            logger.exception("Stage 4 (Graph Build) failed")
            results["graph"] = {}
            self.stage_results.append(
                StageResult("4-graph-build", False, error=str(exc))
            )

        # ═══════════════════════════════════════════════════════════════
        # Stage 5: Enterprise Knowledge Model
        # ═══════════════════════════════════════════════════════════════
        logger.info("── Stage 5: Enterprise Knowledge Model ──")
        ekm_results = []
        try:
            for entity in resolution_results:
                state = await self.ekm.write_state(
                    entity_id=entity.entity_id,
                    entity_type=entity.entity_type,
                    tenant_id=self.tenant_id,
                    interpreted_state={
                        "label": entity.properties.get("name", ""),
                        "type": entity.entity_type,
                        "resolution_method": entity.merge_method,
                        "source_evidence": entity.evidence_id,
                    },
                    confidence=entity.confidence,
                    source_evidence_ids=[entity.evidence_id]
                    if entity.evidence_id
                    else [],
                )
                ekm_results.append(state)

                await self.ekm.write_entity_confidence(
                    entity_id=entity.entity_id,
                    entity_type=entity.entity_type,
                    tenant_id=self.tenant_id,
                    confidence=entity.confidence,
                )

            results["ekm"] = {"states_written": len(ekm_results)}
            self.stage_results.append(
                StageResult("5-ekm", True, {"states_written": len(ekm_results)})
            )
            logger.info("Wrote %d EKM states + confidences", len(ekm_results))
        except Exception as exc:
            logger.exception("Stage 5 (EKM) failed")
            results["ekm"] = {}
            self.stage_results.append(StageResult("5-ekm", False, error=str(exc)))

        # ═══════════════════════════════════════════════════════════════
        # Stage 6: Decision Engine
        # ═══════════════════════════════════════════════════════════════
        logger.info("── Stage 6: Decision Engine ──")
        decision_result = None
        try:
            decision_result = await self.decision_engine.run(
                workspace_id=self.workspace_id,
                tenant_id=self.tenant_id,
            )
            results["decision"] = {
                "id": decision_result.decision.get("id", ""),
                "title": decision_result.decision.get("title", ""),
                "option_count": len(decision_result.options),
            }
            self.stage_results.append(
                StageResult("6-decision-engine", True, results["decision"])
            )
            logger.info(
                "Decision '%s' with %d options",
                decision_result.decision.get("title"),
                len(decision_result.options),
            )
        except Exception as exc:
            logger.exception("Stage 6 (Decision Engine) failed")
            results["decision"] = {}
            self.stage_results.append(
                StageResult("6-decision-engine", False, error=str(exc))
            )

        # ═══════════════════════════════════════════════════════════════
        # Stage 7: Feasibility Scoring
        # ═══════════════════════════════════════════════════════════════
        logger.info("── Stage 7: Feasibility Scoring ──")
        feasibility_results = []
        try:
            if decision_result is not None:
                options = decision_result.options
                # Reconstruct Option objects for scoring
                from src.entities.models import Option

                option_objects = [Option(**opt) for opt in options]
                feasibility_results = await self.feasibility_engine.score_options(
                    option_objects
                )
            results["feasibility"] = [s.model_dump() for s in feasibility_results]
            self.stage_results.append(
                StageResult(
                    "7-feasibility",
                    True,
                    {
                        "scored_count": len(feasibility_results),
                    },
                )
            )
            logger.info("Scored %d options for feasibility", len(feasibility_results))
            for s in feasibility_results:
                logger.info(
                    "  %s: total=%.1f, tier=%s",
                    s.option_title,
                    s.weighted_total,
                    s.readiness_tier,
                )
        except Exception as exc:
            logger.exception("Stage 7 (Feasibility) failed")
            results["feasibility"] = []
            self.stage_results.append(
                StageResult("7-feasibility", False, error=str(exc))
            )

        # ═══════════════════════════════════════════════════════════════
        # Stage 8: Artifact Projection
        # ═══════════════════════════════════════════════════════════════
        logger.info("── Stage 8: Artifact Projection ──")
        artifact_result = None
        try:
            context = {
                "tenant_id": self.tenant_id,
                "decision": (decision_result.decision if decision_result else {}),
                "options": (decision_result.options if decision_result else []),
                "feasibility": [s.model_dump() for s in feasibility_results],
                "evidence": [e.model_dump() for e in normalized],
                "entities": [r.model_dump() for r in resolution_results],
            }
            artifact_result = await self.artifact_engine.project(
                artifact_type="executive-decision-brief",
                workspace_id=self.workspace_id,
                context=context,
            )
            results["artifact"] = {
                "id": artifact_result.artifact.get("id", ""),
                "type": "executive-decision-brief",
                "section_count": artifact_result.section_count,
            }
            self.stage_results.append(
                StageResult("8-artifact-projection", True, results["artifact"])
            )
            logger.info(
                "Projected artifact %s with %d sections",
                artifact_result.artifact.get("id"),
                artifact_result.section_count,
            )
        except Exception as exc:
            logger.exception("Stage 8 (Artifact Projection) failed")
            results["artifact"] = {}
            self.stage_results.append(
                StageResult("8-artifact-projection", False, error=str(exc))
            )

        # ═══════════════════════════════════════════════════════════════
        # Stage 9: Validation
        # ═══════════════════════════════════════════════════════════════
        logger.info("── Stage 9: Validation ──")
        validation_result = None
        try:
            validation_result = await self.validation_engine.validate(
                artifact_result=artifact_result,
                context=context if artifact_result else None,
            )
            results["validation"] = {
                "passed": validation_result.passed,
                "rules_checked": len(validation_result.results),
                "warnings": len(validation_result.warnings),
                "blocking_issues": validation_result.blocking_issues,
            }
            self.stage_results.append(
                StageResult("9-validation", True, results["validation"])
            )
            logger.info(
                "Validation: passed=%s (%d rules, %d warnings)",
                validation_result.passed,
                len(validation_result.results),
                len(validation_result.warnings),
            )
        except Exception as exc:
            logger.exception("Stage 9 (Validation) failed")
            results["validation"] = {}
            self.stage_results.append(
                StageResult("9-validation", False, error=str(exc))
            )

        # ═══════════════════════════════════════════════════════════════
        # Stage 10: Publish to Workspace
        # ═══════════════════════════════════════════════════════════════
        logger.info("── Stage 10: Publish ──")
        try:
            # In production this would call workspace_store.update_workspace_status
            # and add entities to the workspace.  For the vertical slice, we
            # mark the workspace as published in-memory.
            results["publish"] = {
                "workspace_id": self.workspace_id,
                "status": "published",
                "artifact_count": 1 if artifact_result else 0,
                "entity_count": len(resolution_results),
                "evidence_count": len(normalized),
            }
            self.stage_results.append(
                StageResult("10-publish", True, results["publish"])
            )
            logger.info("Workspace %s marked as published", self.workspace_id)
        except Exception as exc:
            logger.exception("Stage 10 (Publish) failed")
            results["publish"] = {}
            self.stage_results.append(StageResult("10-publish", False, error=str(exc)))

        # ═══════════════════════════════════════════════════════════════
        # Summary
        # ═══════════════════════════════════════════════════════════════
        results["status"] = "published"
        results["stage_results"] = [
            {
                "name": s.stage_name,
                "success": s.success,
                "error": s.error,
            }
            for s in self.stage_results
        ]

        stages_ok = sum(1 for s in self.stage_results if s.success)
        stages_total = len(self.stage_results)
        logger.info("=" * 60)
        logger.info("Pipeline complete: %d/%d stages passed", stages_ok, stages_total)
        logger.info("=" * 60)

        return results


# ── Standalone entrypoint ────────────────────────────────────────────────


async def _main() -> None:
    """Run the vertical slice pipeline as a standalone script."""
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%H:%M:%S",
        stream=sys.stdout,
    )

    pipeline = VerticalSlicePipeline(
        neo4j_client=None,
        db_pool=None,
        qdrant_client=None,
    )

    result = await pipeline.run()

    print("\n" + "=" * 60)
    print("PIPELINE RESULT SUMMARY")
    print("=" * 60)
    print(f"  Status:           {result['status']}")
    print(f"  Workspace:        {result['workspace_id']}")
    print(f"  Evidence:         {result.get('evidence_count', 0)} records")
    print(f"  Entities:         {len(result.get('entities', []))}")
    print(f"  Decision:         {result.get('decision', {}).get('title', 'N/A')}")
    print(f"  Feasibility:      {len(result.get('feasibility', []))} scored")
    print(f"  Artifact:         {result.get('artifact', {}).get('type', 'N/A')}")
    print(
        f"  Validation:       {'PASSED' if result.get('validation', {}).get('passed') else 'FAILED'}"
    )
    stages = result.get("stage_results", [])
    for s in stages:
        status = "✓" if s["success"] else "✗"
        print(f"  {status} {s['name']}{' — ' + s['error'] if s['error'] else ''}")
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(_main())

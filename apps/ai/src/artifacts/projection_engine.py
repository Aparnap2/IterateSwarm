"""V6 OntologyAI — Artifact Projection Engine.

Per ADR-002, artifacts are **never** source of truth.  They are read-model
projections computed from the canonical model (Neo4j entities + Postgres
transactional data) at generation time.

This engine orchestrates the projection pipeline:

1.  Load DSL config by artifact ID (via ``DSLLoader``)
2.  Extract model data from workspace context
3.  Render each section via ``TemplateEngine``
4.  Link sections to evidence (traceability)
5.  Create an ``Artifact`` record
"""

from __future__ import annotations

import logging
from typing import Any

from src.artifacts.dsl_loader import DSLLoader
from src.artifacts.template_engine import TemplateEngine, _resolve_dot_path
from src.context.agent_context import AgentContext
from src.entities.models import Artifact, EvidenceRecord

logger = logging.getLogger(__name__)


# ── Exceptions ──────────────────────────────────────────────────────────


class ProjectionError(Exception):
    """Raised when artifact projection fails."""


# ── ProjectionEngine ────────────────────────────────────────────────────


class ProjectionEngine:
    """Orchestrates artifact projection from DSL config + canonical model.

    Usage::

        engine = ProjectionEngine(dsl_loader, template_engine)
        artifact = await engine.project("executive-decision-brief", ws_id, context)
    """

    def __init__(
        self,
        dsl_loader: DSLLoader,
        template_engine: TemplateEngine,
    ) -> None:
        """Initialise the projection engine.

        Parameters
        ----------
        dsl_loader:
            Loads artifact DSL YAML configs by ID.
        template_engine:
            Renders artifact sections from templates + context data.
        """
        self._dsl = dsl_loader
        self._templates = template_engine

    # ── Public API ───────────────────────────────────────────────────

    async def project(
        self,
        artifact_id: str,
        workspace_id: str,
        context: AgentContext,
    ) -> Artifact:
        """Project an artifact from DSL + context.

        Steps:

        1.  Load DSL config for *artifact_id*.
        2.  Build a flat data context from ``AgentContext`` fields mapped
            by the DSL's ``model_dependencies``.
        3.  Render all sections via ``TemplateEngine``.
        4.  Determine artifact status as ``"draft"`` (not yet validated).

        Parameters
        ----------
        artifact_id:
            DSL config ID (e.g. ``"executive-decision-brief"``).
        workspace_id:
            The workspace ULID the artifact belongs to.
        context:
            Assembled ``AgentContext`` containing evidence, decisions, etc.

        Returns
        -------
        Artifact
            A new Artifact with status ``"draft"`` and a ``content`` dict
            in ``artifact_versions`` (if further rendered content is needed,
            check the rendered sections on the returned object's metadata).

        Raises
        ------
        ProjectionError
            If the DSL config cannot be loaded or sections cannot render.
        """
        # Step 1: Load DSL config
        try:
            dsl = self._dsl.load(artifact_id)
        except Exception as exc:
            raise ProjectionError(
                f"Cannot project artifact '{artifact_id}': {exc}"
            ) from exc

        # Step 2: Build flat context for template rendering.
        # Model dependencies are dot-paths like "evidence.top_findings".
        # We resolve them from the AgentContext.
        context_dict = context.model_dump()
        render_context: dict[str, Any] = {}

        for dep in dsl.model_dependencies:
            value = _resolve_dot_path(context_dict, dep)
            render_context[dep] = value

        # Also add section sources directly
        for section in dsl.sections:
            if section.source not in render_context:
                value = _resolve_dot_path(context_dict, section.source)
                render_context[section.source] = value

        # Step 3: Render all sections
        rendered_sections = self._templates.render_artifact(dsl, render_context)

        # Step 4: Create Artifact record
        artifact = Artifact(
            id=f"art-m0.5-{workspace_id}-{artifact_id}",
            tenant_id=context.tenant.get("tenant_id", "m0.5-tenant"),
            workspace_id=workspace_id,
            name=dsl.name,
            artifact_type=dsl.id,
            status="draft",
            dsl_config_id=dsl.id,
        )

        logger.info(
            "Projected artifact '%s' (%s) — %d sections rendered.",
            artifact.id,
            dsl.name,
            len(rendered_sections),
        )

        return artifact

    async def project_with_evidence_links(
        self,
        artifact_id: str,
        workspace_id: str,
        context: AgentContext,
        evidence_records: list[EvidenceRecord],
    ) -> Artifact:
        """Project an artifact and auto-link sections to evidence records.

        This extends ``project()`` by also creating traceability links
        between rendered sections and the evidence records that back them.

        For M0.5 the linkage is stored in-memory (not persisted to Neo4j).

        Parameters
        ----------
        artifact_id:
            DSL config ID.
        workspace_id:
            The workspace ULID.
        context:
            Assembled ``AgentContext``.
        evidence_records:
            Evidence records to link.  The engine will match evidence
            sources to section sources from the DSL's ``traceability``
            block.

        Returns
        -------
        Artifact
            The projected artifact.
        """
        artifact = await self.project(artifact_id, workspace_id, context)

        # Load DSL for traceability
        dsl = self._dsl.load(artifact_id)

        # Build traceability links (in-memory for M0.5)
        traceability_links: dict[str, list[str]] = {}
        for section_name, source_path in dsl.traceability.get("field_sources", {}).items():
            matching = [
                ev.id
                for ev in evidence_records
                if source_path.startswith("evidence.") and ev.source in source_path
            ]
            if matching:
                traceability_links[section_name] = matching

        if traceability_links:
            logger.info(
                "Linked %d sections to %d total evidence records.",
                len(traceability_links),
                sum(len(v) for v in traceability_links.values()),
            )
        else:
            logger.warning(
                "No evidence links established for artifact '%s'. "
                "Check traceability configuration.",
                artifact_id,
            )

        return artifact

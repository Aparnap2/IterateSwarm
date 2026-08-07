"""Artifact Engine — projects artifacts from canonical model data.

For the V6 vertical slice, projects an "executive-decision-brief" artifact
using evidence, decisions, and feasibility data.  The DSL configuration
for this artifact type (V6 spec §6.2 #1) defines 7 sections:

1. Header
2. Executive Summary (LLM-augmented)
3. Key Evidence
4. Active Decisions
5. Recommendations
6. Risk Assessment
7. Downstream Impact

For Milestone 0.5, all sections are populated deterministically (no LLM).
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from src.entities.models import Artifact

logger = logging.getLogger(__name__)

# ── Fixed ULID ───────────────────────────────────────────────────────────

ARTIFACT_ID = "01J0X8X8X8X8X8X8X8X8X8X8X8AR"


class ArtifactResult(BaseModel):
    """Result of projecting an artifact.

    Attributes
    ----------
    artifact:
        The created Artifact entity (as dict).
    content:
        Section-keyed content for artifact projection.
    section_count:
        Number of content sections populated.
    """

    model_config = ConfigDict(extra="forbid", strict=True, from_attributes=True)

    artifact: dict[str, Any]
    content: dict[str, Any] = Field(default_factory=dict)
    section_count: int = 0


class ArtifactEngine:
    """Projects artifacts from canonical model data.

    Parameters
    ----------
    db_pool:
        An ``asyncpg.Pool`` (or compatible). May be ``None``.
    """

    def __init__(self, db_pool) -> None:
        self._pool = db_pool

    async def project(
        self,
        artifact_type: str,
        workspace_id: str,
        context: dict[str, Any] | None = None,
    ) -> ArtifactResult:
        """Project an artifact from contextual data.

        Parameters
        ----------
        artifact_type:
            DSL artifact type ID (e.g. ``"executive-decision-brief"``).
        workspace_id:
            ULID of the owning workspace.
        context:
            Dictionary of contextual data for projection.  Expected keys:
            - ``tenant_id``
            - ``decision`` (dict)
            - ``options`` (list of dicts)
            - ``feasibility`` (list of FeasibilityResult dicts)
            - ``evidence`` (list of EvidenceRecord dicts)
            - ``entities`` (list of EntityResolutionResult dicts)

        Returns
        -------
        ArtifactResult
            The projected artifact with section content.
        """
        tenant_id = (context or {}).get("tenant_id", "tenant-v6-test")

        artifact = Artifact(
            id=ARTIFACT_ID,
            tenant_id=tenant_id,
            workspace_id=workspace_id,
            name="Executive Decision Brief — Onboarding Improvement",
            artifact_type=artifact_type,
            status="draft",
            dsl_config_id="executive-decision-brief",
        )

        content = await self._build_sections(artifact, context or {})

        logger.info(
            "Projected artifact %s (%s) with %d sections",
            artifact.id,
            artifact_type,
            len(content),
        )

        return ArtifactResult(
            artifact=artifact.model_dump(),
            content=content,
            section_count=len(content),
        )

    async def _build_sections(
        self,
        artifact: Artifact,
        context: dict[str, Any],
    ) -> dict[str, Any]:
        """Build artifact content sections from context.

        Parameters
        ----------
        artifact:
            The artifact being projected.
        context:
            Canonical model data for content population.

        Returns
        -------
        dict[str, Any]
            Section-keyed content.
        """
        options = context.get("options", [])
        feasibility = context.get("feasibility", [])
        evidence = context.get("evidence", [])
        entities = context.get("entities", [])
        decision = context.get("decision", {})

        # Section 1: Header
        header = {
            "title": artifact.name,
            "artifact_id": artifact.id,
            "workspace_id": artifact.workspace_id,
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "status": artifact.status,
        }

        # Section 2: Executive Summary
        kpi_evidence = next(
            (e for e in evidence if "drop-off" in str(e.get("structured_data", {}))),
            None,
        )
        drop_rate = "40%"
        if kpi_evidence:
            sd = kpi_evidence.get("structured_data", {})
            drop_rate = f"{sd.get('current_value', 40)}%"

        executive_summary = {
            "problem": (
                f"Customer onboarding currently takes 21 days with a {drop_rate} "
                "user drop-off rate. Customer interviews confirm frustration "
                "with the manual approval process."
            ),
            "key_findings": [
                "Manual manager approval is the primary bottleneck "
                "(avg 4.5 days delay)",
                "40% of new users drop off before completing onboarding",
                "Customer sentiment is frustrated — three customers cited "
                "onboarding delay as a churn risk",
            ],
            "decision_required": decision.get("title", "Improve onboarding process"),
        }

        # Section 3: Key Evidence
        key_evidence = []
        for ev in evidence:
            sd = ev.get("structured_data", {})
            key_evidence.append(
                {
                    "id": ev.get("id", ""),
                    "source": ev.get("source", ""),
                    "title": sd.get("title", "Untitled"),
                    "confidence": ev.get("confidence", 0.0),
                    "summary": sd.get("key_quotes", [sd.get("metric_name", "")]),
                }
            )

        # Section 4: Active Decisions
        active_decisions = {
            "id": decision.get("id", ""),
            "title": decision.get("title", ""),
            "status": decision.get("status", "assessing"),
            "option_count": len(options),
        }

        # Section 5: Recommendations
        recommendations = []
        sorted_feasibility = sorted(
            feasibility,
            key=lambda f: f.get("weighted_total", 0),
            reverse=True,
        )
        for i, fs in enumerate(sorted_feasibility, 1):
            recommendations.append(
                {
                    "rank": i,
                    "option_id": fs.get("option_id", ""),
                    "option_title": fs.get("option_title", ""),
                    "weighted_total": fs.get("weighted_total", 0),
                    "readiness_tier": fs.get("readiness_tier", "review"),
                }
            )

        # Section 6: Risk Assessment
        risk_assessment = {
            "risks": [
                {
                    "risk": "Engineering delay — automation may take longer "
                    "than estimated 6 weeks",
                    "severity": 60,
                    "probability": 0.4,
                    "mitigation": "Phase rollout: automate approval first, "
                    "provisioning second",
                },
                {
                    "risk": "Stakeholder resistance — People Ops may resist "
                    "process changes",
                    "severity": 40,
                    "probability": 0.3,
                    "mitigation": "Early engagement with People Ops team; "
                    "include them in solution design",
                },
            ],
        }

        # Section 7: Downstream Impact
        downstream_impact = {
            "positive": [
                "Reduced time-to-productivity for new hires",
                "Improved NPS from faster onboarding",
                "Scalable process that works for 10x headcount growth",
            ],
            "negative": [
                "Short-term disruption during transition",
                "Engineering resources diverted from other priorities",
            ],
            "affected_entities": [
                {
                    "type": ent.get("entity_type"),
                    "name": ent.get("properties", {}).get("name"),
                }
                for ent in entities
            ],
        }

        return {
            "Header": header,
            "Executive Summary": executive_summary,
            "Key Evidence": key_evidence,
            "Active Decisions": active_decisions,
            "Recommendations": recommendations,
            "Risk Assessment": risk_assessment,
            "Downstream Impact": downstream_impact,
        }

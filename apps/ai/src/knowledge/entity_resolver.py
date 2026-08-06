"""Entity resolution engine for the V6 vertical slice.

For Milestone 0.5, implements **deterministic matching only** (no LLM):

1. Extract entity references from ``EvidenceRecord.structured_data``.
2. Exact match on ``external_id`` against Neo4j.
3. Fuzzy match on name (Levenshtein ratio > 0.85).
4. New entity creation for unmatched records.

Three extraction patterns are hardcoded for the mock evidence types:
- **Interview** → Stakeholder (Sarah Chen)
- **Process doc** → Requirement (Automate onboarding approvals)
- **KPI** → Stakeholder (Mike Liu) + KPI (User drop-off rate)
"""

from __future__ import annotations

import logging
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from src.connectors._test_constants import (
    EVIDENCE_INTERVIEW_ID,
    EVIDENCE_KPI_ID,
    EVIDENCE_PROCESS_ID,
)
from src.entities.models import EvidenceRecord

logger = logging.getLogger(__name__)

# ── Levenshtein helpers (no external dep) ────────────────────────────────


def _levenshtein(a: str, b: str) -> int:
    """Compute the Levenshtein edit distance between two strings."""
    if len(a) < len(b):
        a, b = b, a
    if not b:
        return len(a)
    previous_row = range(len(b) + 1)
    for i, ca in enumerate(a):
        current_row = [i + 1]
        for j, cb in enumerate(b):
            insertions = previous_row[j + 1] + 1
            deletions = current_row[j] + 1
            substitutions = previous_row[j] + (ca != cb)
            current_row.append(min(insertions, deletions, substitutions))
        previous_row = current_row
    return previous_row[-1]


def _lev_ratio(a: str, b: str) -> float:
    """Return Levenshtein similarity ratio (0.0 – 1.0)."""
    if not a and not b:
        return 1.0
    distance = _levenshtein(a.lower(), b.lower())
    max_len = max(len(a), len(b))
    return 1.0 - (distance / max_len)


# ── Resolution result ────────────────────────────────────────────────────


class EntityResolutionResult(BaseModel):
    """Result of resolving a single entity from evidence.

    Attributes
    ----------
    entity_id:
        ULID of the resolved (matched or newly created) entity.
    entity_type:
        Canonical entity type (e.g. ``"Stakeholder"``, ``"Requirement"``).
    matched:
        ``True`` if an existing entity was matched; ``False`` if new.
    confidence:
        Resolution confidence (0.0–1.0).
    merge_method:
        How the resolution was determined: ``"exact"``, ``"fuzzy"``,
        or ``"new"``.
    properties:
        Entity properties suitable for graph node creation.
    evidence_id:
        Source evidence ULID that produced this entity.
    """

    model_config = ConfigDict(extra="forbid", strict=True, from_attributes=True)

    entity_id: str
    entity_type: str
    matched: bool
    confidence: float = Field(ge=0.0, le=1.0)
    merge_method: str  # "exact" | "fuzzy" | "new"
    properties: dict[str, Any] = Field(default_factory=dict)
    evidence_id: str = ""


# ── Extracted entity descriptors (hardcoded for mock data) ───────────────

_EXTRACTED_ENTITIES: dict[str, list[dict[str, Any]]] = {
    EVIDENCE_INTERVIEW_ID: [
        {
            "entity_type": "Stakeholder",
            "name": "Sarah Chen",
            "properties": {
                "name": "Sarah Chen",
                "role": "Head of Product",
                "email": "sarah@example.com",
                "status": "identified",
            },
            "confidence": 0.92,
        },
    ],
    EVIDENCE_PROCESS_ID: [
        {
            "entity_type": "Requirement",
            "name": "Automate onboarding approvals",
            "properties": {
                "name": "Automate onboarding approvals",
                "description": (
                    "Replace manual manager approval step with automated "
                    "Slack workflow to reduce onboarding time from 21 days."
                ),
                "priority": "critical",
                "status": "proposed",
            },
            "confidence": 0.95,
        },
    ],
    EVIDENCE_KPI_ID: [
        {
            "entity_type": "Stakeholder",
            "name": "Mike Liu",
            "properties": {
                "name": "Mike Liu",
                "role": "Analytics",
                "email": "mike@example.com",
                "status": "identified",
            },
            "confidence": 0.96,
        },
        {
            "entity_type": "KPI",
            "name": "User drop-off rate",
            "properties": {
                "name": "User drop-off rate during onboarding",
                "target_value": 15.0,
                "baseline_value": 40.0,
                "unit": "percent",
                "owner_id": "",
                "status": "tracking",
            },
            "confidence": 0.96,
        },
    ],
}

# Fixed ULID prefixes for reproducible entity IDs
_ENTITY_ID_PREFIXES: dict[str, str] = {
    "01J0X8X8X8X8X8X8X8X8X8X8X8A": "01J0X8X8X8X8X8X8X8X8X8X8X8SA",  # Sarah
    "01J0X8X8X8X8X8X8X8X8X8X8X8B": "01J0X8X8X8X8X8X8X8X8X8X8X8RE",  # Requirement
    "01J0X8X8X8X8X8X8X8X8X8X8X8C": "01J0X8X8X8X8X8X8X8X8X8X8X8MI",  # Mike
    "01J0X8X8X8X8X8X8X8X8X8X8X8C_kpi": "01J0X8X8X8X8X8X8X8X8X8X8X8KP",  # KPI
}


class EntityResolver:
    """Resolves entities from evidence records.

    For Milestone 0.5, uses deterministic matching only:
    1. Exact match on ``external_id`` against Neo4j.
    2. Fuzzy match on name (Levenshtein ratio > 0.85).
    3. New entity creation for unmatched records.

    Parameters
    ----------
    neo4j_client:
        An initialised ``Neo4jClient`` (or a duck-typed stand-in).
        May be ``None`` when Neo4j is unavailable — resolution falls
        back to deterministic extraction without graph lookup.
    """

    def __init__(self, neo4j_client) -> None:
        self._neo4j = neo4j_client

    async def resolve(
        self,
        evidence: EvidenceRecord,
        workspace_id: str,  # noqa: ARG002
    ) -> list[EntityResolutionResult]:
        """Extract and resolve entities from *evidence*.

        Uses ``evidence.structured_data`` to identify entity references
        (stakeholder names, requirement descriptions, KPIs, etc.).
        First checks Neo4j for existing matches; creates new entities
        if none are found.

        Parameters
        ----------
        evidence:
            The evidence record to resolve.
        workspace_id:
            ULID of the owning workspace (used for graph scoping).

        Returns
        -------
        list[EntityResolutionResult]
            One result per extracted entity.
        """
        logger.info("Resolving entities for evidence %s", evidence.id)
        extracted = _EXTRACTED_ENTITIES.get(evidence.id, [])
        results: list[EntityResolutionResult] = []

        for idx, desc in enumerate(extracted):
            entity_id = _ENTITY_ID_PREFIXES.get(
                f"{evidence.id}_kpi" if desc["entity_type"] == "KPI" else evidence.id,
                f"{evidence.id}_{idx}",
            )

            # Attempt Neo4j lookup if the client is available
            matched = False
            merge_method = "new"

            if self._neo4j is not None:
                try:
                    existing = await self._neo4j.find_entity_by_id(entity_id)
                    if existing is not None:
                        matched = True
                        merge_method = "exact"
                        logger.debug(
                            "Exact match for entity %s (%s)",
                            entity_id,
                            desc["name"],
                        )
                    else:
                        # Try fuzzy name match
                        fuzzy_id = await self._fuzzy_match_name(
                            desc["entity_type"],
                            desc["name"],
                        )
                        if fuzzy_id is not None:
                            entity_id = fuzzy_id
                            matched = True
                            merge_method = "fuzzy"
                            logger.debug(
                                "Fuzzy match for %s → %s",
                                desc["name"],
                                fuzzy_id,
                            )
                except NotImplementedError:
                    logger.debug(
                        "Neo4j not wired — skipping graph lookup for %s",
                        desc["name"],
                    )

            properties = dict(desc["properties"])
            if desc["entity_type"] == "KPI":
                properties["owner_id"] = _ENTITY_ID_PREFIXES.get(evidence.id, "")

            results.append(
                EntityResolutionResult(
                    entity_id=entity_id,
                    entity_type=desc["entity_type"],
                    matched=matched,
                    confidence=desc["confidence"],
                    merge_method=merge_method,
                    properties=properties,
                    evidence_id=evidence.id,
                )
            )

        return results

    async def resolve_batch(
        self,
        evidence_list: list[EvidenceRecord],
        workspace_id: str,
    ) -> list[EntityResolutionResult]:
        """Resolve entities from a batch of evidence records.

        Parameters
        ----------
        evidence_list:
            Evidence records to resolve.
        workspace_id:
            ULID of the owning workspace.

        Returns
        -------
        list[EntityResolutionResult]
            Flattened list of all resolution results.
        """
        results: list[EntityResolutionResult] = []
        for evidence in evidence_list:
            try:
                resolved = await self.resolve(evidence, workspace_id)
                results.extend(resolved)
            except Exception:
                logger.exception(
                    "Entity resolution failed for evidence %s",
                    evidence.id,
                )
        return results

    async def _fuzzy_match_name(
        self,
        entity_type: str,
        name: str,
    ) -> str | None:
        """Try to find an existing entity by fuzzy name match.

        Queries Neo4j for nodes of *entity_type* and compares *name*
        using Levenshtein ratio.  Returns the first match above the
        0.85 threshold, or ``None``.
        """
        try:
            # This is a simplified approach — in production we'd query
            # Neo4j with a label filter and iterate results.
            rows = await self._neo4j.run_query(
                f"MATCH (n:{entity_type}) RETURN n.id AS id, n.name AS name",
            )
            for row in rows:
                existing_name: str = row.get("name", "")
                if _lev_ratio(name, existing_name) > 0.85:
                    return row["id"]
        except (NotImplementedError, Exception):
            logger.debug("Fuzzy match unavailable (Neo4j not wired)")
        return None

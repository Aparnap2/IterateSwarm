"""Enterprise Knowledge Model (EKM) — interpreted business state store.

While the knowledge graph stores entity-relationship triples, the EKM
stores what the business *means*: interpreted confidence, derived metrics,
business-specific classifications.

The EKM writes to the ``enterprise_knowledge`` and
``entity_confidence_history`` tables in PostgreSQL.  When the database
is unavailable, operations are in-memory only (returned as results but
not persisted).
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

logger = logging.getLogger(__name__)


# ── In-memory fallback store ─────────────────────────────────────────────

_in_memory_state: dict[str, dict[str, Any]] = {}
_in_memory_confidence: dict[str, dict[str, Any]] = {}


class EnterpriseKnowledgeModel:
    """Stores interpreted business state, separate from raw graph relationships.

    Parameters
    ----------
    db_pool:
        An ``asyncpg.Pool`` (or compatible duck-typed pool).
        May be ``None`` — all operations fall back to in-memory dicts.
    """

    def __init__(self, db_pool) -> None:
        self._pool = db_pool
        self._available: bool | None = None  # lazily detected

    async def _check_availability(self) -> bool:
        """Probe database reachability (cached after first check)."""
        if self._available is not None:
            return self._available
        if self._pool is None:
            self._available = False
            return False
        try:
            async with self._pool.acquire() as conn:  # type: ignore[union-attr]
                await conn.execute("SELECT 1")
            self._available = True
        except Exception:
            logger.info("Database not available — EKM using in-memory fallback")
            self._available = False
        return self._available

    async def write_state(
        self,
        entity_id: str,
        entity_type: str,
        tenant_id: str,
        interpreted_state: dict[str, Any],
        confidence: float,
        source_evidence_ids: list[str],
    ) -> dict[str, Any]:
        """Write interpreted business state for an entity.

        Parameters
        ----------
        entity_id:
            ULID of the entity.
        entity_type:
            Canonical entity type (e.g. ``"Stakeholder"``).
        tenant_id:
            ULID of the owning tenant.
        interpreted_state:
            Business-meaningful state (labels, classifications,
            derived metrics).
        confidence:
            Aggregate confidence for this state (0.0–1.0).
        source_evidence_ids:
            ULIDs of evidence records that informed this state.

        Returns
        -------
        dict
            The written record, either from the database or in-memory.
        """
        record = {
            "entity_id": entity_id,
            "entity_type": entity_type,
            "tenant_id": tenant_id,
            "interpreted_state": interpreted_state,
            "confidence": confidence,
            "source_evidence_ids": source_evidence_ids,
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }

        if await self._check_availability():
            try:
                async with self._pool.acquire() as conn:  # type: ignore[union-attr]
                    await conn.execute(
                        """
                        INSERT INTO enterprise_knowledge
                            (entity_id, entity_type, tenant_id, interpreted_state,
                             confidence, source_evidence_ids, updated_at)
                        VALUES ($1, $2, $3, $4::jsonb, $5, $6::jsonb, $7)
                        ON CONFLICT (entity_id)
                        DO UPDATE SET
                            interpreted_state = $4::jsonb,
                            confidence = $5,
                            source_evidence_ids = $6::jsonb,
                            updated_at = $7
                        """,
                        entity_id,
                        entity_type,
                        tenant_id,
                        interpreted_state,
                        confidence,
                        source_evidence_ids,
                        record["updated_at"],
                    )
                logger.debug("Wrote EKM state for entity %s", entity_id)
            except Exception:
                logger.exception("Failed to write EKM state for %s", entity_id)
                _in_memory_state[entity_id] = record
        else:
            _in_memory_state[entity_id] = record

        return record

    async def get_state(
        self,
        entity_id: str,
        entity_type: str,  # noqa: ARG002
    ) -> dict[str, Any] | None:
        """Get current interpreted state for an entity.

        Parameters
        ----------
        entity_id:
            ULID of the entity.
        entity_type:
            Canonical entity type (used for lookup filtering).

        Returns
        -------
        dict | None
            The interpreted state record, or ``None`` if not found.
        """
        if await self._check_availability():
            try:
                async with self._pool.acquire() as conn:  # type: ignore[union-attr]
                    row = await conn.fetchrow(
                        "SELECT * FROM enterprise_knowledge WHERE entity_id = $1",
                        entity_id,
                    )
                    if row is not None:
                        return dict(row)
            except Exception:
                logger.exception("Failed to read EKM state for %s", entity_id)

        return _in_memory_state.get(entity_id)

    async def write_entity_confidence(
        self,
        entity_id: str,
        entity_type: str,
        tenant_id: str,
        confidence: float,
    ) -> dict[str, Any]:
        """Update entity confidence derived from linked evidence confidences.

        Confidence formula (from V6 spec §3.4):
        ``weighted_avg of linked evidence confidences`` weighted by
        evidence freshness (newer evidence has higher weight).

        For the vertical slice mock, confidence is stored directly.

        Parameters
        ----------
        entity_id:
            ULID of the entity.
        entity_type:
            Canonical entity type.
        tenant_id:
            ULID of the owning tenant.
        confidence:
            Computed confidence value (0.0–1.0).

        Returns
        -------
        dict
            The confidence record.
        """
        record = {
            "entity_id": entity_id,
            "entity_type": entity_type,
            "tenant_id": tenant_id,
            "confidence": confidence,
            "computed_at": datetime.now(timezone.utc).isoformat(),
        }

        if await self._check_availability():
            try:
                async with self._pool.acquire() as conn:  # type: ignore[union-attr]
                    await conn.execute(
                        """
                        INSERT INTO entity_confidence_history
                            (entity_id, entity_type, tenant_id, confidence, computed_at)
                        VALUES ($1, $2, $3, $4, $5)
                        """,
                        entity_id,
                        entity_type,
                        tenant_id,
                        confidence,
                        record["computed_at"],
                    )
                logger.debug(
                    "Wrote confidence for entity %s: %.2f", entity_id, confidence
                )
            except Exception:
                logger.exception("Failed to write confidence for %s", entity_id)
                _in_memory_confidence[entity_id] = record
        else:
            _in_memory_confidence[entity_id] = record

        return record

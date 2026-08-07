"""Mission Timeline & Versioning — immutable, append-only operational history.

Sprint 1 of Operational Readiness. Provides the foundation all later
demonstrations build on:

* Enterprise Timeline
* Mission Diff               (compare two snapshots)
* Explainability             (read the decision/event chain)
* Audit / replay             (reprocess the append-only stream)
* Operational continuity     (restart from a snapshot, not from 5000 events)

Design (per architecture freeze — no new runtimes or abstractions):

* ``timeline_events``  — generic, append-only, per-entity *immutable version*.
  ``entity_type`` is ``mission``, ``workspace``, ``decision``, ``evidence``,
  ``knowledge``… so the SAME store powers every business thread (workspace
  activity, decision history, AI-employee activity) without a second event
  store. Version is ``MAX(version)+1`` scoped to ``(entity_type, entity_id)``;
  enforced by a unique constraint, so every event is a total-ordered commit.
* ``mission_snapshots`` — point-in-time captures of the composed mission state.
  Restart reads the latest snapshot instead of replaying the whole stream;
  diffing two snapshots is the "yesterday vs today" comparison.
* ``mission_state`` is NOT touched (the Go core owns it).

Event types are frozen to business verbs (no infra events). Appending an
unknown type is a programming error, surfaced loudly, not silently persisted.
"""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import Any, Iterable, Mapping, Sequence

import asyncpg

logger = logging.getLogger(__name__)

_TIMELINE_TABLE = "timeline_events"
_SNAPSHOT_TABLE = "mission_snapshots"

# ─────────────────────────────────────────────────────────────────────
# Schema — purely additive (never touches `mission_state`). Parametrised by
# table name so callers can isolate test tables.
# ─────────────────────────────────────────────────────────────────────
def _timeline_ddl(table: str) -> str:
    return f"""
CREATE TABLE IF NOT EXISTS {table} (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    entity_type VARCHAR(64) NOT NULL,
    entity_id VARCHAR(100) NOT NULL,
    version BIGINT NOT NULL,
    event_type VARCHAR(64) NOT NULL,
    actor VARCHAR(255),
    source VARCHAR(100),
    payload JSONB,
    causation_id UUID,
    correlation_id UUID,
    created_at TIMESTAMP DEFAULT NOW(),
    UNIQUE (entity_type, entity_id, version)
);
CREATE INDEX IF NOT EXISTS idx_{table}_entity
    ON {table} (entity_type, entity_id, version);
CREATE INDEX IF NOT EXISTS idx_{table}_correlation
    ON {table} (correlation_id);
"""


def _snapshot_ddl(table: str) -> str:
    return f"""
CREATE TABLE IF NOT EXISTS {table} (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    mission_id VARCHAR(100) NOT NULL,
    version BIGINT NOT NULL,
    snapshot_type VARCHAR(32) DEFAULT 'periodic',
    body JSONB NOT NULL,
    created_at TIMESTAMP DEFAULT NOW(),
    UNIQUE (mission_id, version)
);
CREATE INDEX IF NOT EXISTS idx_{table}_mission
    ON {table} (mission_id, version);
"""


def init_schema_sql() -> str:
    """Return the idempotent additive DDL for both default tables."""
    return f"{_timeline_ddl(_TIMELINE_TABLE)}\n{_snapshot_ddl(_SNAPSHOT_TABLE)}"


# ─────────────────────────────────────────────────────────────────────
# Frozen event vocabulary — business verbs, never infrastructure verbs.
# ─────────────────────────────────────────────────────────────────────
class MissionEventType(str, Enum):
    """Canonical, frozen set of business events for a mission timeline.

    Adding a new lifecycle event is a deliberate change to this enum only;
    nobody can append an ad-hoc string to a mission timeline.
    """

    CREATED = "MISSION_CREATED"
    STARTED = "MISSION_STARTED"
    REVIEWED = "MISSION_REVIEWED"
    PAUSED = "MISSION_PAUSED"
    RESUMED = "MISSION_RESUMED"
    REPLANNED = "MISSION_REPLANNED"
    REDIRECTED = "MISSION_REDIRECTED"
    APPROVED = "MISSION_APPROVED"
    REJECTED = "MISSION_REJECTED"
    EXECUTED = "MISSION_EXECUTED"
    CONFIDENCE_CHANGED = "MISSION_CONFIDENCE_CHANGED"
    STATUS_CHANGED = "MISSION_STATUS_CHANGED"
    PRIORITY_CHANGED = "MISSION_PRIORITY_CHANGED"
    EVIDENCE_ADDED = "MISSION_EVIDENCE_ADDED"
    RECOMMENDATION_UPDATED = "MISSION_RECOMMENDATION_UPDATED"
    COMPLETED = "MISSION_COMPLETED"
    ARCHIVED = "MISSION_ARCHIVED"


@dataclass(frozen=True)
class TimelineEvent:
    """Immutable, append-only timeline record (generic across entity types)."""

    entity_type: str
    entity_id: str
    version: int
    event_type: str
    actor: str | None
    source: str | None
    payload: Mapping[str, Any] | None
    causation_id: str | None
    correlation_id: str | None
    created_at: datetime | None = None


# ─────────────────────────────────────────────────────────────────────
# Timeline — generic append-only store with per-entity immutable versions
# ─────────────────────────────────────────────────────────────────────
class Timeline:
    """Append-only, entity-scoped, versioned event store.

    Reusable for any business subject (mission, workspace, decision, evidence,
    knowledge, AI-employee…). Each append atomically claims the next per-entity
    version via ``MAX(version)+1``; the unique constraint guarantees a total
    order even if two writers race a single entity.
    """

    def __init__(self, pool: asyncpg.Pool, table: str = _TIMELINE_TABLE) -> None:
        self._pool = pool
        self._table = table

    async def init_schema(self) -> None:
        """Idempotently create the timeline (and snapshot) tables."""
        ddl = init_schema_sql()
        if self._table != _TIMELINE_TABLE:
            ddl = f"{_timeline_ddl(self._table)}\n{_snapshot_ddl(_SNAPSHOT_TABLE)}"
        async with self._pool.acquire() as conn:
            await conn.execute(ddl)

    async def append(
        self,
        entity_type: str,
        entity_id: str,
        *,
        event_type: str,
        actor: str | None = None,
        source: str | None = None,
        payload: Mapping[str, Any] | None = None,
        causation_id: str | None = None,
        correlation_id: str | None = None,
    ) -> int:
        """Append one event; returns its immutable per-entity ``version``."""
        sql = f"""
        WITH nxt AS (
            SELECT COALESCE(MAX(version), 0) + 1 AS next_version
            FROM {self._table}
            WHERE entity_type = $1 AND entity_id = $2
        )
        INSERT INTO {self._table} (
            entity_type, entity_id, version, event_type,
            actor, source, payload, causation_id, correlation_id
        )
        SELECT $1, $2, nxt.next_version, $3, $4, $5, $6, $7, $8
        FROM nxt
        RETURNING version
        """
        body = json.dumps(dict(payload)) if payload is not None else None
        async with self._pool.acquire() as conn:
            version = await conn.fetchval(
                sql,
                entity_type,
                entity_id,
                event_type,
                actor,
                source,
                body,
                causation_id,
                correlation_id,
            )
        return int(version)

    async def history(self, entity_type: str, entity_id: str) -> Sequence[TimelineEvent]:
        """Return every event for an entity, in append order (oldest first)."""
        rows = await self._query(
            f"""
            SELECT * FROM {self._table}
            WHERE entity_type = $1 AND entity_id = $2
            ORDER BY version ASC
            """,
            entity_type,
            entity_id,
        )
        return self._to_events(rows)

    async def since(self, entity_type: str, entity_id: str, version: int) -> Sequence[TimelineEvent]:
        """Return events strictly after ``version`` (for forward replay)."""
        rows = await self._query(
            f"""
            SELECT * FROM {self._table}
            WHERE entity_type = $1 AND entity_id = $2 AND version > $3
            ORDER BY version ASC
            """,
            entity_type,
            entity_id,
            version,
        )
        return self._to_events(rows)

    async def _query(self, sql: str, *args) -> Any:
        async with self._pool.acquire() as conn:
            return await conn.fetch(sql, *args)

    @staticmethod
    def _to_event(row: asyncpg.Record) -> TimelineEvent:
        payload = row["payload"]
        if isinstance(payload, str):
            try:
                payload = json.loads(payload)
            except (ValueError, TypeError):
                payload = None
        return TimelineEvent(
            entity_type=row["entity_type"],
            entity_id=row["entity_id"],
            version=row["version"],
            event_type=row["event_type"],
            actor=row["actor"],
            source=row["source"],
            payload=payload if isinstance(payload, Mapping) else None,
            causation_id=str(row["causation_id"]) if row["causation_id"] else None,
            correlation_id=str(row["correlation_id"]) if row["correlation_id"] else None,
            created_at=row["created_at"],
        )

    @classmethod
    def _to_events(cls, rows: Iterable[asyncpg.Record]) -> list[TimelineEvent]:
        return [cls._to_event(r) for r in rows]


# ─────────────────────────────────────────────────────────────────────
# MissionTimeline — a mission-scoped facade over the frozen Timeline.
# ─────────────────────────────────────────────────────────────────────
MISSION_ENTITY = "mission"


class MissionTimeline:
    """Mission-scoped, type-safe facade around the generic ``Timeline``.

    Every mission gets one timeline; ``event_type`` is restricted to the frozen
    ``MissionEventType`` set. An unlisted event type is a real bug, so it is
    raised before touching the database rather than silently written.
    """

    def __init__(self, pool: asyncpg.Pool, table: str = _TIMELINE_TABLE) -> None:
        self._log = Timeline(pool, table=table)

    async def init_schema(self) -> None:
        await self._log.init_schema()

    async def record(
        self,
        mission_id: str,
        event_type: MissionEventType,
        *,
        actor: str | None = None,
        source: str | None = None,
        payload: Mapping[str, Any] | None = None,
        causation_id: str | None = None,
        correlation_id: str | None = None,
    ) -> int:
        """Append a frozen business event; returns its mission-local version.

        ``event_type`` must be a member of the frozen :class:`MissionEventType`
        enum; any other value is a programming error and raises ``ValueError``
        before touching the database.
        """
        if isinstance(event_type, str):
            try:
                event_type = MissionEventType(event_type)
            except ValueError:
                raise ValueError(
                    f"Unknown mission event type: {event_type!r}. "
                    f"Add it to MissionEventType or use a frozen member."
                ) from None
        elif not isinstance(event_type, MissionEventType):
            raise TypeError(
                f"event_type must be a MissionEventType, got {type(event_type).__name__}"
            )

        return await self._log.append(
            MISSION_ENTITY,
            mission_id,
            event_type=event_type.value,
            actor=actor,
            source=source,
            payload=payload,
            causation_id=causation_id,
            correlation_id=correlation_id,
        )

    async def history(self, mission_id: str) -> Sequence[TimelineEvent]:
        """The mission's full timeline in append order (oldest first)."""
        return await self._log.history(MISSION_ENTITY, mission_id)

    async def since(self, mission_id: str, version: int) -> Sequence[TimelineEvent]:
        """Events for the mission produced after ``version`` (forward replay)."""
        return await self._log.since(MISSION_ENTITY, mission_id, version)


# ─────────────────────────────────────────────────────────────────────
# MissionSnapshotStore — point-in-time captures for instant restore + diff
# ─────────────────────────────────────────────────────────────────────
class MissionSnapshotStore:
    """Capture/restore/diff of composed mission state.

    Snapshots let a restart read *current* state from one row instead of
    replaying the entire timeline, and make Mission Diff a pure comparison of
    two serialized bodies (no event replay).
    """

    def __init__(self, pool: asyncpg.Pool, table: str = _SNAPSHOT_TABLE) -> None:
        self._pool = pool
        self._table = table

    async def init_schema(self) -> None:
        async with self._pool.acquire() as conn:
            await conn.execute(_snapshot_ddl(self._table))

    async def capture(
        self,
        mission_id: str,
        body: Mapping[str, Any],
        *,
        snapshot_type: str = "periodic",
    ) -> int:
        """Persist a snapshot atomically; returns its per-mission version."""
        sql = f"""
WITH nxt AS (
    SELECT COALESCE(MAX(version), 0) + 1 AS next_version
    FROM {self._table}
    WHERE mission_id = $1
)
INSERT INTO {self._table} (mission_id, version, snapshot_type, body)
SELECT $1, nxt.next_version, $2, $3 FROM nxt
RETURNING version
"""
        async with self._pool.acquire() as conn:
            version = await conn.fetchval(
                sql, mission_id, snapshot_type, json.dumps(dict(body))
            )
        return int(version)

    async def latest(self, mission_id: str) -> Mapping[str, Any] | None:
        """Return the most recent snapshot body (or ``None``)."""
        row = await self._fetch_one(
            f"""
            SELECT body, version FROM {self._table}
            WHERE mission_id = $1
            ORDER BY version DESC LIMIT 1
            """,
            mission_id,
        )
        return self._decode_body(row[0]["body"]) if row else None

    async def at(self, mission_id: str, version: int) -> Mapping[str, Any] | None:
        """Return the snapshot body at an exact version (or ``None``)."""
        row = await self._fetch_one(
            f"""
            SELECT body FROM {self._table} WHERE mission_id = $1 AND version = $2
            """,
            mission_id,
            version,
        )
        return self._decode_body(row[0]["body"]) if row else None

    async def versions(self, mission_id: str) -> list[int]:
        """All snapshot versions for a mission, ascending (for address-diff UI)."""
        async with self._pool.acquire() as conn:
            rows = await conn.fetch(
                f"SELECT version FROM {self._table} "
                "WHERE mission_id = $1 ORDER BY version ASC",
                mission_id,
            )
        return [int(r["version"]) for r in rows]

    async def diff(self, mission_id: str, newer: int, older: int) -> Mapping[str, Any] | None:
        """Compare two snapshot versions → 'yesterday vs today' diff.

        Returns a non-empty dict when the bodies differ, else ``None``. This is
        the primitive that powers Mission Diff downstream.
        """
        row = await self._fetch_one(
            """
            SELECT version, body FROM %s
            WHERE mission_id = $1 AND version IN ($2, $3)
            """ % self._table,
            mission_id,
            newer,
            older,
        )
        if not row:
            return None
        bodies = {int(r["version"]): self._decode_body(r["body"]) for r in row}
        if newer not in bodies or older not in bodies:
            return None

        before, after = dict(bodies[older]), dict(bodies[newer])
        changed = {
            key: (before.get(key), after.get(key))
            for key in sorted(after.keys() | before.keys())
            if before.get(key) != after.get(key)
        }
        return {
            "from_version": older,
            "to_version": newer,
            "changed": changed,
            "confidence_delta": _delta(before.get("confidence"), after.get("confidence")),
        }

    async def _fetch_one(self, sql: str, *args) -> Sequence[asyncpg.Record]:
        async with self._pool.acquire() as conn:
            return await conn.fetch(sql, *args)

    @staticmethod
    def _decode_body(raw: Any) -> dict[str, Any]:
        """Normalise a JSONB body (str from asyncpg) into a dict."""
        if isinstance(raw, Mapping):
            return dict(raw)
        if isinstance(raw, str):
            try:
                return json.loads(raw)
            except (ValueError, TypeError):
                return {}
        if raw is None:
            return {}
        return dict(raw)


def _delta(before: Any, after: Any) -> float | None:
    """Signed difference of two numeric values (or ``None`` if not numeric)."""
    try:
        return float(after) - float(before)
    except (TypeError, ValueError):
        return None
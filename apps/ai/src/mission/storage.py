"""MissionState persistence bridge — PostgreSQL backend.

Functional, reusable persistence layer for long-running business missions.
Centralises the ``mission_state`` DDL so the Python AI worker and the Go core
stay schema-consistent (see ``apps/core/internal/db/schema/command_center.sql``).

Design notes:
    * Async only — the mission pipeline is Temporal/async by nature.
    * Tiny surface: create, get, save (upsert full row), rollup (KPI writeback).
    * Connection is owned by the caller and injected via ``__init__`` so tests
      can pass a pool/tx and production can pass ``MissionRuntime``-managed DB.
    * DSN resolved from ``ITERATESWARM_DATABASE_URL`` (fallback local default),
      matching the ``EngagementStateStore`` convention.

Usage::

    store = MissionStateStore(pool=pool)
    await store.init_schema()
    await store.save(MissionMetrics(...))          # upsert full row
    row = await store.get_epoch(mission.tenant_id) # latest snapshot
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from typing import Any, Mapping

import asyncpg

logger = logging.getLogger(__name__)

_DEFAULT_TABLE = "mission_state"

# Schema mirrors Go DDL (apps/core/internal/db/schema/command_center.sql) so the
# Python AI worker and the Go core write/read the same columns and semantics.
# Parametrised by configured table name so callers can isolate test tables.
def _schema_for(table: str) -> str:
    return f"""
CREATE TABLE IF NOT EXISTS {table} (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id VARCHAR(100) NOT NULL,
    mrr DECIMAL(12,2),
    burn_rate DECIMAL(12,2),
    runway_days INTEGER,
    burn_alert BOOLEAN DEFAULT FALSE,
    burn_severity VARCHAR(20),
    mrr_trend VARCHAR(10),
    churn_rate DECIMAL(5,2),
    error_spike BOOLEAN,
    active_alerts TEXT,
    founder_focus TEXT,
    trust_score INTEGER,
    burn_multiple DECIMAL(5,2),
    effective_runway_days INTEGER,
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_{table}_tenant ON {table}(tenant_id);
"""


@dataclass(frozen=True)
class MissionMetrics:
    """Immutable, functional snapshot of mission operating metrics.

    Field names/semantics mirror the ``mission_state`` columns so the store can
    persist without a separate mapping table.
    """
    tenant_id: str = "default"
    mrr: float | None = None
    burn_rate: float | None = None
    runway_days: int | None = None
    active_alerts: str | None = None
    founder_focus: str | None = None
    trust_score: int | None = None
    effective_runway_days: int | None = None
    timestamp: datetime | None = None

    # Optional computed/derived fields persisted for completeness.
    burn_alert: bool = False
    burn_severity: str | None = None
    mrr_trend: str | None = None
    churn_rate: float | None = None
    error_spike: bool | None = None
    burn_multiple: float | None = None

    def as_row(self) -> dict[str, Any]:
        """Deduplicate the dataclass into the column-space used by SQL."""
        row: dict[str, Any] = dict(asdict(self))
        ts = row.pop("timestamp", None)
        if ts:
            row["updated_at"] = ts
            row.setdefault("created_at", ts)
        row = {k: v for k, v in row.items() if v is not None}
        if row.get("updated_at") is None and row.get("created_at") is None:
            row["updated_at"] = datetime.now(timezone.utc).replace(tzinfo=None)
        return row


class MissionStateStore:
    """Async PostgreSQL repository for mission state snapshots.

    The store intentionally takes an ``asyncpg.Pool`` (or a connection alias) so
    it can be reused across tests, workers, and the Go-mirrored schema without
    owning connection lifecycle.
    """

    def __init__(self, pool: asyncpg.Pool, table_name: str = _DEFAULT_TABLE) -> None:
        self._pool = pool
        self._table = table_name

    async def init_schema(self) -> None:
        """Idempotently create the configured table and its tenant index."""
        async with self._pool.acquire() as conn:
            await conn.execute(_schema_for(self._table))

    async def save(self, metrics: MissionMetrics, mission_id: str | None = None) -> str:
        """Upsert a mission snapshot; returns the mission (row) id.

        Inserts a row when ``mission_id`` is absent, otherwise updates it. Uses a
        single ``ON CONFLICT`` so concurrent save/rollup calls cannot tear rows.
        """
        row = metrics.as_row()
        row["tenant_id"] = row.get("tenant_id") or metrics.tenant_id
        if mission_id:
            row["id"] = mission_id

        columns = list(row.keys())
        params = [row[c] for c in columns]
        placeholders = ", ".join(f"${i}" for i in range(1, len(columns) + 1))
        updates = ", ".join(
            f"{column} = EXCLUDED.{column}" for column in columns if column != "id"
        )

        sql = (
            f"INSERT INTO {self._table} ({', '.join(columns)}) "
            f"VALUES ({placeholders}) "
            f"ON CONFLICT (id) DO UPDATE SET {updates} "
            f"RETURNING id"
        )

        async with self._pool.acquire() as conn:
            inserted: asyncpg.Record = await conn.fetchrow(sql, *params)
        return str(inserted["id"])

    async def get_epoch(self, tenant_id: str) -> Mapping[str, Any] | None:
        """Return the most recent row for a tenant (or None)."""
        async with self._pool.acquire() as conn:
            row = await conn.fetchrow(
                f"""
                SELECT * FROM {self._table}
                WHERE tenant_id = $1
                ORDER BY updated_at DESC, created_at DESC
                LIMIT 1
                """,
                tenant_id,
            )
        if not row:
            return None
        record = dict(row)
        if record.get("id") is not None:
            record["id"] = str(record["id"])
        return record

    async def delete_tenant(self, tenant_id: str) -> None:
        """Remove all rows for a tenant (used by tests to stay idempotent)."""
        async with self._pool.acquire() as conn:
            await conn.execute(
                f"DELETE FROM {self._table} WHERE tenant_id = $1", tenant_id
            )
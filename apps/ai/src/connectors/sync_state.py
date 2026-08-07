"""V6 Connector Sync State — persistent store for connector checkpointing.

Tracks pagination cursors, ETags, retry counts, and backoff timestamps
so connectors can resume where they left off after a crash or restart.

Usage::

    store = SyncStateStore(db_pool)

    state = await store.get("notion", "tenant-abc")
    if state is None:
        state = ConnectorSyncState(connector="notion", tenant_id="tenant-abc")

    # After a successful fetch
    await store.mark_success("notion", "tenant-abc", cursor="next_page_1", records_count=42)

    # After a failure
    await store.mark_failure("notion", "tenant-abc", error_message="Rate limited")

    # Find stale connectors needing resync
    stale = await store.list_stale(since=datetime.now(timezone.utc) - timedelta(hours=1))
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any

from pydantic import BaseModel, Field

if TYPE_CHECKING:
    import asyncpg

logger = logging.getLogger(__name__)

# ── Sync State Model ──────────────────────────────────────────────────────


class ConnectorSyncState(BaseModel):
    """Persistent sync state for a single connector + tenant pair.

    Stored in the ``connector_sync_state`` table.  The ``cursor`` and
    ``etag`` fields let connectors resume incremental fetches after a
    restart.  ``backoff_until`` gates retries when the upstream is
    rate-limiting or unavailable.
    """

    connector: str  # e.g. "notion", "slack", "jira", "salesforce"
    tenant_id: str
    cursor: str | None = None  # pagination / checkpoint cursor
    etag: str | None = None  # HTTP ETag for conditional requests
    last_sync: datetime | None = None
    last_success: datetime | None = None
    last_failure: datetime | None = None
    retry_count: int = 0
    backoff_until: datetime | None = None
    total_records_synced: int = 0
    error_message: str | None = None


# ── Sync State Store ──────────────────────────────────────────────────────


class SyncStateStore:
    """Async PostgreSQL store for connector sync state.

    Parameters
    ----------
    db_pool:
        An ``asyncpg.Pool`` (or compatible duck-typed pool) used for
        all database operations.
    """

    _TABLE_NAME = "connector_sync_state"

    def __init__(self, db_pool: asyncpg.Pool[Any]) -> None:
        self._pool = db_pool

    # ── DDL ───────────────────────────────────────────────────────────────

    @classmethod
    def init_table_queries(cls) -> list[str]:
        """Return DDL statements to create the sync state table.

        Call this at startup to ensure the table exists.  Returns a
        list so callers can execute them in a transaction if desired.
        """
        return [
            f"""
            CREATE TABLE IF NOT EXISTS {cls._TABLE_NAME} (
                connector        TEXT NOT NULL,
                tenant_id        TEXT NOT NULL,
                cursor           TEXT,
                etag             TEXT,
                last_sync        TIMESTAMPTZ,
                last_success     TIMESTAMPTZ,
                last_failure     TIMESTAMPTZ,
                retry_count      INTEGER NOT NULL DEFAULT 0,
                backoff_until    TIMESTAMPTZ,
                total_records_synced INTEGER NOT NULL DEFAULT 0,
                error_message    TEXT,
                PRIMARY KEY (connector, tenant_id)
            );
            """,
        ]

    # ── CRUD ──────────────────────────────────────────────────────────────

    async def get(self, connector: str, tenant_id: str) -> ConnectorSyncState | None:
        """Load sync state for *connector* + *tenant_id*.

        Returns ``None`` if no state exists yet for this pair.
        """
        query = f"""
            SELECT connector, tenant_id, cursor, etag, last_sync, last_success,
                   last_failure, retry_count, backoff_until, total_records_synced,
                   error_message
            FROM {self._TABLE_NAME}
            WHERE connector = $1 AND tenant_id = $2
        """
        async with self._pool.acquire() as conn:
            row = await conn.fetchrow(query, connector, tenant_id)

        if row is None:
            return None

        return self._row_to_state(dict(row))

    async def upsert(self, state: ConnectorSyncState) -> None:
        """Insert or replace the sync state for a connector + tenant pair."""
        query = f"""
            INSERT INTO {self._TABLE_NAME}
                (connector, tenant_id, cursor, etag, last_sync, last_success,
                 last_failure, retry_count, backoff_until, total_records_synced,
                 error_message)
            VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11)
            ON CONFLICT (connector, tenant_id) DO UPDATE SET
                cursor             = EXCLUDED.cursor,
                etag               = EXCLUDED.etag,
                last_sync          = EXCLUDED.last_sync,
                last_success       = EXCLUDED.last_success,
                last_failure       = EXCLUDED.last_failure,
                retry_count        = EXCLUDED.retry_count,
                backoff_until      = EXCLUDED.backoff_until,
                total_records_synced = EXCLUDED.total_records_synced,
                error_message      = EXCLUDED.error_message
        """
        async with self._pool.acquire() as conn:
            await conn.execute(
                query,
                state.connector,
                state.tenant_id,
                state.cursor,
                state.etag,
                state.last_sync,
                state.last_success,
                state.last_failure,
                state.retry_count,
                state.backoff_until,
                state.total_records_synced,
                state.error_message,
            )

    async def mark_success(
        self,
        connector: str,
        tenant_id: str,
        cursor: str | None = None,
        etag: str | None = None,
        records_count: int = 0,
    ) -> None:
        """Record a successful sync.

        Updates ``last_sync``, ``last_success``, resets ``retry_count``
        and ``backoff_until``, and increments ``total_records_synced``.
        """
        now = datetime.now(timezone.utc)
        query = f"""
            UPDATE {self._TABLE_NAME}
            SET cursor = COALESCE($3, cursor),
                etag = COALESCE($4, etag),
                last_sync = $5,
                last_success = $5,
                last_failure = last_failure,
                retry_count = 0,
                backoff_until = NULL,
                total_records_synced = total_records_synced + $6,
                error_message = NULL
            WHERE connector = $1 AND tenant_id = $2
        """
        async with self._pool.acquire() as conn:
            await conn.execute(query, connector, tenant_id, cursor, etag, now, records_count)

    async def mark_failure(
        self,
        connector: str,
        tenant_id: str,
        error_message: str,
        backoff_seconds: int = 30,
    ) -> None:
        """Record a sync failure.

        Increments ``retry_count`` and sets ``backoff_until`` to
        ``now + backoff_seconds`` so the scheduler can skip this
        connector until the backoff window expires.
        """
        now = datetime.now(timezone.utc)
        backoff_until = now.replace(microsecond=0)  # floor microseconds for clean comparison
        # Manually compute: PostgreSQL TIMESTAMPTZ addition
        query = f"""
            UPDATE {self._TABLE_NAME}
            SET last_failure = $3,
                error_message = $4,
                retry_count = retry_count + 1,
                backoff_until = $3 + ($5 || ' seconds')::INTERVAL,
                last_sync = $3
            WHERE connector = $1 AND tenant_id = $2
        """
        async with self._pool.acquire() as conn:
            await conn.execute(
                query,
                connector,
                tenant_id,
                now,
                error_message,
                str(backoff_seconds),
            )

    async def list_stale(self, since: datetime) -> list[ConnectorSyncState]:
        """Return all sync states where ``last_sync`` is older than *since*.

        This is used by the scheduler to identify connectors that need
        re-synchronisation.  Connectors with an active ``backoff_until``
        that is still in the future are excluded.
        """
        now = datetime.now(timezone.utc)
        query = f"""
            SELECT connector, tenant_id, cursor, etag, last_sync, last_success,
                   last_failure, retry_count, backoff_until, total_records_synced,
                   error_message
            FROM {self._TABLE_NAME}
            WHERE (last_sync IS NULL OR last_sync < $1)
              AND (backoff_until IS NULL OR backoff_until <= $2)
            ORDER BY last_sync ASC NULLS FIRST
        """
        async with self._pool.acquire() as conn:
            rows = await conn.fetch(query, since, now)

        return [self._row_to_state(dict(r)) for r in rows]

    # ── Helpers ───────────────────────────────────────────────────────────

    @staticmethod
    def _row_to_state(row: dict[str, Any]) -> ConnectorSyncState:
        """Convert a database row dict to a ``ConnectorSyncState``."""
        return ConnectorSyncState(
            connector=row["connector"],
            tenant_id=row["tenant_id"],
            cursor=row.get("cursor"),
            etag=row.get("etag"),
            last_sync=row.get("last_sync"),
            last_success=row.get("last_success"),
            last_failure=row.get("last_failure"),
            retry_count=row.get("retry_count", 0),
            backoff_until=row.get("backoff_until"),
            total_records_synced=row.get("total_records_synced", 0),
            error_message=row.get("error_message"),
        )


__all__ = [
    "ConnectorSyncState",
    "SyncStateStore",
]

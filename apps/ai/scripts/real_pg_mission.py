#!/usr/bin/env python
"""Real-Postgres persistence probe for MissionRuntime.

Connects to the healthy `iterateswarm-postgres` container (started via docker
compose), creates the `mission_state` table if missing, then persists and reads
back a mission through MissionRuntime.persist_mission_state / update_mission_kpis.
"""
import asyncio
import os
import sys
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
sys.path.insert(0, str(Path.cwd() / "src"))

import asyncpg

from src.mission.runtime import MissionRuntime
from src.mission.runtime import Mission
from src.goal.models import GoalKPI

DB = dict(
    host=os.getenv("PGHOST", "localhost"),
    port=int(os.getenv("PGPORT", "5433")),
    user=os.getenv("PGUSER", "iterateswarm"),
    password=os.getenv("PGPASSWORD", "iterateswarm"),
    database=os.getenv("PGDATABASE", "iterateswarm"),
)

DDL_MISSION_STATE = """
CREATE TABLE IF NOT EXISTS mission_state (
    id UUID PRIMARY KEY,
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
"""


class AsyncPGWrapper:
    """Thin adapter exposing `async def execute(sql, *args)` for MissionRuntime."""

    def __init__(self, conn: asyncpg.Connection):
        self._conn = conn

    async def execute(self, query: str, *args):
        return await self._conn.execute(query, *args)


async def main() -> int:
    conn = await asyncpg.connect(**DB)
    try:
        await conn.execute(DDL_MISSION_STATE)
        print(f"[DB] connected to {DB['host']}:{DB['port']}/{DB['database']} ✓")
        print("[DB] ensured mission_state table ✓")
    except Exception as e:  # pragma: no cover
        print(f"[DB] setup error: {e}")
        await conn.close()
        return 1

    runtime = MissionRuntime()
    kpi = GoalKPI(
        id="kpi_rev_001",
        goal_id="mission_rev_real",
        name="MRR",
        target_value=50000.0,
        baseline_value=25000.0,
        current_value=35000.0,
        unit="USD",
        direction="increase",
    )
    goal = await runtime.create(
        tenant_id="real-docker-tenant",
        owner_id="e2e",
        title="Revenue Health (real PG)",
        kpis=[kpi],
    )
    mission = Mission.from_goal(goal)
    # mission_state.id is UUID; convert the mission id to a compatible key
    import uuid
    mid = str(uuid.uuid5(uuid.NAMESPACE_URL, mission.id))

    db = AsyncPGWrapper(conn)
    await runtime.persist_mission_state(Mission(id=mid, tenant_id="real-docker-tenant"), db=db)
    await runtime.update_mission_kpis(mid, {"MRR": 35000.0}, 0.7, db=db)

    row = await conn.fetchrow(
        "SELECT id, tenant_id, mrr, burn_rate, updated_at FROM mission_state WHERE id = $1", mid
    )
    print(f"[DB] persisted row: id={row['id']} tenant={row['tenant_id']} "
          f"mrr={row['mrr']} burn_rate={row['burn_rate']} updated_at={row['updated_at']}")
    reliable = row is not None and float(row["mrr"]) == 35000.0
    print("[DB] real Postgres write verified ✓" if reliable else "[DB] MISSING row ✗")
    return 0 if reliable else 1


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
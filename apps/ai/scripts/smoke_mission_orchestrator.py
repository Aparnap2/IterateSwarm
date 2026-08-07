"""Continuous Mission Control demo — a deterministic "Monday morning".

Proves the Mission Orchestrator (Milestone 1) with no Temporal / LLM /
connectors: a compressed clock drives real orchestrator behaviour.

    uv run python scripts/smoke_mission_orchestrator.py

It shows, start to finish, that missions keep operating across ~4 simulated
days with interruptions, replans, approvals, execution and proactive review.
"""
from __future__ import annotations

import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.goal.models import GoalKPI
from src.mission.coordinator import MissionCoordinator

T0 = datetime(2026, 8, 2, 20, 0, tzinfo=timezone.utc)
clock = {"t": T0}


def now() -> datetime:
    return clock["t"]


def step(hours: float) -> None:
    clock["t"] = clock["t"] + timedelta(hours=hours)


def kpi(name: str, current: float, target: float, direction: str = "increase") -> GoalKPI:
    return GoalKPI(
        id=f"kpi_{name}",
        goal_id="",
        name=name,
        target_value=target,
        baseline_value=0.0,
        current_value=current,
        unit="USD" if direction == "increase" else "pct",
        direction=direction,
    )


def render(a_coord: MissionCoordinator, mission_id: str) -> str:
    m = a_coord.mission_card(mission_id)
    return (
        f"    {m['name']:<26}{m['status']:<16}conf={m['confidence']:<7}"
        f"ev={m['evidence_count']:<3}prio={m['priority']:<8}worker={m['worker']}"
    )


def summarize(a_coord: MissionCoordinator, label: str) -> None:
    print(f"\n[{clock['t']:%m-%d %H:%M}] {label}")
    for om in a_coord.list_missions():
        print(render(a_coord, om.mission.id))


def main() -> int:
    print("OntarioMAX — Continuous Mission Orchestrator (deterministic clock)\n")

    c = MissionCoordinator(tenant_id="acme", now_fn=now)

    revops = c.create_mission(
        title="Revenue Health", owner_id="COO", kpis=[kpi("MRR", 50.0, 100.0)],
        employee_id="revops-analyst", subscriptions=["salesforce"],
    )
    c.create_mission(
        title="Customer Health", owner_id="CSO", kpis=[kpi("Churn", 30.0, 100.0, "decrease")],
        employee_id="orgint-analyst", subscriptions=["salesforce"],
    )
    c.create_mission(
        title="Product Delivery", owner_id="CTO", kpis=[kpi("Roadmap", 80.0, 100.0)],
        employee_id="productops-analyst", subscriptions=["jira"],
    )

    step(12)  # overnight → Monday morning (~12h later)
    c.run_due_reviews(now=now())
    summarize(c, "Good morning — three missions have been running all night")

    # ── 1. One Salesforce event fans out to Revenue + Customer, not Product ──
    step(0.5)
    c.ingest_event(
        {"id": "ev-sf-001", "structured_data": {"kpi_scores": {"MRR": 32}}},
        sources=["salesforce"],
    )
    summarize(c, "Salesforce event → Revenue + Customer Health re-evaluate; Product untouched")

    # ── 2. Investigation is high risk → needs the COO ─────────────────────
    c.signal(revops.mission.id, "reprioritize", priority="high")
    revops.investigate(needs_approval=True)
    summarize(c, "RevOps analysis → high-risk → AWAITING_APPROVAL (COO must look)")

    # ── 3. COO interrupts and redirects ───────────────────────────────────
    c.signal(revops.mission.id, "redirect", employee_id="revops-analyst", directive="Ignore SMB. Focus Enterprise.")
    revops.investigate(needs_approval=False)
    c.signal(revops.mission.id, "approve")
    summarize(c, "COO: 'Ignore SMB. Focus Enterprise.' → replan → approve → executing")

    # ── 4. Execution updates KPIs → monitoring ─────────────────────────────
    revops.execution_complete(success=True, kpi_updates={"MRR": 58}, outcome={"focus": "enterprise"})
    summarize(c, "RevOps executed (enterprise focus) → MONITORING")

    # ── 5. Later, fresh evidence shifts confidence → workspace refresh ──────
    step(3)
    c.ingest_event(
        {"id": "ev-sf-002", "structured_data": {"kpi_scores": {"MRR": 72}}},
        sources=["salesforce"],
    )
    summarize(c, "New Salesforce opportunity → confidence up → workspace refresh")

    # ── 6. Proactive Review wakes a silently-degraded mission ───────────────
    step(72)
    c.run_due_reviews(now=now())
    summarize(c, "72h later — nobody typed; periodic review pulled every mission awake")

    print(f"\nContinuous-operation check:")
    print(f"    Revenue Health: {revops.mission.id} epoch={revops.epoch} "
          f"interrupts={revops.interruption_count} events={len(revops.events)} "
          f"evidence={revops.evidence_count}")
    print(f"    survived {clock['t'] - T0} of simulated operation without sleeping.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
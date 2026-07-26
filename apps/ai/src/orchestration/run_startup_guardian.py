"""
Startup Guardian Orchestration — Startup Health Assessment Pipeline.

Assembles the unified MissionStateV2 from multiple data connectors and
computes cross-domain overall health. Sends Slack alerts on CRITICAL/ATTENTION.
"""
from __future__ import annotations

import asyncio
import logging
from typing import Any
from uuid import uuid4

from src.events import emit
from src.notifications.slack_alert_forwarder import SlackAlertForwarder
from src.guardian.assemblers import (
    assemble_execution_state,
    assemble_finance_state,
    assemble_revenue_state,
    assemble_support_state,
    assemble_team_state,
)
from src.integrations.erpnext import get_erpnext_snapshot
from src.integrations.hubspot import get_hubspot_snapshot
from src.integrations.quickbooks import get_quickbooks_snapshot
from src.services.dead_letter import send_to_dlq
from src.states.schemas import (
    ExecutionHealth,
    FinancialHealth,
    MissionStateV2,
    SupportHealth,
)

log = logging.getLogger(__name__)

_CONNECTORS: list[tuple[str, Any]] = [
    ("erpnext", get_erpnext_snapshot),
    ("hubspot", get_hubspot_snapshot),
    ("quickbooks", get_quickbooks_snapshot),
]

_HEALTH_PRIORITY: list[SupportHealth] = [
    SupportHealth.CRITICAL,
    SupportHealth.ATTENTION,
    SupportHealth.GOOD,
]


def _map_health(health: Any) -> SupportHealth:
    raw = health.value if hasattr(health, "value") else str(health)
    mapping = {
        "critical": SupportHealth.CRITICAL,
        "attention": SupportHealth.ATTENTION,
        "good": SupportHealth.GOOD,
        "on_track": SupportHealth.GOOD,
        "at_risk": SupportHealth.ATTENTION,
        "blocked": SupportHealth.CRITICAL,
        "healthy": SupportHealth.GOOD,
        "warning": SupportHealth.ATTENTION,
    }
    return mapping.get(raw, SupportHealth.GOOD)


async def run_startup_guardian(tenant_id: str) -> dict[str, Any]:
    run_id = str(uuid4())
    state = MissionStateV2(tenant_id=tenant_id, run_id=run_id)
    log.info("Starting Startup Guardian run_id=%s tenant=%s", run_id, tenant_id)

    connectors_ok: dict[str, bool] = {}
    snapshots: dict[str, dict[str, Any]] = {}

    async def _run_connector(name: str, func: Any) -> tuple[str, Any]:
        try:
            snap = await asyncio.to_thread(func, tenant_id)
            return name, snap, True
        except Exception as exc:
            log.error("Connector %s failed for tenant %s: %s", name, tenant_id, exc)
            return name, None, False

    results = await asyncio.gather(*(
        _run_connector(name, func) for name, func in _CONNECTORS
    ))

    for name, snap, ok in results:
        connectors_ok[name] = ok
        if ok and snap is not None:
            snapshots[name] = snap
            log.info("Connector %s succeeded for tenant %s", name, tenant_id)

    if "erpnext" in snapshots:
        raw = snapshots["erpnext"]
        state.support = assemble_support_state(raw)
        state.execution = assemble_execution_state(raw)
        state.team = assemble_team_state(raw)
        state.finance = assemble_finance_state(raw)

    if "hubspot" in snapshots:
        raw = snapshots["hubspot"]
        state.revenue = assemble_revenue_state(raw)

    if "quickbooks" in snapshots:
        raw = snapshots["quickbooks"]
        state.finance = assemble_finance_state(raw)

    domain_healths = [
        _map_health(state.support.health),
        _map_health(state.execution.health),
        _map_health(state.team.health),
        _map_health(state.finance.health),
    ]

    worst = SupportHealth.GOOD
    for h in domain_healths:
        if _HEALTH_PRIORITY.index(h) < _HEALTH_PRIORITY.index(worst):
            worst = h
    state.overall_health = worst

    state.connectors_ok = connectors_ok
    state.raw_snapshots = snapshots

    log.info("Startup Guardian complete run_id=%s tenant=%s ok=%s", run_id, tenant_id, all(connectors_ok.values()))

    # ── Alert delivery via SlackAlertForwarder (non-blocking) ──────
    try:
        forwarder = SlackAlertForwarder()
        alert_result = forwarder.forward_mission_alert(state)
        if alert_result.get("ok") and not alert_result.get("skipped"):
            await emit("startup_guardian.alert_delivered", tenant_id, {
                "run_id": run_id,
                "overall_health": state.overall_health.value,
                "connectors_ok": connectors_ok,
            })
    except Exception as exc:
        log.warning("Failed to send Startup Guardian alert: %s", exc)

    # Emit completion event
    await emit("startup_guardian.completed", tenant_id, {
        "run_id": run_id,
        "overall_health": state.overall_health.value,
        "connectors_ok": connectors_ok,
    })

    return state.model_dump()

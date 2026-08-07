"""
Finance Guardian Orchestration.

Reuses existing run_pulse_agent and run_guardian_watchlist logic.
"""
from __future__ import annotations

import logging
from typing import Any
from uuid import uuid4

from src.activities.run_pulse_agent import run_pulse_agent
from src.activities.run_guardian_watchlist import run_guardian_watchlist
from src.activities.send_slack_message import send_slack_message
from src.events import emit

log = logging.getLogger(__name__)


async def run_finance_guardian(tenant_id: str) -> dict[str, Any]:
    """
    Run finance guardian job.

    This orchestrates:
    1. Run PulseAgent to fetch financial data and compute metrics
    2. Run Guardian watchlist to detect patterns
    3. Send Slack alert if anomalies detected
    4. Write to memory
    5. Emit events for tracking

    Args:
        tenant_id: Tenant identifier

    Returns:
        dict with execution results
    """
    run_id = str(uuid4())
    log.info(f"Running finance guardian for {tenant_id}, run_id={run_id}")

    result = {
        "run_id": run_id,
        "tenant_id": tenant_id,
        "pulse_result": {},
        "guardian_result": {},
        "ok": True,
    }

    try:
        # Step 1: Run PulseAgent
        pulse_result = await run_pulse_agent(tenant_id)
        result["pulse_result"] = pulse_result

        if not pulse_result.get("ok"):
            error_msg = pulse_result.get("error", "Unknown error")
            log.error(f"PulseAgent failed: {error_msg}")

            try:
                await send_slack_message(
                    f"❌ Finance Guardian failed for {tenant_id}: {error_msg}",
                )
            except Exception as slack_err:
                log.error(f"Slack notification failed: {slack_err}")

            result["ok"] = False
            result["error"] = error_msg
            return result

        log.info(f"PulseAgent completed: {pulse_result.get('narrative', '')[:100]}")

    except Exception as e:
        log.error(f"PulseAgent activity failed: {e}")

        try:
            await send_slack_message(
                f"❌ Finance Guardian failed for {tenant_id}: {str(e)}",
            )
        except Exception as slack_err:
            log.error(f"Slack notification failed: {slack_err}")

        result["ok"] = False
        result["error"] = str(e)
        return result

    # Step 2: Run Guardian watchlist analysis
    # Pass metrics from pulse_result (computed metrics under pulse_result["metrics"])
    metrics_payload = pulse_result.get("metrics", pulse_result)
    try:
        guardian_result = await run_guardian_watchlist(
            tenant_id,
            metrics_payload,
        )
        result["guardian_result"] = guardian_result

        match_count = guardian_result.get("match_count", 0)
        log.info(f"Guardian watchlist: {match_count} patterns triggered")

    except Exception as e:
        log.warning(f"Guardian watchlist failed (non-blocking): {e}")
        result["guardian_result"] = {
            "ok": False,
            "error": str(e),
            "blindspots_triggered": [],
            "match_count": 0,
        }

    # Step 3: Send alert if needed
    if result["guardian_result"].get("match_count", 0) > 0:
        try:
            narrative = pulse_result.get("narrative", "Guardian patterns detected")
            slack_blocks = pulse_result.get("slack_blocks", [])

            await send_slack_message(
                narrative,
                blocks=slack_blocks if slack_blocks else None,
            )

            await emit("guardian.alert_delivered", tenant_id, {
                "run_id": run_id,
                "agent": "finance",
                "match_count": result["guardian_result"].get("match_count", 0),
            })

        except Exception as e:
            log.warning(f"Failed to send alert: {e}")

    # Step 4: Emit completion event
    await emit("guardian.completed", tenant_id, {
        "run_id": run_id,
        "agent": "finance",
        "pulse_ok": pulse_result.get("ok", False),
        "guardian_match_count": result["guardian_result"].get("match_count", 0),
    })

    return result
"""
BI Pulse Orchestration.

Reuses existing run_pulse_agent logic for daily BI metrics.
"""
from __future__ import annotations

import logging
from typing import Any
from uuid import uuid4

from src.activities.run_pulse_agent import run_pulse_agent
from src.activities.send_slack_message import send_slack_message
from src.events import emit

log = logging.getLogger(__name__)


async def run_bi_pulse(tenant_id: str) -> dict[str, Any]:
    """
    Run BI pulse job.

    This orchestrates:
    1. Run PulseAgent to compute metrics and narrative
    2. Send Slack notification with results

    Args:
        tenant_id: Tenant identifier

    Returns:
        dict with execution results
    """
    run_id = str(uuid4())
    log.info(f"Running BI pulse for {tenant_id}, run_id={run_id}")

    result = {
        "run_id": run_id,
        "tenant_id": tenant_id,
        "pulse_result": {},
        "ok": True,
    }

    try:
        pulse_result = await run_pulse_agent(tenant_id)
        result["pulse_result"] = pulse_result

        if not pulse_result.get("ok"):
            error_msg = pulse_result.get("error", "Unknown error")
            log.error(f"PulseAgent failed: {error_msg}")

            try:
                await send_slack_message(
                    f"❌ BI Pulse failed for {tenant_id}: {error_msg}",
                )
            except Exception as slack_err:
                log.error(f"Slack notification failed: {slack_err}")

            result["ok"] = False
            result["error"] = error_msg
            return result

        log.info(f"BI Pulse completed: {pulse_result.get('narrative', '')[:100]}")

    except Exception as e:
        log.error(f"BI Pulse activity failed: {e}")

        try:
            await send_slack_message(
                f"❌ BI Pulse failed for {tenant_id}: {str(e)}",
            )
        except Exception as slack_err:
            log.error(f"Slack notification failed: {slack_err}")

        result["ok"] = False
        result["error"] = str(e)
        return result

    # Send Slack notification
    try:
        narrative = pulse_result.get("narrative", "No narrative generated")
        slack_blocks = pulse_result.get("slack_blocks", [])

        await send_slack_message(
            narrative,
            blocks=slack_blocks if slack_blocks else None,
        )

    except Exception as e:
        log.warning(f"Slack notification failed: {e}")

    # Emit completion event
    await emit("bi_pulse.completed", tenant_id, {
        "run_id": run_id,
        "agent": "bi_pulse",
    })

    return result
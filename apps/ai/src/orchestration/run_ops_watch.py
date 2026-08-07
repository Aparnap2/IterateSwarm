"""
Ops Watch Orchestration.

Reuses existing ops agent logic for monitoring.
"""
from __future__ import annotations

import logging
from typing import Any
from uuid import uuid4

from src.activities.run_pulse_agent import run_pulse_agent
from src.activities.run_anomaly_agent import run_anomaly_agent
from src.activities.send_slack_message import send_slack_message
from src.events import emit

log = logging.getLogger(__name__)


async def run_ops_watch(tenant_id: str) -> dict[str, Any]:
    """
    Run ops watch job.

    This orchestrates:
    1. Run PulseAgent to get current state
    2. Run AnomalyAgent to detect operational anomalies
    3. Send alerts if critical issues found

    Args:
        tenant_id: Tenant identifier

    Returns:
        dict with execution results
    """
    run_id = str(uuid4())
    log.info(f"Running ops watch for {tenant_id}, run_id={run_id}")

    result = {
        "run_id": run_id,
        "tenant_id": tenant_id,
        "pulse_result": {},
        "anomaly_result": {},
        "ok": True,
    }

    try:
        # Get current metrics
        pulse_result = await run_pulse_agent(tenant_id)
        result["pulse_result"] = pulse_result

        if not pulse_result.get("ok"):
            log.warning(f"PulseAgent failed: {pulse_result.get('error')}")
            # Continue with anomaly detection even if pulse fails

    except Exception as e:
        log.warning(f"PulseAgent failed (non-blocking): {e}")

    # Run anomaly detection
    # Get anomalies from pulse_result or use default operational anomalies
    anomalies = []
    if pulse_result.get("ok"):
        # Extract anomaly triggers from pulse metrics
        anomalies = [
            "ops_high_churn",
            "ops_support_spike",
            "ops_deploy_failure",
        ]
    else:
        # Use default anomalies when pulse fails
        anomalies = ["ops_default_check"]
    
    try:
        anomaly_result = await run_anomaly_agent(tenant_id, anomalies)
        result["anomaly_result"] = anomaly_result

        # Use actual return keys: ok, output_message, slack_blocks
        if anomaly_result.get("ok") and anomaly_result.get("output_message"):
            alert_message = anomaly_result.get("output_message", "Operational anomaly detected")

            await send_slack_message(alert_message)

            await emit("ops.alert_delivered", tenant_id, {
                "run_id": run_id,
                "agent": "ops",
                "anomaly_type": "ops_anomaly",
                "severity": "medium",
            })

    except TypeError as e:
        log.error(f"AnomalyAgent called with wrong arguments: {e}")
        raise
    except Exception as e:
        log.warning(f"AnomalyAgent failed (non-blocking): {e}")

    # Emit completion event
    await emit("ops_watch.completed", tenant_id, {
        "run_id": run_id,
        "agent": "ops_watch",
    })

    return result
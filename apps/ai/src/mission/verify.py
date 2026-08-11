"""Verify — read-back verification of governed writes.

After a write op executes, the runtime reads the record back through the op's
read counterpart and compares it against the expected state. A mismatch yields
``verified=False`` plus rollback metadata; the runtime then blocks downstream
steps. Every verification produces a frozen :class:`ActionResult` for audit.
"""
from __future__ import annotations

import logging
import uuid
from typing import Any

from src.entities.models import ActionResult, OntologyBaseModel

logger = logging.getLogger(__name__)

# Write op → read-back counterpart.
READ_COUNTERPART: dict[str, str] = {
    "salesforce.update": "salesforce.read",
    "jira.update": "jira.read",
    "notion.update": "notion.read",
    "slack.send": "slack.search",
}


class VerifyOutcome(OntologyBaseModel):
    """The outcome of a read-back verification."""

    verified: bool = False
    verified_by: str = "EmployeeRuntime.verify"
    rollback_metadata: dict[str, Any] = {}
    mismatch: str | None = None


def _read_params_for(op_name: str, params: dict[str, Any]) -> dict[str, Any]:
    """Derive the read-back params from the write params."""
    if op_name == "salesforce.update":
        return {"object_type": "opportunity", "record_id": params.get("record_id")}
    if op_name == "jira.update":
        return {"jql": f"key = {params.get('issue_id', '')}"}
    if op_name == "notion.update":
        return {"page_id": params.get("page_id")}
    if op_name == "slack.send":
        return {"channel": params.get("channel", ""), "query": str(params.get("text", ""))[:80]}
    return dict(params)


def _first_record(data: Any) -> dict[str, Any] | None:
    """Extract the first record from an op result payload."""
    if isinstance(data, dict):
        return data
    if isinstance(data, list) and data:
        return data[0] if isinstance(data[0], dict) else None
    return None


def _find_mismatch(expected: dict[str, Any], record: dict[str, Any] | None) -> str | None:
    """Return the first expected key that does not match the record, or None."""
    if record is None:
        return "record"
    for key, value in (expected or {}).items():
        if record.get(key) != value:
            return str(key)
    return None


async def verify_write(
    op_name: str,
    params: dict[str, Any],
    expected: dict[str, Any],
    tenant_id: str,
    *,
    capabilities: Any,
    role_caps: list[str] | None = None,
) -> VerifyOutcome:
    """Verify a write by reading it back through the op's read counterpart."""
    read_op = READ_COUNTERPART.get(op_name)
    if read_op is None:
        return VerifyOutcome(
            verified=False,
            rollback_metadata={
                "op": op_name,
                "reason": f"no read counterpart for {op_name}",
            },
        )
    try:
        read_back = capabilities.execute(
            read_op, _read_params_for(op_name, params), tenant_id, role_caps=role_caps
        )
        payload = read_back.get("data", read_back) if isinstance(read_back, dict) else read_back
        record = _first_record(payload)
        mismatch = _find_mismatch(expected, record)
        if mismatch is None:
            return VerifyOutcome(verified=True)
        return VerifyOutcome(
            verified=False,
            mismatch=mismatch,
            rollback_metadata={
                "capability": op_name,
                "read_op": read_op,
                "record_id": params.get("record_id") or params.get("issue_id")
                or params.get("page_id") or params.get("channel"),
                "expected": expected,
                "read_back": record,
                "reason": f"read-back mismatch on {mismatch}",
            },
        )
    except Exception as exc:  # noqa: BLE001 — verification must not raise
        logger.warning("verify_write failed for %s: %s", op_name, exc)
        return VerifyOutcome(
            verified=False,
            rollback_metadata={"capability": op_name, "error": str(exc)},
        )


def build_action_result(action_id: str, outcome: VerifyOutcome) -> ActionResult:
    """Project a VerifyOutcome onto the frozen ActionResult entity."""
    return ActionResult(
        id=f"ar-{uuid.uuid4().hex[:12]}",
        action_id=action_id,
        result_summary=(
            "verified" if outcome.verified else f"rejected: {outcome.mismatch or 'error'}"
        ),
        output_snapshot={"verified": outcome.verified, "mismatch": outcome.mismatch},
        rollback_metadata=outcome.rollback_metadata,
        verified=outcome.verified,
        verified_by=outcome.verified_by,
    )
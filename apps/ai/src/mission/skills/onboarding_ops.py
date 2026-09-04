"""Blocker-investigation skill — investigate one onboarding blocker (slice).

ONE skill only: ``investigate_onboarding_blocker``. The LLM is used
strictly for ambiguous evidence interpretation / root-cause reasoning.
Every authority decision (evidence gating, parameter policy,
authorization, idempotency, approval, execution, verification, audit)
is deterministic and lives in the Control Plane.
"""
from __future__ import annotations

import contextvars
import json
from contextlib import contextmanager
from dataclasses import dataclass, field
from typing import Any, Iterator

from src.config import llm as llm_module
from src.control_plane.contracts import ActionIntent
from src.control_plane.ingress import submit_intent
from src.mission.skill_contracts import SkillContext, SkillDefinition, SkillInput, SkillOutput

BLOCKER_INVESTIGATION_SKILL_NAME = "investigate_onboarding_blocker"

# Deterministic blocker-investigation action surface: the ONLY operations this skill may propose.
BLOCKER_INVESTIGATION_ALLOWED_OPS = {"jira.update", "jira.create", "slack.send"}

_JIRA_STATUS_ALLOWED = {"To Do", "In Progress", "Blocked", "Done"}

_VALID_TIERS = {"LOW", "MEDIUM", "HIGH", "CRITICAL"}

# Tiers that require grounded evidence before any intent may be proposed.
_EVIDENCE_TIERS = {"MEDIUM", "HIGH", "CRITICAL"}

_SYSTEM = (
    "You investigate B2B onboarding blockers. Given evidence texts, reply "
    "with JSON only: {root_cause, action: {capability, operation, target, "
    "parameters}, confidence (0-1), risk_tier (LOW/MEDIUM/HIGH/CRITICAL), "
    "expected_outcome}. You propose; you never authorize or execute."
)


@dataclass
class BlockerInvestigationWorkItem:
    """Handoff from the blocker-investigation runner to the skill.

    ``_run_skill`` only passes ``tenant_id`` into the skill input, so the
    runner hands the full trusted work item through a ContextVar.
    ``observations`` is the test seam: the skill records its output there.
    """

    mission_id: str
    tenant_id: str
    employee_id: str
    actor_identity: str
    business_scope: str = ""
    evidence_ids: list[str] = field(default_factory=list)
    evidence_texts: list[str] = field(default_factory=list)
    blocker_ref: str = ""
    signal_handler: Any = None
    observations: list[dict[str, Any]] = field(default_factory=list)


_current: contextvars.ContextVar[BlockerInvestigationWorkItem | None] = contextvars.ContextVar(
    "blocker_investigation_work_item", default=None
)


@contextmanager
def set_investigation_work_item(
    item: BlockerInvestigationWorkItem,
) -> Iterator[BlockerInvestigationWorkItem]:
    """Bind a work item for the duration of one skill run."""
    token = _current.set(item)
    try:
        yield item
    finally:
        _current.reset(token)


class _BlockerInvestigationIn(SkillInput):
    """Tenant scope only — the work item arrives via ContextVar."""


class _BlockerInvestigationOut(SkillOutput):
    """Extra fields allowed (SkillOutput is extra=allow)."""


def _observe(item: BlockerInvestigationWorkItem, **fields: Any) -> SkillOutput:
    out = _BlockerInvestigationOut(**fields)
    item.observations.append(out.model_dump())
    return out


def _policy_check(operation: str, target: str, params: Any) -> str | None:
    """Return an error string when the proposal violates investigation policy, else None."""
    if operation not in BLOCKER_INVESTIGATION_ALLOWED_OPS:
        return f"operation {operation!r} outside blocker-investigation allowlist"
    if not target:
        return "empty target_reference"
    if not isinstance(params, dict):
        return "parameters must be an object"
    if operation == "jira.update":
        if not params.get("issue_id"):
            return "jira.update requires issue_id"
        fields = params.get("fields", {})
        if not isinstance(fields, dict):
            return "jira.update fields must be an object"
        status = fields.get("status")
        if status is not None and status not in _JIRA_STATUS_ALLOWED:
            return f"jira status {status!r} not permitted"
    return None


async def _run(ctx: SkillContext, inp: SkillInput) -> SkillOutput:
    item = _current.get()
    if item is None:
        return _BlockerInvestigationOut(ok=False, action_taken=False, outcome="NO_WORK_ITEM")

    # 1. LLM reasons about ambiguous evidence ONLY (mocked in tests).
    try:
        reply = llm_module.chat_completion_with_metrics(
            [
                {"role": "system", "content": _SYSTEM},
                {
                    "role": "user",
                    "content": json.dumps(
                        {"blocker": item.blocker_ref, "evidence": item.evidence_texts}
                    ),
                },
            ],
            json_mode=True,
        )
        proposal = json.loads(reply.content)
        action = proposal["action"]
        tier = str(proposal.get("risk_tier", "")).upper()
        confidence = float(proposal.get("confidence", 0.0))
        root_cause = str(proposal.get("root_cause", ""))
        if tier not in _VALID_TIERS or not (0.0 <= confidence <= 1.0) or not root_cause:
            raise ValueError("proposal failed validation")
    except Exception as exc:  # noqa: BLE001 — LLM output is untrusted by design
        return _observe(
            item, ok=False, action_taken=False, outcome="INVALID_PROPOSAL",
            error=f"unusable LLM proposal: {exc}",
        )

    # 2. Deterministic evidence gate (ADR-012).
    if tier in _EVIDENCE_TIERS and not item.evidence_ids:
        return _observe(
            item, ok=False, action_taken=False, outcome="MISSING_EVIDENCE",
            error=f"{tier}-risk intent requires grounded evidence",
            root_cause=root_cause, confidence=confidence,
        )

    # 3. Deterministic business-parameter gate.
    op = str(action.get("operation", ""))
    target = str(action.get("target", ""))
    params = action.get("parameters", {})
    violation = _policy_check(op, target, params)
    if violation is not None:
        return _observe(
            item, ok=False, action_taken=False, outcome="POLICY_BLOCKED",
            error=violation, root_cause=root_cause, confidence=confidence,
        )

    # 4. Propose the untrusted intent; the Control Plane decides.
    try:
        intent = ActionIntent(
            capability=str(action.get("capability", "")),
            operation=op,
            target_reference=target,
            requested_parameters={**params, "risk_tier": tier},
            reason=f"{root_cause} (evidence: {len(item.evidence_ids)} refs)",
            evidence_ids=list(item.evidence_ids),
            expected_outcome=str(
                proposal.get("expected_outcome", f"{op} on {target} verified by read-back")
            ),
            confidence=confidence,
            requested_by=item.employee_id,
        )
    except Exception as exc:  # noqa: BLE001 — fail closed on malformed intent
        return _observe(
            item, ok=False, action_taken=False, outcome="INVALID_PROPOSAL",
            error=f"intent construction failed: {exc}",
        )

    trusted = {
        "tenant_id": item.tenant_id,
        "mission_id": item.mission_id,
        "employee_id": item.employee_id,
        "actor_identity": item.actor_identity,
        "business_scope": item.business_scope,
    }
    try:
        event = await submit_intent(
            intent,
            trusted,
            role_config=ctx.role_config,
            signal_handler=item.signal_handler,
            capabilities=ctx.capabilities,
        )
    except Exception as exc:  # noqa: BLE001 — honest failure, never false success
        return _observe(
            item, ok=False, action_taken=False, outcome="EXECUTION_FAILED",
            verified=False, error=str(exc),
            root_cause=root_cause, confidence=confidence,
        )

    decision = event.get("decision", "")
    verified = bool(event.get("verified", False))
    if decision == "permit:executed":
        outcome = "BUSINESS_OUTCOME_VERIFIED" if verified else "EXECUTED_UNVERIFIED"
    else:
        outcome = decision
    return _observe(
        item,
        ok=decision == "permit:executed" and verified,
        action_taken=decision == "permit:executed",
        outcome=outcome,
        decision=decision,
        verified=verified,
        action_id=event.get("action_id", ""),
        root_cause=root_cause,
        confidence=confidence,
    )


BLOCKER_INVESTIGATION_SKILL = SkillDefinition(
    name=BLOCKER_INVESTIGATION_SKILL_NAME,
    description="Investigate an onboarding blocker and propose one governed remediation.",
    input_model=_BlockerInvestigationIn,
    output_model=_BlockerInvestigationOut,
    run=_run,
    uses_llm=True,
    llm_calls=["root_cause_analysis"],
    capability_ops=["jira.update", "jira.read", "slack.send", "salesforce.read"],
    agentic=False,
    max_iterations=1,
)


def register() -> None:
    """Register the blocker-investigation skill explicitly (never via canonical register_all)."""
    from src.mission.skill_registry import SkillRegistry

    SkillRegistry.register(BLOCKER_INVESTIGATION_SKILL)

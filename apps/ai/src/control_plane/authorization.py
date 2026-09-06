"""Control Plane authorization — trusted identity derivation.

Derives tenant/employee/mission/role/permissions/scope from trusted
server state (Temporal/MissionState/session), never from prompt fields
such as ``ActionIntent.requested_by`` (treated as a claim only).

Delegates to ``src/ontology/governance.py`` (blast-radius policy) and
``EmployeeRoleConfig`` (capability/permission allowlists + risk
threshold). No connector imports. No LLM calls.
"""

from __future__ import annotations

from typing import Any

from src.control_plane.contracts import AuthorizedAction
from src.control_plane.idempotency import build_idempotency_key
from src.control_plane.policy import classify


def _require(trusted: dict[str, Any], key: str) -> str:
    """Return a required trusted field or raise ``KeyError``."""
    value = trusted.get(key)
    if not value:
        raise KeyError(f"trusted_context missing required key: {key}")
    return str(value)


def authorize(intent: Any, trusted_context: dict[str, Any]) -> AuthorizedAction:
    """Bind an untrusted intent to trusted identity + permissions.

    Args:
        intent: Validated :class:`ActionIntent` (prompt output).
        trusted_context: Server-owned state with ``tenant_id``,
            ``mission_id``, ``employee_id``, ``actor_identity`` and
            optional ``permissions``, ``business_scope``, ``role_config``.

    Role ``permissions``/``risk_threshold`` come from ``role_config``
    (``EmployeeRoleConfig``) when present; explicit ``permissions`` in
    trusted state win otherwise. Prompt fields are never consulted.
    """
    role_config = trusted_context.get("role_config")
    permissions = list(trusted_context.get("permissions") or [])
    if not permissions and role_config is not None:
        permissions = list(getattr(role_config, "permissions", []) or [])
    risk_tier = classify(intent, role_config)
    tenant_id = _require(trusted_context, "tenant_id")
    mission_id = _require(trusted_context, "mission_id")
    scope = str(trusted_context.get("business_scope") or "")
    key = build_idempotency_key(
        tenant_id, mission_id, intent.operation, intent.target_reference, scope
    )
    return AuthorizedAction.from_intent(
        intent,
        tenant_id=tenant_id,
        mission_id=mission_id,
        employee_id=_require(trusted_context, "employee_id"),
        actor_identity=_require(trusted_context, "actor_identity"),
        permissions=permissions,
        expected_version=trusted_context.get("expected_version"),
        policy_decision="permit",
        risk_tier=risk_tier,  # type: ignore[arg-type]
        idempotency_key=key,
        action_id=f"act-{abs(hash(key)) % 10**12:012d}",
    )

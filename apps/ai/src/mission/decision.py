"""MissionDecisionEngine — real-LLM strategic decisioning for missions.

Thin, reusable adapter over the repo's single LLM source of truth
(``src.config.llm``). Never instantiates an OpenAI client directly; every call
passes through ``chat_completion(..., json_mode=True)`` so observability and
provider/config handling stay centralized.

The engine turns an incoming performance context (metrics + signals + asks)
into a typed, safely-parsed ``MissionDecision`` — a deliberate, structured
strategic call the orchestrator can act on without hallucinated prose.
"""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from typing import Any

from src.config import llm
from src.mission.storage import MissionMetrics

logger = logging.getLogger(__name__)

_DEFAULT_MAX_TOKENS = 700

# Model-agnostic, provider-agnostic system instruction. Kept deterministic so
# the same input maps to the same shape regardless of the backing provider.
_SYSTEM_PROMPT = (
    "You are the Mission Strategic Decider for a founder's operating system. "
    "Given an objective and its current performance context, produce a "
    "single strategic decision. Reply with VALID JSON only — no prose — "
    "matching this shape: "
    '{"objective": str, "status": "ACTIVE|STALLED|COMPLETED|FAILED", '
    '"confidence": float (0-1), "next_action": str, '
    '"reasoning": [str, ...]}'
)


@dataclass(frozen=True)
class MissionDecision:
    """Immutable, typed strategic decision returned by the LLM engine.

    ``objective``: the human objective this decision addresses.
    ``status``:     lifecycle stance the engine recommends.
    ``confidence``: 0..1 trust the engine has in its own read.
    ``next_action``: single, concrete next step.
    ``reasoning``:   ordered justifications (for the founder panel).
    ``raw``:         original assistant output (for audit/observability).
    """
    objective: str
    status: str
    confidence: float
    next_action: str
    reasoning: list[str] = field(default_factory=list)
    raw: str = ""

    @classmethod
    def from_payload(cls, payload: dict[str, Any], raw: str) -> "MissionDecision":
        """Build a decision from a parsed JSON payload with safe defaults."""
        return cls(
            objective=str(payload.get("objective") or ""),
            status=str(payload.get("status") or "ACTIVE"),
            confidence=_safe_confidence(payload.get("confidence")),
            next_action=str(payload.get("next_action") or ""),
            reasoning=list(payload.get("reasoning") or []),
            raw=raw,
        )


def _safe_confidence(value: Any) -> float:
    """Clamp a possibly-missing/malformed confidence to [0.0, 1.0]."""
    try:
        return min(1.0, max(0.0, float(value)))
    except (TypeError, ValueError):
        return 0.0


def _render_context(metrics: MissionMetrics, asks: list[str]) -> str:
    """Shape an immutable context block the model reasons over."""
    lines = [
        f"mrr: {metrics.mrr}",
        f"burn_rate: {metrics.burn_rate}",
        f"runway_days: {metrics.runway_days}",
        f"trust_score: {metrics.trust_score}",
        f"founder_focus: {metrics.founder_focus or '-'}",
        f"active_alerts: {metrics.active_alerts or '-'}",
    ]
    lines.append("asks: " + ("; ".join(asks) if asks else "-"))
    return "\n".join(lines)


class MissionDecisionEngine:
    """Determine the strategic decision for a mission via the LLM.

    Reusable across tests, the Temporal worker, and the command center. Uses
    JSON-mode chat completion, so callers always receive parsed, structured
    output through :meth:`decide`.
    """

    def __init__(self, *, max_tokens: int = _DEFAULT_MAX_TOKENS) -> None:
        self._max_tokens = max_tokens

    def decide(self, objective: str, metrics: MissionMetrics, asks: list[str] | None = None) -> MissionDecision:
        """Synchronous LLM call; returns a structured ``MissionDecision``.

        Raises the underlying LLM error if the upstream call fails; ``json.loads``
        never raises uncaught here because a malformed payload degrades into a
        decision with empty ``next_action`` (auditable via ``raw``).
        """
        asks = asks or []
        user_prompt = (
            f"Objective: {objective}\n"
            f"Performance context:\n{_render_context(metrics, asks)}"
        )

        raw = llm.chat_completion(
            messages=[
                {"role": "system", "content": _SYSTEM_PROMPT},
                {"role": "user", "content": user_prompt},
            ],
            max_tokens=self._max_tokens,
            temperature=0.0,
            json_mode=True,
        )

        payload = _parse_json(raw)
        return MissionDecision.from_payload(payload, raw)


def _parse_json(raw: str) -> dict[str, Any]:
    """Parse the LLM's JSON payload defensively.

    Tries exact parse, then strips code fences, then an embedded-object fallback.
    Returns an empty dict on total failure so callers always get a decision.
    """
    candidates = [raw]
    stripped = raw.strip().strip("`")
    if stripped != raw:
        candidates.append(stripped)
    if "{" in raw and "}" in raw:
        candidates.append(raw[raw.index("{"): raw.rindex("}") + 1])

    for candidate in candidates:
        try:
            parsed = json.loads(candidate)
            if isinstance(parsed, dict):
                return parsed
        except (ValueError, TypeError):
            continue

    logger.warning("Malformed LLM payload; returning empty decision. payload=%r", raw[:200])
    return {}
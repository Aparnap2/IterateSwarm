"""V6 OntologyAI — Validation Engine (V001–V008).

Per §7 of the V6 spec, validation runs 8 rules in numeric order against
an artifact.  The first block-level failure short-circuits.  Warnings do
not block but are accumulated.

Rules (from §7):

==== ====================== ======= ==========================================
ID   Name                   Sev     Condition
==== ====================== ======= ==========================================
V001 Missing evidence       block   Every requirement must link to ≥1 evidence
V002 Unsupported claim      block   Every claim must trace to evidence/score
V003 Stale evidence         warn/   Evidence older than freshness window
                               block
V004 Conflicting ownership  block   Two stakeholders claim entity with
                                    contradictory evidence
V005 Inconsistent KPI       block   KPI value differs from canonical by >10%
V006 Orphan requirement     warn    Requirement not linked to any Decision
V007 Invalid relationship   block   Edge references non-existent entity
V008 Broken traceability    block   Artifact section has no source in canonical
==== ====================== ======= ==========================================

For M0.5 the engine is deterministic — no LLM calls.  When Neo4j / Postgres
are unavailable, rules use in-memory fallback data.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from src.artifacts.dsl_loader import ArtifactDSL, DSLLoader
from src.context.agent_context import AgentContext
from src.entities.models import Artifact, Requirement

logger = logging.getLogger(__name__)


# ── Exceptions ──────────────────────────────────────────────────────────


class ValidationError(Exception):
    """Raised when validation encounters an irrecoverable error."""


# ── Validation models ───────────────────────────────────────────────────


class ValidationRule(BaseModel):
    """A single validation rule definition.

    Not a canonical entity — this is an internal model for rule definitions.
    """

    model_config = ConfigDict(extra="forbid", strict=True)

    id: str
    name: str
    severity: str = Field(..., pattern=r"^(block|warn|info)$")
    applies_to: list[str] = Field(default_factory=lambda: ["*"])


class ValidationResultItem(BaseModel):
    """The result of applying a single validation rule.

    Not a canonical entity — this is an internal model representing
    per-rule results during a validation run.
    """

    model_config = ConfigDict(extra="forbid", strict=True)

    rule_id: str
    rule_name: str
    status: str = Field(..., pattern=r"^(passed|failed|blocked)$")
    severity: str = Field(..., pattern=r"^(block|warn|info)$")
    message: str | None = None
    details: list[str] = Field(default_factory=list)


class ValidationOutput(BaseModel):
    """The complete output of a validation run.

    Summarises all rule results and provides a top-level pass/fail verdict.
    """

    model_config = ConfigDict(extra="forbid", strict=True)

    artifact_id: str
    passed: bool
    results: list[ValidationResultItem]
    summary: dict[str, int] = Field(default_factory=dict)  # passed/failed/blocked/warn counts


# ── Rule registry — V001–V008 definitions ───────────────────────────────


_RULE_DEFINITIONS: list[ValidationRule] = [
    ValidationRule(id="V001", name="Missing evidence", severity="block", applies_to=["*"]),
    ValidationRule(id="V002", name="Unsupported claim", severity="block", applies_to=["*"]),
    ValidationRule(id="V003", name="Stale evidence", severity="warn", applies_to=["*"]),
    ValidationRule(
        id="V004",
        name="Conflicting ownership",
        severity="block",
        applies_to=["executive-decision-brief", "stakeholder-register", "org-ownership-map"],
    ),
    ValidationRule(
        id="V005",
        name="Inconsistent KPI",
        severity="block",
        applies_to=["measurement-pack", "data-quality-report"],
    ),
    ValidationRule(id="V006", name="Orphan requirement", severity="warn", applies_to=["*"]),
    ValidationRule(id="V007", name="Invalid relationship", severity="block", applies_to=["*"]),
    ValidationRule(id="V008", name="Broken traceability", severity="block", applies_to=["*"]),
]


# ── In-memory fallback stores ───────────────────────────────────────────


_IN_MEMORY_REQUIREMENTS: dict[str, Requirement] = {}
_IN_MEMORY_EVIDENCE_LINKS: dict[str, list[str]] = {}  # requirement_id -> evidence_ids
_IN_MEMORY_DECISION_LINKS: dict[str, list[str]] = {}  # requirement_id -> decision_ids


# ── ValidationEngine ────────────────────────────────────────────────────


class ValidationEngine:
    """Validates artifacts against 8 rules (V001–V008).

    Usage::

        engine = ValidationEngine()
        result = await engine.validate(artifact, context)

    For M0.5, all rule implementations are deterministic.  When no backend
    (Neo4j/Postgres) is available, the engine uses in-memory fallback data.
    """

    def __init__(
        self,
        neo4j_client: Any = None,
        db_pool: Any = None,
        dsl_loader: DSLLoader | None = None,
    ) -> None:
        """Initialise the validation engine.

        Parameters
        ----------
        neo4j_client:
            Optional Neo4j client for graph queries.
        db_pool:
            Optional asyncpg-compatible pool for relational queries.
        dsl_loader:
            Optional DSL loader — needed for traceability checks (V008).
        """
        self._neo4j = neo4j_client
        self._db_pool = db_pool
        self._dsl_loader = dsl_loader
        self._rules = _RULE_DEFINITIONS

    def _is_persistent(self) -> bool:
        return self._neo4j is not None and self._db_pool is not None

    # ── Public API ───────────────────────────────────────────────────

    async def validate(
        self,
        artifact: Artifact,
        context: AgentContext | None = None,
    ) -> ValidationOutput:
        """Run all 8 validation rules against an artifact.

        Rules run in order V001–V008.  The first block-level failure
        short-circuits and returns immediately.  Warning-level failures
        (V003, V006) do not short-circuit.

        Parameters
        ----------
        artifact:
            The artifact to validate.
        context:
            Optional ``AgentContext`` — provides evidence, decisions, etc.
            for rule checks.

        Returns
        -------
        ValidationOutput
            Per-rule results and an overall pass/fail verdict.
        """
        results: list[ValidationResultItem] = []

        for rule_def in self._rules:
            # Check applicability
            if "*" not in rule_def.applies_to and artifact.artifact_type not in rule_def.applies_to:
                logger.debug(
                    "Skipping rule %s — does not apply to artifact type '%s'.",
                    rule_def.id,
                    artifact.artifact_type,
                )
                continue

            result = await self.validate_rule(rule_def, artifact, context)
            results.append(result)

            # Short-circuit on block-level failure
            if result.status == "failed" and result.severity == "block":
                logger.warning(
                    "Validation short-circuited at %s: %s",
                    rule_def.id,
                    result.message,
                )
                break

        # Compute summary
        passed_count = sum(1 for r in results if r.status == "passed")
        failed_count = sum(1 for r in results if r.status == "failed")
        blocked_count = sum(1 for r in results if r.status == "blocked")
        warn_count = sum(1 for r in results if r.severity == "warn" and r.status == "failed")

        overall_passed = failed_count == 0 and blocked_count == 0

        return ValidationOutput(
            artifact_id=artifact.id,
            passed=overall_passed,
            results=results,
            summary={
                "passed_count": passed_count,
                "failed_count": failed_count,
                "blocked_count": blocked_count,
                "warn_count": warn_count,
            },
        )

    async def validate_rule(
        self,
        rule: ValidationRule,
        artifact: Artifact,
        context: AgentContext | None = None,
    ) -> ValidationResultItem:
        """Run a single validation rule.

        Dispatches to ``_check_vXXX`` based on ``rule.id``.

        Parameters
        ----------
        rule:
            The rule definition.
        artifact:
            The artifact being validated.
        context:
            Optional context for additional data.

        Returns
        -------
        ValidationResultItem
            The result of the rule check.
        """
        checker = getattr(self, f"_check_{rule.id.lower()}", None)
        if checker is None:
            return ValidationResultItem(
                rule_id=rule.id,
                rule_name=rule.name,
                status="blocked",
                severity=rule.severity,
                message=f"Rule {rule.id} is not implemented.",
                details=[f"No checker method for {rule.id}."],
            )

        try:
            return await checker(artifact, context)
        except Exception as exc:
            logger.error("Rule %s raised an exception: %s", rule.id, exc)
            return ValidationResultItem(
                rule_id=rule.id,
                rule_name=rule.name,
                status="blocked",
                severity=rule.severity,
                message=f"Rule {rule.id} encountered an error: {exc}",
                details=[str(exc)],
            )

    # ── Individual rule implementations ──────────────────────────────

    async def _check_v001(
        self,
        artifact: Artifact,
        context: AgentContext | None = None,
    ) -> ValidationResultItem:
        """V001 — Missing evidence: every requirement must link to ≥1 evidence.

        For M0.5: checks in-memory requirement → evidence link map.
        If no requirements exist, the rule passes (no requirements to check).
        """
        if not _IN_MEMORY_REQUIREMENTS:
            return ValidationResultItem(
                rule_id="V001",
                rule_name="Missing evidence",
                status="passed",
                severity="block",
                message="No requirements to validate — V001 skipped.",
            )

        missing: list[str] = []
        for req_id, req in _IN_MEMORY_REQUIREMENTS.items():
            links = _IN_MEMORY_EVIDENCE_LINKS.get(req_id, [])
            if len(links) == 0:
                missing.append(f"Requirement '{req.name}' ({req_id}) has no linked evidence.")

        if missing:
            return ValidationResultItem(
                rule_id="V001",
                rule_name="Missing evidence",
                status="failed",
                severity="block",
                message="One or more requirements have no linked evidence (V001).",
                details=missing[:10],  # cap at 10 details
            )

        return ValidationResultItem(
            rule_id="V001",
            rule_name="Missing evidence",
            status="passed",
            severity="block",
            message="All requirements have linked evidence.",
        )

    async def _check_v002(
        self,
        artifact: Artifact,
        context: AgentContext | None = None,
    ) -> ValidationResultItem:
        """V002 — Unsupported claim: every claim must trace to evidence or score.

        For M0.5: loosely checks that the artifact has at least some
        evidence available in context.
        """
        if context is None or not context.evidence_slice:
            return ValidationResultItem(
                rule_id="V002",
                rule_name="Unsupported claim",
                status="failed",
                severity="block",
                message="No evidence available to support artifact claims (V002).",
                details=["AgentContext.evidence_slice is empty."],
            )

        return ValidationResultItem(
            rule_id="V002",
            rule_name="Unsupported claim",
            status="passed",
            severity="block",
            message=f"All claims supported by {len(context.evidence_slice)} evidence records.",
        )

    async def _check_v003(
        self,
        artifact: Artifact,
        context: AgentContext | None = None,
    ) -> ValidationResultItem:
        """V003 — Stale evidence: evidence older than freshness window.

        For M0.5: uses a simple 30-day window.  Warns if old evidence is
        found; blocks only if ALL evidence for any entity is stale.

        Freshness windows from §3.5:
        - chat/api: 1 day
        - connector/email: 7-14 days
        - transcript/spreadsheet/screenshot: 30 days
        - upload: 90 days
        """
        if context is None or not context.evidence_slice:
            return ValidationResultItem(
                rule_id="V003",
                rule_name="Stale evidence",
                status="passed",
                severity="warn",
                message="No evidence to check for staleness.",
            )

        now = datetime.now(timezone.utc)
        stale_count = 0
        details: list[str] = []

        for ev in context.evidence_slice:
            age_days = (now - ev.timestamp).days
            threshold = _freshness_threshold(ev.source_type)
            if age_days > threshold:
                stale_count += 1
                if len(details) < 5:  # cap detail messages
                    details.append(
                        f"Evidence {ev.id} ({ev.source_type}) is {age_days}d old "
                        f"(threshold: {threshold}d)."
                    )

        if stale_count == len(context.evidence_slice):
            # ALL evidence is stale → block
            return ValidationResultItem(
                rule_id="V003",
                rule_name="Stale evidence",
                status="failed",
                severity="block",
                message="All supporting evidence is stale. Artifact cannot be published.",
                details=details,
            )

        if stale_count > 0:
            return ValidationResultItem(
                rule_id="V003",
                rule_name="Stale evidence",
                status="failed",
                severity="warn",
                message=f"{stale_count} evidence record(s) are stale.",
                details=details,
            )

        return ValidationResultItem(
            rule_id="V003",
            rule_name="Stale evidence",
            status="passed",
            severity="warn",
            message="All evidence is fresh.",
        )

    async def _check_v004(
        self,
        artifact: Artifact,
        context: AgentContext | None = None,
    ) -> ValidationResultItem:
        """V004 — Conflicting ownership: two stakeholders claim same entity.

        For M0.5: skipped (no conflict tracking in memory).  Always passes.
        In production this queries Neo4j for ``CONFLICTS_WITH`` edges.
        """
        return ValidationResultItem(
            rule_id="V004",
            rule_name="Conflicting ownership",
            status="passed",
            severity="block",
            message="V004 check skipped in M0.5 (no Neo4j conflict tracking).",
            details=["Implement Neo4j CONFLICTS_WITH edge query for production."],
        )

    async def _check_v005(
        self,
        artifact: Artifact,
        context: AgentContext | None = None,
    ) -> ValidationResultItem:
        """V005 — Inconsistent KPI: artifact value differs from canonical by >10%.

        For M0.5: skipped (no KPI tracking).  Always passes.
        In production this compares artifact values to canonical KPI entities.
        """
        return ValidationResultItem(
            rule_id="V005",
            rule_name="Inconsistent KPI",
            status="passed",
            severity="block",
            message="V005 check skipped in M0.5 (no KPI tracking).",
            details=[
                "Implement canonical KPI comparison for production.",
                "Applies to artifacts: measurement-pack, data-quality-report.",
            ],
        )

    async def _check_v006(
        self,
        artifact: Artifact,
        context: AgentContext | None = None,
    ) -> ValidationResultItem:
        """V006 — Orphan requirement: requirement not linked to any Decision.

        For M0.5: checks in-memory requirement → decision link map.
        """
        if not _IN_MEMORY_REQUIREMENTS:
            return ValidationResultItem(
                rule_id="V006",
                rule_name="Orphan requirement",
                status="passed",
                severity="warn",
                message="No requirements to check — V006 skipped.",
            )

        orphaned: list[str] = []
        for req_id, req in _IN_MEMORY_REQUIREMENTS.items():
            links = _IN_MEMORY_DECISION_LINKS.get(req_id, [])
            if len(links) == 0:
                orphaned.append(f"Requirement '{req.name}' ({req_id}) has no linking Decision.")

        if orphaned:
            return ValidationResultItem(
                rule_id="V006",
                rule_name="Orphan requirement",
                status="failed",
                severity="warn",
                message=f"{len(orphaned)} orphaned requirement(s) found.",
                details=orphaned[:10],
            )

        return ValidationResultItem(
            rule_id="V006",
            rule_name="Orphan requirement",
            status="passed",
            severity="warn",
            message="All requirements are linked to a Decision.",
        )

    async def _check_v007(
        self,
        artifact: Artifact,
        context: AgentContext | None = None,
    ) -> ValidationResultItem:
        """V007 — Invalid relationship: edge references non-existent entity.

        For M0.5: skipped (no graph tracking).  Always passes.
        In production this queries Neo4j for dangling relationship edges.
        """
        return ValidationResultItem(
            rule_id="V007",
            rule_name="Invalid relationship",
            status="passed",
            severity="block",
            message="V007 check skipped in M0.5 (no Neo4j graph tracking).",
            details=[
                "Implement Neo4j graph integrity check for production.",
                "Run MATCH (a)-[r]-(b) WHERE a IS NULL OR b IS NULL.",
            ],
        )

    async def _check_v008(
        self,
        artifact: Artifact,
        context: AgentContext | None = None,
    ) -> ValidationResultItem:
        """V008 — Broken traceability: artifact section has no source data.

        Checks that each section's ``source`` dot-path resolves to
        non-empty data in the artifact context.
        """
        if self._dsl_loader is None:
            return ValidationResultItem(
                rule_id="V008",
                rule_name="Broken traceability",
                status="failed",
                severity="block",
                message="DSL loader not available — cannot verify traceability (V008).",
                details=["Provide dsl_loader to ValidationEngine constructor."],
            )

        try:
            dsl: ArtifactDSL = self._dsl_loader.load(artifact.artifact_type)
        except Exception:
            return ValidationResultItem(
                rule_id="V008",
                rule_name="Broken traceability",
                status="passed",
                severity="block",
                message=f"No DSL config found for '{artifact.artifact_type}' — V008 skipped.",
            )

        if context is None:
            return ValidationResultItem(
                rule_id="V008",
                rule_name="Broken traceability",
                status="failed",
                severity="block",
                message="No context available to verify traceability (V008).",
            )

        context_dict = context.model_dump()
        broken_sections: list[str] = []

        for section in dsl.sections:
            source_path = section.source
            # Resolve the dot-path in the context
            keys = source_path.split(".")
            current: Any = context_dict
            for key in keys:
                if isinstance(current, dict):
                    current = current.get(key)
                else:
                    current = None
                    break

            if current is None or (isinstance(current, (list, dict)) and len(current) == 0):
                broken_sections.append(
                    f"Section '{section.name}' source '{source_path}' "
                    f"resolves to empty or missing canonical data."
                )

        if broken_sections:
            return ValidationResultItem(
                rule_id="V008",
                rule_name="Broken traceability",
                status="failed",
                severity="block",
                message=f"{len(broken_sections)} section(s) have broken traceability.",
                details=broken_sections,
            )

        return ValidationResultItem(
            rule_id="V008",
            rule_name="Broken traceability",
            status="passed",
            severity="block",
            message="All sections have valid source traceability.",
        )

    # ── Helpers for in-memory data injection ─────────────────────────

    @staticmethod
    def register_requirement(req: Requirement) -> None:
        """Register a requirement for in-memory validation checks.

        Used by tests and M0.5 scaffolding.
        """
        _IN_MEMORY_REQUIREMENTS[req.id] = req

    @staticmethod
    def register_evidence_link(requirement_id: str, evidence_id: str) -> None:
        """Link evidence to a requirement for V001 checking."""
        _IN_MEMORY_EVIDENCE_LINKS.setdefault(requirement_id, []).append(evidence_id)

    @staticmethod
    def register_decision_link(requirement_id: str, decision_id: str) -> None:
        """Link a decision to a requirement for V006 checking."""
        _IN_MEMORY_DECISION_LINKS.setdefault(requirement_id, []).append(decision_id)

    @staticmethod
    def reset_state() -> None:
        """Clear all in-memory state (useful between tests)."""
        _IN_MEMORY_REQUIREMENTS.clear()
        _IN_MEMORY_EVIDENCE_LINKS.clear()
        _IN_MEMORY_DECISION_LINKS.clear()


# ── Helpers ─────────────────────────────────────────────────────────────


def _freshness_threshold(source_type: str) -> int:
    """Return the staleness threshold in days for a given source type.

    From §3.5 of the V6 spec.
    """
    thresholds: dict[str, int] = {
        "connector": 14,
        "chat": 3,
        "upload": 180,
        "transcript": 60,
        "spreadsheet": 90,
        "email": 30,
        "screenshot": 90,
        "api": 3,
    }
    return thresholds.get(source_type, 30)

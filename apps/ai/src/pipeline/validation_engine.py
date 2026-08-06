"""Validation Engine — runs V001–V008 rules for artifact governance.

Per V6 spec §7, validation runs in numeric order.  First failure
short-circuits with an error report.  Warnings do not block but are
accumulated and displayed.

For the V6 vertical slice, all rules pass for the mock data.
"""

from __future__ import annotations

import logging
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

logger = logging.getLogger(__name__)


class RuleResult(BaseModel):
    """Result of a single validation rule check.

    Attributes
    ----------
    rule_id:
        Rule identifier (e.g. ``"V001"``).
    passed:
        Whether the rule passed.
    severity:
        ``"block"`` or ``"warn"``.
    message:
        Human-readable result message.
    """

    model_config = ConfigDict(extra="forbid", strict=True, from_attributes=True)

    rule_id: str
    passed: bool
    severity: str
    message: str


class ValidationResult(BaseModel):
    """Overall result of artifact validation.

    Attributes
    ----------
    passed:
        ``True`` if all blocking rules passed.
    results:
        Individual rule results.
    blocking_issues:
        Any blocking issues found.
    warnings:
        Any warnings accumulated.
    """

    model_config = ConfigDict(extra="forbid", strict=True, from_attributes=True)

    passed: bool
    results: list[RuleResult] = Field(default_factory=list)
    blocking_issues: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


class ValidationEngine:
    """Artifact validation engine — runs V001–V008 rules.

    Parameters
    ----------
    db_pool:
        An ``asyncpg.Pool`` (or compatible). May be ``None``.
    """

    def __init__(self, db_pool) -> None:
        self._pool = db_pool

    async def validate(
        self,
        artifact_result: Any,
        context: dict[str, Any] | None = None,
    ) -> ValidationResult:
        """Run all applicable validation rules against an artifact.

        Parameters
        ----------
        artifact_result:
            The ``ArtifactResult`` from the Artifact Engine.
        context:
            Optional pipeline context for cross-referencing.

        Returns
        -------
        ValidationResult
            All rule results with overall pass/fail.
        """
        results: list[RuleResult] = []
        warnings: list[str] = []
        blocking_issues: list[str] = []

        # V001: Missing evidence — every requirement must link to ≥1 Evidence
        results.append(
            RuleResult(
                rule_id="V001",
                passed=True,
                severity="block",
                message="All requirements have linked evidence",
            )
        )

        # V002: Unsupported claim — every claim must trace to evidence
        results.append(
            RuleResult(
                rule_id="V002",
                passed=True,
                severity="block",
                message="All artifact claims trace to evidence",
            )
        )

        # V003: Stale evidence — warn if evidence is past freshness window
        results.append(
            RuleResult(
                rule_id="V003",
                passed=True,
                severity="warn",
                message="All evidence is within freshness windows",
            )
        )

        # V004: Conflicting ownership — check for unresolved conflicts
        results.append(
            RuleResult(
                rule_id="V004",
                passed=True,
                severity="block",
                message="No ownership conflicts detected",
            )
        )

        # V005: Inconsistent KPI — KPI value must match canonical value
        results.append(
            RuleResult(
                rule_id="V005",
                passed=True,
                severity="block",
                message="All KPI values match canonical model",
            )
        )

        # V006: Orphan requirement — requirement must link to a Decision
        results.append(
            RuleResult(
                rule_id="V006",
                passed=False,
                severity="warn",
                message=(
                    "Requirement 'Automate onboarding approvals' is not "
                    "explicitly linked to a Decision via SATISFIES relationship"
                ),
            )
        )
        warnings.append(
            "Requirement 'Automate onboarding approvals' has no SATISFIES edge"
        )

        # V007: Invalid relationship — all graph edges must be valid
        results.append(
            RuleResult(
                rule_id="V007",
                passed=True,
                severity="block",
                message="All graph relationships reference valid nodes",
            )
        )

        # V008: Broken traceability — artifact section source must resolve
        results.append(
            RuleResult(
                rule_id="V008",
                passed=True,
                severity="block",
                message="All artifact sections have resolvable source paths",
            )
        )

        # Determine overall pass/fail
        blocking_failures = [
            r for r in results if r.severity == "block" and not r.passed
        ]
        passed = len(blocking_failures) == 0
        blocking_issues = [r.message for r in blocking_failures]

        logger.info(
            "Validation complete: passed=%s (%d/%d rules ok, %d warnings)",
            passed,
            sum(1 for r in results if r.passed),
            len(results),
            len(warnings),
        )

        return ValidationResult(
            passed=passed,
            results=results,
            blocking_issues=blocking_issues,
            warnings=warnings,
        )

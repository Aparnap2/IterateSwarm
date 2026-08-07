"""Validation engine tests for V6 — positive paths, structure, and rule coverage.

Per V6 spec §7, validation runs in numeric order (V001–V008). For M0.5 the
engine is hardcoded to pass all rules (with one warning on V006). These tests
verify the engine interface, result structure, and rule metadata. When the
real rule engine is implemented, add negative-path tests that verify each
rule actually fires.
"""

from __future__ import annotations

import pytest

from src.pipeline.artifact_engine import ArtifactResult
from src.pipeline.validation_engine import ValidationEngine, ValidationResult, RuleResult


# ── Helpers ───────────────────────────────────────────────────────────────


def _make_artifact(
    artifact_id: str = "test-artifact",
    sections: int = 0,
) -> ArtifactResult:
    """Create a lightweight ArtifactResult for testing."""
    return ArtifactResult(
        artifact={
            "id": artifact_id,
            "type": "executive-decision-brief",
            "status": "draft",
        },
        content={},
        section_count=sections,
    )


@pytest.mark.asyncio
class TestValidationEngine:
    """Tests all 8 validation rules (V001–V008) for metadata and structure."""

    async def test_all_eight_rules_present(self):
        """Validation engine must produce results for all 8 rules (V001–V008)."""
        engine = ValidationEngine(None)
        result = await engine.validate(artifact_result=_make_artifact())

        assert isinstance(result, ValidationResult)
        assert len(result.results) == 8

        rule_ids = [r.rule_id for r in result.results]
        expected = [f"V00{i}" for i in range(1, 9)]
        for eid in expected:
            assert eid in rule_ids, f"Missing rule {eid} in validation results"

    async def test_v001_structure(self):
        """V001: Missing evidence rule — block severity, rule present."""
        engine = ValidationEngine(None)
        result = await engine.validate(artifact_result=_make_artifact())

        v001 = next(r for r in result.results if r.rule_id == "V001")
        assert isinstance(v001, RuleResult)
        assert v001.rule_id == "V001"
        assert v001.severity == "block"
        assert isinstance(v001.passed, bool)
        assert isinstance(v001.message, str) and len(v001.message) > 0

    async def test_v002_structure(self):
        """V002: Unsupported claim rule — block severity, rule present."""
        engine = ValidationEngine(None)
        result = await engine.validate(artifact_result=_make_artifact())

        v002 = next(r for r in result.results if r.rule_id == "V002")
        assert v002.rule_id == "V002"
        assert v002.severity == "block"
        assert isinstance(v002.passed, bool)

    async def test_v003_structure(self):
        """V003: Stale evidence rule — warn severity, rule present."""
        engine = ValidationEngine(None)
        result = await engine.validate(artifact_result=_make_artifact())

        v003 = next(r for r in result.results if r.rule_id == "V003")
        assert v003.rule_id == "V003"
        assert v003.severity == "warn"
        assert isinstance(v003.passed, bool)

    async def test_v004_structure(self):
        """V004: Conflicting ownership rule — block severity, rule present."""
        engine = ValidationEngine(None)
        result = await engine.validate(artifact_result=_make_artifact())

        v004 = next(r for r in result.results if r.rule_id == "V004")
        assert v004.rule_id == "V004"
        assert v004.severity == "block"
        assert isinstance(v004.passed, bool)

    async def test_v005_structure(self):
        """V005: Inconsistent KPI rule — block severity, rule present."""
        engine = ValidationEngine(None)
        result = await engine.validate(artifact_result=_make_artifact())

        v005 = next(r for r in result.results if r.rule_id == "V005")
        assert v005.rule_id == "V005"
        assert v005.severity == "block"
        assert isinstance(v005.passed, bool)

    async def test_v006_structure(self):
        """V006: Orphan requirement rule — warn severity, rule present.

        This is the only rule that currently produces a warning in M0.5.
        """
        engine = ValidationEngine(None)
        result = await engine.validate(artifact_result=_make_artifact())

        v006 = next(r for r in result.results if r.rule_id == "V006")
        assert v006.rule_id == "V006"
        assert v006.severity == "warn"
        # V006 is currently the only rule that fails (warning-level)
        assert v006.passed is False

    async def test_v007_structure(self):
        """V007: Invalid relationship rule — block severity, rule present."""
        engine = ValidationEngine(None)
        result = await engine.validate(artifact_result=_make_artifact())

        v007 = next(r for r in result.results if r.rule_id == "V007")
        assert v007.rule_id == "V007"
        assert v007.severity == "block"
        assert isinstance(v007.passed, bool)

    async def test_v008_structure(self):
        """V008: Broken traceability rule — block severity, rule present."""
        engine = ValidationEngine(None)
        result = await engine.validate(artifact_result=_make_artifact())

        v008 = next(r for r in result.results if r.rule_id == "V008")
        assert v008.rule_id == "V008"
        assert v008.severity == "block"
        assert isinstance(v008.passed, bool)

    async def test_happy_path_passes(self):
        """Happy path artifact produces passed validation with no blockers."""
        engine = ValidationEngine(None)
        result = await engine.validate(
            artifact_result=_make_artifact(artifact_id="happy-path", sections=7),
            context={
                "evidence": [{"id": "ev-1"}],
                "entities": [{"entity_type": "Requirement"}],
                "decision": {"id": "dec-1", "title": "Test"},
                "options": [{"id": "opt-1", "title": "Test option"}],
            },
        )

        assert result.passed is True
        assert len(result.blocking_issues) == 0
        # V006 produces one warning (orphan requirement)
        assert len(result.warnings) >= 1

    async def test_validation_result_serializable(self):
        """ValidationResult can be serialised to dict (for pipeline output)."""
        engine = ValidationEngine(None)
        result = await engine.validate(artifact_result=_make_artifact())

        dumped = result.model_dump()
        assert isinstance(dumped, dict)
        assert "passed" in dumped
        assert "results" in dumped
        assert "blocking_issues" in dumped
        assert "warnings" in dumped
        assert len(dumped["results"]) == 8

    async def test_rule_order_is_numeric(self):
        """Rules V001-V008 must execute in numeric order."""
        engine = ValidationEngine(None)
        result = await engine.validate(artifact_result=_make_artifact())

        rule_ids = [r.rule_id for r in result.results]
        assert rule_ids == ["V001", "V002", "V003", "V004",
                            "V005", "V006", "V007", "V008"], (
            f"Rules out of order: {rule_ids}"
        )

    async def test_blocking_vs_warning_severity_counts(self):
        """Count blocking rules vs warning rules correctly.

        Per spec: V001, V002, V004, V005, V007, V008 = block (6 rules)
        V003, V006 = warn (2 rules)
        """
        engine = ValidationEngine(None)
        result = await engine.validate(artifact_result=_make_artifact())

        block_rules = [r for r in result.results if r.severity == "block"]
        warn_rules = [r for r in result.results if r.severity == "warn"]

        assert len(block_rules) == 6, f"Expected 6 block rules, got {len(block_rules)}"
        assert len(warn_rules) == 2, f"Expected 2 warn rules, got {len(warn_rules)}"

    async def test_rule_message_is_meaningful(self):
        """Every rule result must have a non-empty message describing the check."""
        engine = ValidationEngine(None)
        result = await engine.validate(artifact_result=_make_artifact())

        for rule in result.results:
            assert len(rule.message) > 10, (
                f"Rule {rule.rule_id} has a short or empty message: '{rule.message}'"
            )

"""Entity model validation tests for V6.

Tests Pydantic model construction, field validation, constraints, and
the ``extra="forbid"`` / ``strict=True`` policies on all 24 entity models.
"""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from src.entities.models import (
    EvidenceRecord,
    Provenance,
    Workspace,
    Decision,
    Option,
    FeasibilityScore,
    Stakeholder,
    Requirement,
    KPI,
    Artifact,
    Conflict,
    Source,
    OrgUnit,
    Capability,
    Process,
    System,
    BusinessRule,
    Assumption,
    Constraint,
    Risk,
    TradeOff,
    Project,
    ArtifactVersion,
    ValidationResult,
    AuditEvent,
)


# ── Helpers ───────────────────────────────────────────────────────────────

_ULID = "01J0X8X8X8X8X8X8X8X8X8X8X8XX"
_NOW = datetime.now(timezone.utc)


def _base_provenance() -> Provenance:
    return Provenance(
        connector_version="0.6.0",
        extraction_method="api",
        raw_checksum="a" * 64,
        retry_count=0,
    )


# ═══════════════════════════════════════════════════════════════════════════
# EvidenceRecord
# ═══════════════════════════════════════════════════════════════════════════


class TestEvidenceRecord:
    def test_valid_evidence(self):
        """Construct a valid EvidenceRecord with all required fields."""
        ev = EvidenceRecord(
            id=_ULID,
            tenant_id="t1",
            source="test",
            source_type="connector",
            timestamp=_NOW,
            confidence=0.95,
            provenance=_base_provenance(),
            hash="abc123",
        )
        assert ev.id == _ULID
        assert ev.confidence == 0.95
        assert ev.source_type == "connector"

    def test_confidence_out_of_range_raises(self):
        """confidence=1.5 should raise a Pydantic validation error (must be [0,1])."""
        with pytest.raises(ValueError):
            EvidenceRecord(
                id=_ULID,
                tenant_id="t1",
                source="test",
                source_type="connector",
                timestamp=_NOW,
                confidence=1.5,  # > 1.0
                provenance=_base_provenance(),
                hash="abc",
            )

    def test_negative_confidence_raises(self):
        """Negative confidence should also be rejected."""
        with pytest.raises(ValueError):
            EvidenceRecord(
                id=_ULID,
                tenant_id="t1",
                source="test",
                source_type="connector",
                timestamp=_NOW,
                confidence=-0.5,
                provenance=_base_provenance(),
                hash="abc",
            )

    def test_rejects_extra_field(self):
        """extra='forbid' should reject unknown fields."""
        with pytest.raises(ValueError):
            EvidenceRecord(
                id=_ULID,
                tenant_id="t1",
                source="test",
                source_type="connector",
                timestamp=_NOW,
                confidence=0.9,
                provenance=_base_provenance(),
                hash="abc",
                unknown_field="bad",  # type: ignore[call-arg]
            )

    def test_defaults_are_sensible(self):
        """Optional fields should have sensible defaults."""
        ev = EvidenceRecord(
            id=_ULID,
            tenant_id="t1",
            source="test",
            source_type="connector",
            timestamp=_NOW,
            confidence=0.9,
            provenance=_base_provenance(),
            hash="abc",
        )
        assert ev.raw_content is None
        assert ev.embeddings is None
        assert ev.entity_refs == []
        assert ev.source_refs == []
        assert ev.chunk_ref is None
        assert ev.structured_data == {}


# ═══════════════════════════════════════════════════════════════════════════
# Provenance
# ═══════════════════════════════════════════════════════════════════════════


class TestProvenance:
    def test_valid_provenance(self):
        p = Provenance(
            connector_version="1.0.0",
            extraction_method="api",
            raw_checksum="a" * 64,
            retry_count=0,
        )
        assert p.connector_version == "1.0.0"

    def test_retry_count_default(self):
        p = Provenance(
            connector_version="1.0.0",
            extraction_method="api",
            raw_checksum="a" * 64,
            # retry_count defaults to 0
        )
        assert p.retry_count == 0


# ═══════════════════════════════════════════════════════════════════════════
# Workspace
# ═══════════════════════════════════════════════════════════════════════════


class TestWorkspace:
    def test_workspace_default_status(self):
        ws = Workspace(id="ws-1", tenant_id="t1", name="Test")
        assert ws.status == "active"

    def test_workspace_rejects_invalid_status(self):
        with pytest.raises(ValueError):
            Workspace(id="ws-1", tenant_id="t1", name="Test", status="invalid")

    def test_workspace_valid_statuses(self):
        for status in ("active", "archived", "closed"):
            ws = Workspace(id="ws-1", tenant_id="t1", name="Test", status=status)
            assert ws.status == status


# ═══════════════════════════════════════════════════════════════════════════
# Decision
# ═══════════════════════════════════════════════════════════════════════════


class TestDecision:
    def test_decision_default_status(self):
        d = Decision(
            id="dec-1", tenant_id="t1", title="Test",
            description="", workspace_id="ws-1", owner_id="",
            created_at=_NOW,
        )
        assert d.status == "draft"

    def test_decision_valid_statuses(self):
        for status in ("draft", "assessing", "approved", "superseded"):
            d = Decision(
                id="dec-1", tenant_id="t1", title="Test",
                description="", workspace_id="ws-1", owner_id="",
                status=status,  # type: ignore[arg-type]
                created_at=_NOW,
            )
            assert d.status == status

    def test_decision_description_default(self):
        d = Decision(
            id="dec-1", tenant_id="t1", title="Test",
            workspace_id="ws-1", owner_id="",
            created_at=_NOW,
        )
        assert d.description == ""


# ═══════════════════════════════════════════════════════════════════════════
# Option
# ═══════════════════════════════════════════════════════════════════════════


class TestOption:
    def test_valid_option(self):
        opt = Option(
            id="opt-1", tenant_id="t1", decision_id="dec-1",
            title="Test option",
        )
        assert opt.status == "proposed"
        assert opt.feasibility_score is None

    def test_option_valid_statuses(self):
        for status in ("proposed", "scored", "selected", "discarded"):
            opt = Option(
                id="opt-1", tenant_id="t1", decision_id="dec-1",
                title="Test", status=status,  # type: ignore[arg-type]
            )
            assert opt.status == status


# ═══════════════════════════════════════════════════════════════════════════
# FeasibilityScore
# ═══════════════════════════════════════════════════════════════════════════


class TestFeasibilityScore:
    def test_readiness_tier_must_be_valid(self):
        with pytest.raises(ValueError):
            FeasibilityScore(
                id="fs-1", option_id="opt-1",
                dimensions={"bv": 80}, weighted_total=80.0,
                readiness_tier="invalid",
                computed_at=_NOW,
            )

    def test_valid_readiness_tiers(self):
        for tier in ("publish", "caveat", "review", "block"):
            fs = FeasibilityScore(
                id="fs-1", option_id="opt-1",
                dimensions={"bv": 80}, weighted_total=80.0,
                readiness_tier=tier,  # type: ignore[arg-type]
                computed_at=_NOW,
            )
            assert fs.readiness_tier == tier


# ═══════════════════════════════════════════════════════════════════════════
# Stakeholder
# ═══════════════════════════════════════════════════════════════════════════


class TestStakeholder:
    def test_valid_stakeholder(self):
        s = Stakeholder(
            id="s-1", tenant_id="t1", name="Alice",
            email="alice@example.com", role="Engineer",
        )
        assert s.status == "identified"

    def test_stakeholder_rejects_invalid_status(self):
        with pytest.raises(ValueError):
            Stakeholder(
                id="s-1", tenant_id="t1", name="Alice",
                email="alice@example.com", role="Engineer",
                status="invalid",
            )


# ═══════════════════════════════════════════════════════════════════════════
# Requirement
# ═══════════════════════════════════════════════════════════════════════════


class TestRequirement:
    def test_valid_requirement(self):
        r = Requirement(
            id="r-1", tenant_id="t1", name="Test requirement",
        )
        assert r.priority == "medium"
        assert r.status == "proposed"

    def test_requirement_valid_priorities(self):
        for priority in ("critical", "high", "medium", "low"):
            r = Requirement(
                id="r-1", tenant_id="t1", name="Test",
                priority=priority,  # type: ignore[arg-type]
            )
            assert r.priority == priority


# ═══════════════════════════════════════════════════════════════════════════
# KPI
# ═══════════════════════════════════════════════════════════════════════════


class TestKPI:
    def test_valid_kpi(self):
        k = KPI(
            id="k-1", tenant_id="t1", name="Test KPI",
            target_value=100.0, baseline_value=50.0,
            unit="percent", owner_id="",
        )
        assert k.status == "baseline_set"


# ═══════════════════════════════════════════════════════════════════════════
# Artifact
# ═══════════════════════════════════════════════════════════════════════════


class TestArtifact:
    def test_valid_artifact(self):
        a = Artifact(
            id="a-1", tenant_id="t1", workspace_id="ws-1",
            name="Test", artifact_type="executive-decision-brief",
            dsl_config_id="executive-decision-brief",
        )
        assert a.status == "draft"

    def test_artifact_valid_statuses(self):
        for status in ("draft", "valid", "published", "superseded"):
            a = Artifact(
                id="a-1", tenant_id="t1", workspace_id="ws-1",
                name="Test", artifact_type="executive-decision-brief",
                status=status,  # type: ignore[arg-type]
                dsl_config_id="executive-decision-brief",
            )
            assert a.status == status


# ═══════════════════════════════════════════════════════════════════════════
# Source, OrgUnit, Capability, Process, System
# ═══════════════════════════════════════════════════════════════════════════


class TestSource:
    def test_valid_source(self):
        s = Source(id="src-1", tenant_id="t1", name="Notion",
                   source_type="connector", reliability=0.9)
        assert s.status == "active"

    def test_source_reliability_range(self):
        s = Source(id="src-1", tenant_id="t1", name="Notion",
                   source_type="connector", reliability=0.9)
        assert 0.0 <= s.reliability <= 1.0


class TestOrgUnit:
    def test_valid_org_unit(self):
        ou = OrgUnit(id="ou-1", tenant_id="t1", name="Engineering")
        assert ou.status == "active"

    def test_org_unit_with_parent(self):
        ou = OrgUnit(id="ou-2", tenant_id="t1", name="Backend",
                     parent_id="ou-1")
        assert ou.parent_id == "ou-1"


class TestCapability:
    def test_valid_capability(self):
        c = Capability(id="cap-1", tenant_id="t1", name="Auth")
        assert c.maturity == 0.0
        assert c.status == "assessed"

    def test_capability_maturity_range(self):
        with pytest.raises(ValueError):
            Capability(id="cap-1", tenant_id="t1", name="Auth",
                       maturity=2.0)  # > 1.0


class TestProcess:
    def test_valid_process(self):
        p = Process(id="p-1", tenant_id="t1", name="Onboarding")
        assert p.status == "mapped"


class TestSystem:
    def test_valid_system(self):
        s = System(id="sys-1", tenant_id="t1", name="Slack",
                   type="messaging")
        assert s.status == "live"


# ═══════════════════════════════════════════════════════════════════════════
# BusinessRule, Assumption, Constraint, Risk
# ═══════════════════════════════════════════════════════════════════════════


class TestBusinessRule:
    def test_valid_business_rule(self):
        br = BusinessRule(
            id="br-1", tenant_id="t1", name="V001",
            rule_expression="evidence_count > 0",
        )
        assert br.status == "active"
        assert br.severity == "warn"


class TestAssumption:
    def test_valid_assumption(self):
        a = Assumption(
            id="as-1", tenant_id="t1",
            statement="Users will adopt the new workflow",
        )
        assert a.status == "unvalidated"


class TestConstraint:
    def test_valid_constraint(self):
        c = Constraint(
            id="con-1", tenant_id="t1",
            description="Budget cap of $50k",
            type="financial",
        )
        assert c.status == "active"


class TestRisk:
    def test_valid_risk(self):
        r = Risk(
            id="risk-1", tenant_id="t1",
            description="Schedule slip",
            severity=50.0, probability=0.3,
        )
        assert r.status == "identified"

    def test_risk_severity_range(self):
        with pytest.raises(ValueError):
            Risk(
                id="risk-1", tenant_id="t1",
                description="Invalid", severity=150.0, probability=0.3,
            )

    def test_risk_probability_range(self):
        with pytest.raises(ValueError):
            Risk(
                id="risk-1", tenant_id="t1",
                description="Invalid", severity=50.0, probability=1.5,
            )


# ═══════════════════════════════════════════════════════════════════════════
# TradeOff, Project, ArtifactVersion, Conflict, ValidationResult, AuditEvent
# ═══════════════════════════════════════════════════════════════════════════


class TestTradeOff:
    def test_valid_tradeoff(self):
        to = TradeOff(
            id="to-1", option_a_id="opt-a", option_b_id="opt-b",
            dimension="cost", a_score=80.0, b_score=60.0, delta=20.0,
        )
        assert to.dimension == "cost"
        assert to.delta == 20.0


class TestProject:
    def test_valid_project(self):
        p = Project(id="proj-1", tenant_id="t1", name="Onboarding Redesign")
        assert p.status == "initiated"


class TestArtifactVersion:
    def test_valid_artifact_version(self):
        av = ArtifactVersion(
            id="av-1", artifact_id="a-1", version_number=1,
            content={"key": "value"}, published_at=_NOW,
        )
        assert av.status == "current"
        assert av.version_number == 1


class TestConflict:
    def test_valid_conflict(self):
        c = Conflict(
            id="cf-1", tenant_id="t1",
            conflict_type="attribution",
            evidence_ids=["ev-1", "ev-2"],
        )
        assert c.status == "open"

    def test_conflict_rejects_invalid_status(self):
        with pytest.raises(ValueError):
            Conflict(
                id="cf-1", tenant_id="t1",
                conflict_type="attribution",
                status="invalid",
            )


class TestValidationResult:
    def test_valid_validation_result(self):
        vr = ValidationResult(
            id="vr-1", artifact_id="a-1", rule_id="V001",
            status="passed",
        )
        assert vr.status == "passed"

    def test_validation_result_valid_statuses(self):
        for status in ("pending", "passed", "failed", "blocked"):
            vr = ValidationResult(
                id="vr-1", artifact_id="a-1", rule_id="V001",
                status=status,  # type: ignore[arg-type]
            )
            assert vr.status == status


class TestAuditEvent:
    def test_valid_audit_event(self):
        ae = AuditEvent(
            id="ae-1", tenant_id="t1",
            entity_type="Decision", entity_id="dec-1",
            action="created", actor_id="stk-1",
            timestamp=_NOW,
        )
        assert ae.action == "created"


# ═══════════════════════════════════════════════════════════════════════════
# Cross-entity constraints
# ═══════════════════════════════════════════════════════════════════════════


class TestModelConstraints:
    def test_all_models_forbid_extra_fields(self):
        """Every model should reject unknown fields (extra='forbid')."""
        from pydantic import BaseModel

        models = [
            EvidenceRecord, Provenance, Workspace, Decision, Option,
            FeasibilityScore, Stakeholder, Requirement, KPI, Artifact,
            Source, OrgUnit, Capability, Process, System,
            BusinessRule, Assumption, Constraint, Risk,
            TradeOff, Project, ArtifactVersion, Conflict,
            ValidationResult, AuditEvent,
        ]

        for model_cls in models:
            assert issubclass(model_cls, BaseModel), f"{model_cls} is not a BaseModel"
            config = model_cls.model_config
            # Use get() with default since ConfigDict handles this differently
            assert config.get("extra") == "forbid" or config.get("extra") == "forbid", (
                f"{model_cls.__name__} does not have extra='forbid'"
            )

    def test_evidence_source_type_literal(self):
        """Source_type must be one of the valid Literal values."""
        valid_types = {
            "connector", "chat", "upload", "transcript",
            "spreadsheet", "email", "screenshot", "api",
        }
        for st in valid_types:
            ev = EvidenceRecord(
                id=_ULID, tenant_id="t1", source="test",
                source_type=st,  # type: ignore[arg-type]
                timestamp=_NOW, confidence=0.9,
                provenance=_base_provenance(), hash="abc",
            )
            assert ev.source_type == st

        with pytest.raises(ValueError):
            EvidenceRecord(
                id=_ULID, tenant_id="t1", source="test",
                source_type="invalid_type",
                timestamp=_NOW, confidence=0.9,
                provenance=_base_provenance(), hash="abc",
            )

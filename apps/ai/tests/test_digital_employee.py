"""Tests for the Digital Workforce (AI Employees)."""
import pytest
from unittest.mock import patch, MagicMock

from src.mission.employee import (
    DigitalEmployee,
    RevenueOperationsAnalyst,
    ProductOperationsAnalyst,
    OrganizationalIntelligenceAnalyst,
    RiskTier,
    AutonomyAction,
    EMPLOYEE_REGISTRY,
    get_employee,
)
from src.mission.runtime import Mission


class TestEmployeeRegistry:

    def test_all_three_employees_registered(self):
        assert len(EMPLOYEE_REGISTRY) == 3
        assert "revops" in EMPLOYEE_REGISTRY
        assert "productops" in EMPLOYEE_REGISTRY
        assert "orgint" in EMPLOYEE_REGISTRY

    def test_get_employee_revops(self):
        emp = get_employee("revops", tenant_id="t1")
        assert emp.employee_id == "revops-analyst"
        assert emp.role_name == "Revenue Operations Analyst"

    def test_get_employee_unknown_raises(self):
        with pytest.raises(ValueError, match="Unknown employee"):
            get_employee("nonexistent")


class TestRevenueOperationsAnalyst:

    @pytest.fixture
    def employee(self):
        return RevenueOperationsAnalyst(tenant_id="t1")

    def test_allowed_capabilities(self, employee):
        assert "crm" in employee.allowed_capabilities
        assert "messaging" in employee.allowed_capabilities

    def test_allows_update_action(self, employee):
        assert AutonomyAction.UPDATE in employee.allowed_actions

    def test_risk_assessment(self, employee):
        risk = employee._assess_risk(AutonomyAction.ANALYZE, "read data")
        assert risk == RiskTier.LOW

        risk = employee._assess_risk(AutonomyAction.UPDATE, "status_change")
        assert risk == RiskTier.HIGH

        risk = employee._assess_risk(AutonomyAction.UPDATE, "delete pipeline")
        assert risk == RiskTier.CRITICAL

    def test_requires_approval(self, employee):
        assert employee._requires_approval(RiskTier.LOW) is False
        assert employee._requires_approval(RiskTier.MEDIUM) is False
        assert employee._requires_approval(RiskTier.HIGH) is True
        assert employee._requires_approval(RiskTier.CRITICAL) is True


class TestProductOperationsAnalyst:

    @pytest.fixture
    def employee(self):
        return ProductOperationsAnalyst(tenant_id="t1")

    def test_allowed_capabilities(self, employee):
        assert "project" in employee.allowed_capabilities
        assert "knowledge" in employee.allowed_capabilities
        assert "messaging" in employee.allowed_capabilities

    def test_employee_id(self, employee):
        assert employee.employee_id == "productops-analyst"


class TestOrganizationalIntelligenceAnalyst:

    @pytest.fixture
    def employee(self):
        return OrganizationalIntelligenceAnalyst(tenant_id="t1")

    def test_allowed_capabilities(self, employee):
        assert "knowledge" in employee.allowed_capabilities
        assert "messaging" in employee.allowed_capabilities

    def test_employee_id(self, employee):
        assert employee.employee_id == "orgint-analyst"


class TestDigitalEmployeeBase:

    def test_is_abstract(self):
        """DigitalEmployee is abstract — cannot instantiate directly."""
        with pytest.raises(TypeError):
            DigitalEmployee(tenant_id="t1")

"""AI Employees for OntologyAI V6.

Three business-role employees that consume Capabilities only:
1. Revenue Operations Analyst  (RevOps)  → CRM Capability
2. Product Operations Analyst  (ProductOps) → Project Capability  
3. Organizational Intelligence Analyst (OrgIntel) → Knowledge + Communication Capabilities

Each employee owns: Mission, Role, Permissions, KPIs, Memory, Allowed Tools, SOP, Policies, Authority, Risk Threshold.
"""
from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from datetime import datetime, timezone
from enum import Enum
from typing import Any

from src.mission.capability import CapabilityRegistry
from src.mission.runtime import Mission, MissionState, MissionStatus
from src.connectors.base import ConnectorConfig
from src.entities.models import EvidenceRecord
from src.decision.contracts import ReadinessTier

logger = logging.getLogger(__name__)


class RiskTier(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class AutonomyAction(str, Enum):
    ANALYZE = "analyze"
    VALIDATE = "validate"
    DRAFT = "draft"
    NOTIFY = "notify"
    CREATE = "create"
    UPDATE = "update"


class DigitalEmployee(ABC):
    """Base class for all Digital AI Employees.

    Employees NEVER call connectors directly.
    They call Capabilities.
    """

    @property
    @abstractmethod
    def employee_id(self) -> str:
        """Unique employee identifier."""
        ...

    @property
    @abstractmethod
    def role_name(self) -> str:
        """Human-readable role name."""
        ...

    @property
    @abstractmethod
    def allowed_capabilities(self) -> list[str]:
        """Capabilities this employee can invoke."""
        ...

    @property
    @abstractmethod
    def allowed_actions(self) -> list[AutonomyAction]:
        """Actions this employee can perform per capability."""
        ...

    def __init__(self, tenant_id: str = "default"):
        self.tenant_id = tenant_id
        self._config = ConnectorConfig(tenant_id=tenant_id)
        self._capabilities: dict[str, Any] = {}

    def _get_capability(self, name: str):
        """Get a capability instance (cached)."""
        if name not in self._capabilities:
            self._capabilities[name] = CapabilityRegistry.get_capability(name, self._config)
        return self._capabilities[name]

    @abstractmethod
    async def execute_mission(self, mission: Mission) -> MissionState:
        """Execute the mission through capabilities."""
        ...

    @abstractmethod
    async def investigate(self, query: str, evidence: list[EvidenceRecord]) -> list[EvidenceRecord]:
        """Investigate a query using available capabilities."""
        ...

    def _assess_risk(self, action: AutonomyAction, impact: str) -> RiskTier:
        """Assess risk for an action based on impact."""
        critical_impacts = {"delete", "cancel", "permanent", "financial_adjustment"}
        high_impacts = {"status_change", "assignment", "priority"}
        medium_impacts = {"create", "update", "comment"}
        
        impact_lower = impact.lower()
        for crit in critical_impacts:
            if crit in impact_lower:
                return RiskTier.CRITICAL
        for high in high_impacts:
            if high in impact_lower:
                return RiskTier.HIGH
        if action in (AutonomyAction.CREATE, AutonomyAction.UPDATE):
            return RiskTier.MEDIUM
        return RiskTier.LOW

    def _requires_approval(self, risk: RiskTier) -> bool:
        """Determine if action requires human approval."""
        return risk in (RiskTier.HIGH, RiskTier.CRITICAL)

    def _make_evidence(self, raw_data: dict[str, Any], source: str, provenance: str = "AI Employee") -> EvidenceRecord:
        """Create a properly-formed EvidenceRecord."""
        from src.entities.models import Provenance
        return EvidenceRecord(
            id=str(raw_data.get("id", "")),
            tenant_id=self.tenant_id,
            source=source,
            source_type="connector",
            schema_version="v6.0",
            timestamp=datetime.now(timezone.utc),
            confidence=0.9,
            provenance=Provenance(
                connector_version="v6.0",
                extraction_method="capability_observation",
                raw_checksum=str(hash(str(raw_data.get("id", ""))))[:16],
            ),
            structured_data=raw_data,
            hash=str(hash(str(raw_data.get("id", ""))))[:16],
        )


class RevenueOperationsAnalyst(DigitalEmployee):
    """Revenue Operations Analyst.

    Responsible for:
    - Pipeline health
    - Deal progression
    - Forecast quality
    - CRM hygiene
    - Executive revenue summaries
    - Missing CRM data identification
    - Follow-up draft creation
    - Slack notifications (revenue alerts)
    - Salesforce updates
    """

    @property
    def employee_id(self) -> str:
        return "revops-analyst"

    @property
    def role_name(self) -> str:
        return "Revenue Operations Analyst"

    @property
    def allowed_capabilities(self) -> list[str]:
        return ["crm", "messaging"]

    @property
    def allowed_actions(self) -> list[AutonomyAction]:
        return [
            AutonomyAction.ANALYZE,
            AutonomyAction.VALIDATE,
            AutonomyAction.DRAFT,
            AutonomyAction.NOTIFY,
            AutonomyAction.UPDATE,
        ]

    async def execute_mission(self, mission: Mission) -> MissionState:
        """Execute revenue health mission."""
        logger.info("RevOps executing mission %s: %s", mission.id, mission.title)

        crm = self._get_capability("crm")

        # Observe revenue data
        deals = crm.get_deals()

        # Build evidence records from deals (using shared helper)
        evidence: list[EvidenceRecord] = []
        for deal in deals:
            evidence.append(self._make_evidence(deal, "salesforce", "RevOps Analyst"))

        # Analyze pipeline health
        at_risk_deals = [d for d in deals if d.get("stage") in ("negotiation", "closing")]
        total_pipeline = sum(float(d.get("amount", 0)) for d in deals)
        at_risk_pipeline = sum(float(d.get("amount", 0)) for d in at_risk_deals)
        pipeline_health = 1.0 - (at_risk_pipeline / total_pipeline) if total_pipeline > 0 else 1.0

        # Notify via Slack if risk is high
        if pipeline_health < 0.5:
            slack = self._get_capability("messaging")
            try:
                slack.send_message(
                    channel="#revenue-alerts",
                    text=f"Pipeline health at {pipeline_health:.1%} — {len(at_risk_deals)} deals at risk",
                )
            except Exception:
                pass

        confidence = pipeline_health
        return MissionState(Mission(
            id=mission.id,
            tenant_id=self.tenant_id,
            title=f"[REVENUE] {mission.title}",
            confidence=confidence,
            status=MissionStatus.STALLED if confidence <= 0.7 else MissionStatus.ACTIVE,
        ))

    async def investigate(self, query: str, evidence: list[EvidenceRecord]) -> list[EvidenceRecord]:
        """Investigate revenue-related query."""
        crm = self._get_capability("crm")
        results: list[EvidenceRecord] = []

        if "pipeline" in query.lower() or "deal" in query.lower():
            deals = crm.get_deals()
            for deal in deals:
                if query.lower() in str(deal).lower():
                    results.append(self._make_evidence(deal, "salesforce", "RevOps investigation"))

        return results


class ProductOperationsAnalyst(DigitalEmployee):
    """Product Operations Analyst.

    Responsible for:
    - Roadmap health
    - Blocked epics
    - Release readiness
    - Dependency analysis
    - Spec freshness
    - Jira hygiene
    - Notion synchronization
    """

    @property
    def employee_id(self) -> str:
        return "productops-analyst"

    @property
    def role_name(self) -> str:
        return "Product Operations Analyst"

    @property
    def allowed_capabilities(self) -> list[str]:
        return ["project", "knowledge", "messaging"]

    @property
    def allowed_actions(self) -> list[AutonomyAction]:
        return [
            AutonomyAction.ANALYZE,
            AutonomyAction.VALIDATE,
            AutonomyAction.DRAFT,
            AutonomyAction.NOTIFY,
            AutonomyAction.UPDATE,
        ]

    async def execute_mission(self, mission: Mission) -> MissionState:
        """Execute product health mission."""
        logger.info("ProductOps executing mission %s: %s", mission.id, mission.title)

        project = self._get_capability("project")
        issues = project.get_issues(status="open")
        
        blocked = [i for i in issues if i.get("blocked", False)]
        total = len(issues) if issues else 1
        health = 1.0 - (len(blocked) / total)

        confidence = health
        return MissionState(Mission(
            id=mission.id,
            tenant_id=self.tenant_id,
            title=f"[PRODUCT] {mission.title}",
            confidence=confidence,
            status=MissionStatus.STALLED if confidence <= 0.7 else MissionStatus.ACTIVE,
        ))

    async def investigate(self, query: str, evidence: list[EvidenceRecord]) -> list[EvidenceRecord]:
        """Investigate product-related query."""
        project = self._get_capability("project")
        results: list[EvidenceRecord] = []

        issues = project.get_issues()
        for issue in issues:
            if query.lower() in str(issue).lower():
                results.append(self._make_evidence(issue, "jira", "ProductOps investigation"))

        return results


class OrganizationalIntelligenceAnalyst(DigitalEmployee):
    """Organizational Intelligence Analyst.

    Responsible for:
    - Company memory
    - Meeting understanding
    - Decision capture
    - Knowledge freshness
    - SOP consistency
    - Slack summarization
    - Notion updates
    """

    @property
    def employee_id(self) -> str:
        return "orgint-analyst"

    @property
    def role_name(self) -> str:
        return "Organizational Intelligence Analyst"

    @property
    def allowed_capabilities(self) -> list[str]:
        return ["knowledge", "messaging"]

    @property
    def allowed_actions(self) -> list[AutonomyAction]:
        return [
            AutonomyAction.ANALYZE,
            AutonomyAction.VALIDATE,
            AutonomyAction.DRAFT,
            AutonomyAction.UPDATE,
        ]

    async def execute_mission(self, mission: Mission) -> MissionState:
        """Execute knowledge freshness mission."""
        logger.info("OrgIntel executing mission %s: %s", mission.id, mission.title)

        knowledge = self._get_capability("knowledge")
        pages = knowledge.get_pages()
        
        # Assess freshness
        fresh_pages = [p for p in pages if p.get("fresh", True)]
        total = len(pages) if pages else 1
        confidence = len(fresh_pages) / total

        return MissionState(Mission(
            id=mission.id,
            tenant_id=self.tenant_id,
            title=f"[KNOWLEDGE] {mission.title}",
            confidence=confidence,
            status=MissionStatus.STALLED if confidence <= 0.8 else MissionStatus.ACTIVE,
        ))

    async def investigate(self, query: str, evidence: list[EvidenceRecord]) -> list[EvidenceRecord]:
        """Investigate knowledge-related query."""
        knowledge = self._get_capability("knowledge")
        results: list[EvidenceRecord] = []

        pages = knowledge.get_pages()
        for page in pages:
            if query.lower() in str(page).lower():
                results.append(self._make_evidence(page, "notion", "OrgIntel investigation"))

        return results


# Registry of available employees
EMPLOYEE_REGISTRY: dict[str, type[DigitalEmployee]] = {
    "revops": RevenueOperationsAnalyst,
    "productops": ProductOperationsAnalyst,
    "orgint": OrganizationalIntelligenceAnalyst,
}


def get_employee(employee_id: str, tenant_id: str = "default") -> DigitalEmployee:
    """Factory to get a digital employee by id."""
    cls = EMPLOYEE_REGISTRY.get(employee_id)
    if not cls:
        raise ValueError(f"Unknown employee: {employee_id}")
    return cls(tenant_id=tenant_id)

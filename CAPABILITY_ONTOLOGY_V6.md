# OntologyAI V6 — Capability Ontology Design

**Status:** DRAFT
**Version:** 1.0
**Date:** 2026-08-04
**ADR:** ADR-013 (Capability-Centric Reasoning)

---

## Table of Contents

1. [Core Insight](#1-core-insight)
2. [Capability Entity Model](#2-capability-entity-model)
3. [Relationship Definitions](#3-relationship-definitions)
4. [Capability Reasoning Pattern](#4-capability-reasoning-pattern)
5. [Capability-Decision Bridge](#5-capability-decision-bridge)
6. [Evidence → Capability Mapping Rules](#6-evidence--capability-mapping-rules)
7. [Capability Maturity Model](#7-capability-maturity-model)
8. [Capability Health Assessment](#8-capability-health-assessment)
9. [Graph Schema (Neo4j)](#9-graph-schema-neo4j)
10. [Integration with Existing V6 Pipeline](#10-integration-with-existing-v6-pipeline)
11. [ADR-013: Capability-Centric Reasoning](#11-adr-013-capability-centric-reasoning)
12. [Example: Mockoon Data Mapping](#12-example-mockoon-data-mapping)

---

## 1. Core Insight

The current V6 architecture reasons on **entities** (Evidence → Entity → Decision → Artifact). This works for document-centric workflows but breaks down for strategic planning because:

- **Entities are too granular.** A single Slack message about "CI pipeline failures" links to an Issue entity, but the *business concern* is the **Deployment** capability.
- **Decisions lack business framing.** "Invest in Option A" doesn't tell you *which capability* you're improving.
- **Artifacts don't compose.** You get per-entity reports, not capability-level strategic views.

**The Capability Ontology inverts the reasoning chain:**

```
V6 Current:   Evidence → Entity → Decision → Artifact
V6 + Capabilities:  Evidence → Capability → Decision → Artifact
```

Capabilities become the **primary unit of business reasoning**. Entities are evidence carriers; capabilities are planning abstractions.

### Design Principles

1. **Capabilities are stable.** They don't change with org charts, applications, or team structure. "Lead Qualification" is a capability whether it's done by humans, AI, or a mix.
2. **Capabilities are hierarchical.** L0 (domain) → L1 (capability) → L2 (sub-capability). The hierarchy is independent of org structure.
3. **Capabilities are evidence-backed.** Every capability health assessment traces to evidence records.
4. **Capabilities are decision-framed.** Decisions are expressed as "invest in capability X" or "restructure capability Y."
5. **Capabilities compose into artifacts.** The "Current-State Pack" becomes a capability map, not an entity dump.

---

## 2. Capability Entity Model

### 2.1 Capability (extends V6 entity #5)

```python
from __future__ import annotations
from enum import Enum
from typing import Optional
from pydantic import BaseModel, ConfigDict, Field


class CapabilityLevel(str, Enum):
    """Hierarchy level for capabilities."""
    L0 = "L0"  # Domain (e.g., "Sales", "Engineering", "Finance")
    L1 = "L1"  # Capability (e.g., "Lead Qualification", "CI/CD Pipeline")
    L2 = "L2"  # Sub-capability (e.g., "Lead Scoring", "Build Automation")


class CapabilityStatus(str, Enum):
    """Lifecycle status for capabilities."""
    ASSESSED = "assessed"
    DEVELOPING = "developing"
    MATURE = "mature"
    DEPRECATED = "deprecated"
    EMERGING = "emerging"


class MaturityLevel(int, Enum):
    """CMMI-inspired maturity levels."""
    INITIAL = 1       # Ad hoc, chaotic
    MANAGED = 2       # Repeatable, project-level
    DEFINED = 3       # Standardized, organization-wide
    QUANTIFIED = 4    # Measured, data-driven
    OPTIMIZING = 5    # Continuous improvement


class Capability(BaseModel):
    """A business capability — stable planning abstraction.

    Capabilities are independent of org charts, applications, or team
    structure. They represent *what the business does*, not *who does it*
    or *which tool does it*.

    Identity: name (normalized, case-insensitive) within tenant.
    Persistence: Neo4j node.
    """

    model_config = ConfigDict(extra="forbid", strict=True)

    id: str                              # ULID
    tenant_id: str                       # ULID
    name: str                            # e.g. "Lead Qualification"
    description: str = ""
    level: CapabilityLevel = CapabilityLevel.L1
    parent_id: Optional[str] = None      # ULID of parent capability (L0 for L1, L1 for L2)
    domain: str = ""                     # Business domain (e.g. "Sales", "Engineering")
    aliases: list[str] = Field(default_factory=list)  # Alternative names
    maturity_level: MaturityLevel = MaturityLevel.INITIAL
    maturity_score: float = 0.0          # Computed [0.0, 1.0] from evidence
    health_score: float = 0.0            # Computed [0.0, 1.0] from evidence
    investment_level: str = "none"       # none, low, medium, high
    owner_id: Optional[str] = None       # Stakeholder ULID
    status: CapabilityStatus = CapabilityStatus.ASSESSED
    source_refs: list[str] = Field(default_factory=list)
    created_at: str = ""
    updated_at: str = ""


class CapabilityRelationship(BaseModel):
    """A typed edge between two capabilities.

    Persistence: Neo4j edge.
    """

    model_config = ConfigDict(extra="forbid", strict=True)

    id: str                              # ULID
    source_id: str                       # ULID of source capability
    target_id: str                       # ULID of target capability
    relationship_type: CapabilityEdgeType
    strength: float = 1.0               # [0.0, 1.0] — dependency strength
    description: str = ""
    source_refs: list[str] = Field(default_factory=list)
    created_at: str = ""


class CapabilityEdgeType(str, Enum):
    """Semantic edge types between capabilities."""
    ENABLES = "ENABLES"                 # A enables B (A is prerequisite for B)
    DEPENDS_ON = "DEPENDS_ON"           # A depends on B (B must exist for A)
    CONFLICTS_WITH = "CONFLICTS_WITH"   # A and B compete for same resources
    INVESTED_IN = "INVESTED_IN"         # A project/investment targets this capability
    EVOLVES_TO = "EVOLVES_TO"          # A is evolving into B (roadmap)
    REPLACES = "REPLACES"              # A replaces B (succession)


class CapabilityEvidence(BaseModel):
    """Links an evidence record to a capability with relevance scoring.

    Persistence: Neo4j edge (EVIDENCE_LINKS_TO_CAPABILITY).
    """

    model_config = ConfigDict(extra="forbid", strict=True)

    evidence_id: str                     # ULID of EvidenceRecord
    capability_id: str                   # ULID of Capability
    relevance_score: float = 0.0         # [0.0, 1.0] — how relevant to capability
    mapping_method: str = "auto"         # auto, llm, manual, keyword
    mapped_by: str = "system"            # agent or stakeholder who mapped
    created_at: str = ""


class CapabilityScore(BaseModel):
    """Computed health/maturity/investment score for a capability.

    Persistence: Postgres (append-only, new computation supersedes old).
    """

    model_config = ConfigDict(extra="forbid", strict=True)

    id: str                              # ULID
    capability_id: str                   # ULID
    computed_at: str = ""                # ISO timestamp

    # Health dimensions
    health_score: float = 0.0            # [0.0, 1.0] overall health
    evidence_volume: int = 0             # count of linked evidence
    evidence_freshness: float = 0.0      # [0.0, 1.0] — recency of evidence
    evidence_sentiment: float = 0.0      # [-1.0, 1.0] — avg sentiment
    evidence_confidence: float = 0.0     # [0.0, 1.0] — avg confidence

    # Maturity dimensions
    maturity_level: MaturityLevel = MaturityLevel.INITIAL
    maturity_score: float = 0.0          # [0.0, 1.0] computed maturity
    process_standardization: float = 0.0 # [0.0, 1.0]
    measurement_coverage: float = 0.0    # [0.0, 1.0]
    improvement_activity: float = 0.0    # [0.0, 1.0]

    # Investment dimensions
    investment_level: str = "none"
    linked_projects: int = 0
    linked_requirements: int = 0
    linked_decisions: int = 0

    # Risk dimensions
    open_risks: int = 0
    open_conflicts: int = 0
    unresolved_issues: int = 0

    # Metadata
    weights_snapshot: dict = Field(default_factory=dict)
    computation_version: str = "1.0"
```

### 2.2 Capability Domain Map

The L0 → L1 → L2 hierarchy forms a **Capability Map** — the primary strategic planning view.

```
L0: Sales
├── L1: Lead Qualification
│   ├── L2: Lead Scoring
│   ├── L2: Lead Routing
│   └── L2: Qualification Criteria
├── L1: Proposal Generation
│   ├── L2: Template Management
│   ├── L2: Pricing Calculation
│   └── L2: Proposal Assembly
├── L1: Negotiation
│   ├── L2: Discount Authorization
│   └── L2: Contract Terms
└── L1: Close Deal
    ├── L2: Legal Review
    ├── L2: Signature Collection
    └── L2: Onboarding Handoff

L0: Engineering
├── L1: CI/CD Pipeline
│   ├── L2: Build Automation
│   ├── L2: Test Automation
│   └── L2: Deployment Automation
├── L1: Code Review
│   ├── L2: Review Assignment
│   ├── L2: Quality Gates
│   └── L2: Knowledge Sharing
├── L1: Monitoring
│   ├── L2: Alerting
│   ├── L2: Dashboards
│   └── L2: Incident Response
└── L1: Technical Debt Management
    ├── L2: Debt Identification
    ├── L2: Prioritization
    └── L2: Paydown Execution

L0: Finance
├── L1: Revenue Recognition
├── L1: Expense Management
├── L1: Financial Reporting
└── L1: Cash Flow Management

L0: People
├── L1: Hiring
├── L1: Onboarding
├── L1: Performance Management
└── L1: Retention
```

---

## 3. Relationship Definitions

### 3.1 Capability ↔ Capability Edges

| Edge Type | Source | Target | Meaning | Example |
|-----------|--------|--------|---------|---------|
| `ENABLES` | Capability A | Capability B | A is a prerequisite for B; B cannot function without A | CI/CD Pipeline **ENABLES** Deployment |
| `DEPENDS_ON` | Capability A | Capability B | A needs B to deliver value; B can exist without A | Lead Scoring **DEPENDS_ON** CRM Data Quality |
| `CONFLICTS_WITH` | Capability A | Capability B | A and B compete for same resources/time | Cost Optimization **CONFLICTS_WITH** Speed-to-Market |
| `INVESTED_IN` | Project | Capability | A project targets this capability | Project Alpha **INVESTED_IN** CI/CD Pipeline |
| `EVOLVES_TO` | Capability A | Capability B | A is being transformed into B | Manual Review **EVOLVES_TO** AI-Assisted Review |
| `REPLACES` | Capability A | Capability B | A is replacing B | New CRM **REPLACES** Legacy CRM |

### 3.2 Capability ↔ Entity Edges (extending V6 §2)

| Edge Type | Source | Target | Meaning |
|-----------|--------|--------|---------|
| `CAPABILITY_OWNED_BY` | Capability | Stakeholder | Who owns this capability |
| `CAPABILITY_MEASURED_BY` | Capability | KPI | KPIs that measure this capability |
| `CAPABILITY_GOVERNED_BY` | Capability | BusinessRule | Rules that govern this capability |
| `CAPABILITY_REQUIRED_BY` | Capability | Requirement | Requirements that require this capability |
| `CAPABILITY_AFFECTED_BY` | Capability | Risk | Risks that affect this capability |
| `EVIDENCE_LINKS_TO_CAPABILITY` | Evidence | Capability | Evidence relevant to this capability |
| `PROCESS_IMPLEMENTS` | Process | Capability | A process implements this capability |
| `SYSTEM_ENABLES` | System | Capability | A system enables this capability |

### 3.3 Capability ↔ Decision Edges

| Edge Type | Source | Target | Meaning |
|-----------|--------|--------|---------|
| `DECISION_TARGETS_CAPABILITY` | Decision | Capability | A decision targets improving this capability |
| `CAPABILITY_FEEDS_DECISION` | Capability | Decision | Evidence from this capability feeds a decision |
| `OPTION_IMPROVES` | Option | Capability | An option improves this capability |

---

## 4. Capability Reasoning Pattern

### 4.1 The Capability-First Pipeline

```
┌─────────────────────────────────────────────────────────────────┐
│                    CAPABILITY REASONING PIPELINE                 │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│  ┌──────────┐    ┌──────────────┐    ┌──────────────────┐      │
│  │ Evidence  │───▶│   Mapping    │───▶│  Capability      │      │
│  │ Ingest    │    │   Rules      │    │  Evidence Store   │      │
│  └──────────┘    └──────────────┘    └────────┬─────────┘      │
│                                               │                  │
│                                               ▼                  │
│                                    ┌──────────────────┐          │
│                                    │  Capability      │          │
│                                    │  Health Engine   │          │
│                                    └────────┬─────────┘          │
│                                             │                    │
│                        ┌────────────────────┼───────────┐       │
│                        ▼                    ▼           ▼       │
│              ┌──────────────┐   ┌──────────────┐ ┌──────────┐  │
│              │ Maturity     │   │ Gap          │ │ Risk     │  │
│              │ Assessment   │   │ Analysis     │ │ Analysis │  │
│              └──────┬───────┘   └──────┬───────┘ └────┬─────┘  │
│                     │                  │              │          │
│                     ▼                  ▼              ▼          │
│              ┌──────────────────────────────────────────────┐   │
│              │         Decision Framing Engine              │   │
│              │   "Invest in X" / "Restructure Y" /          │   │
│              │   "Deprecate Z" / "Merge A into B"           │   │
│              └──────────────────────┬───────────────────────┘   │
│                                     │                            │
│                                     ▼                            │
│              ┌──────────────────────────────────────────────┐   │
│              │         Feasibility Engine (existing)        │   │
│              │   Options scored against capability health   │   │
│              └──────────────────────┬───────────────────────┘   │
│                                     │                            │
│                                     ▼                            │
│              ┌──────────────────────────────────────────────┐   │
│              │         Artifact Engine (existing)           │   │
│              │   Artifacts generated at capability level    │   │
│              └──────────────────────────────────────────────┘   │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

### 4.2 Reasoning Steps

| Step | Agent/Stage | Input | Output | LLM? |
|------|------------|-------|--------|------|
| 1. **Map Evidence** | Mapping Agent | EvidenceRecord, CapabilityMap | CapabilityEvidence links | Yes (classification) |
| 2. **Score Capability** | Health Engine | CapabilityEvidence[], Capability | CapabilityScore | No (deterministic) |
| 3. **Assess Maturity** | Maturity Agent | CapabilityScore, Capability | MaturityLevel, gaps | Yes (gap analysis) |
| 4. **Find Gaps** | Gap Engine | CapabilityMap, CapabilityScores | GapReport | No (deterministic) |
| 5. **Frame Decisions** | Decision Agent | GapReport, CapabilityScores | DecisionOptions | Yes (option generation) |
| 6. **Score Options** | Feasibility Engine | Options, CapabilityScores | FeasibilityScores | No (existing) |
| 7. **Generate Artifacts** | Artifact Engine | CapabilityMap, Scores, Decisions | Artifacts | Partial (LLM augment) |

### 4.3 What Changes vs. Current V6

| Aspect | Current V6 | V6 + Capability Ontology |
|--------|-----------|--------------------------|
| **Primary unit** | Entity | Capability |
| **Evidence links** | Evidence → Entity | Evidence → Capability (+ Entity) |
| **Feasibility input** | Option dimensions | Option dimensions + Capability health |
| **Decision framing** | "Should we do X?" | "Should we invest in capability Y?" |
| **Artifact scope** | Per-entity or per-workspace | Per-capability or capability-family |
| **Gap analysis** | Missing entities in workspace | Missing/weak capabilities in domain |
| **Maturity tracking** | Not modeled | 5-level CMMI-inspired model |

---

## 5. Capability-Decision Bridge

### 5.1 Decision Framing Pattern

Every decision in V6 must be framed around capabilities:

```
Decision: "Invest in CI/CD Pipeline Automation"
  ├── Targets Capability: CI/CD Pipeline (L1)
  ├── Current Maturity: Level 2 (Managed)
  ├── Target Maturity: Level 4 (Quantified)
  ├── Gap: Test automation coverage at 45%, deployment manual
  ├── Options:
  │   ├── Option A: Invest in GitHub Actions (cost: $2K/mo)
  │   ├── Option B: Invest in GitLab CI (cost: $1.5K/mo)
  │   └── Option C: Do nothing (risk: maturity stays at L2)
  └── Evidence: 12 evidence records linked to CI/CD Pipeline capability
```

### 5.2 Capability → Decision Mapping Rules

| Rule | Trigger | Decision Frame |
|------|---------|---------------|
| **Invest** | Capability maturity < target AND evidence shows gap | "Invest in {capability} to reach maturity level {target}" |
| **Restructure** | Capability health declining AND ownership unclear | "Restructure {capability} — clarify ownership and process" |
| **Deprecate** | Capability maturity = L1 AND no evidence of use for 90d | "Deprecate {capability} — no active evidence of use" |
| **Merge** | Two capabilities have high overlap AND conflicting investment | "Merge {capability_a} into {capability_b}" |
| **Protect** | Capability health high AND risks identified | "Protect {capability} from identified risks" |
| **Scale** | Capability health high AND demand increasing | "Scale {capability} to meet growing demand" |

### 5.3 Capability-Scoped Feasibility

The existing 8-dimension feasibility model gets a 9th dimension when capabilities are involved:

```yaml
# Existing 8 dimensions (from V6_DOMAIN_SPEC §8.1)
dimensions:
  business_value: 0.25
  technical_complexity: 0.15
  operational_fit: 0.15
  financial_impact: 0.20
  compliance_risk: 0.10
  data_readiness: 0.05
  change_effort: 0.05
  stakeholder_alignment: 0.05

# New 9th dimension for capability-centric reasoning
  capability_maturity_lift:
    weight: 0.00  # Additional dimension, not weighted by default
    source: capability_health_engine
    scale: 0-100
    description: "How much does this option improve target capability maturity?"
    formula: "target_maturity_score - current_maturity_score × 100"
```

This dimension is **informational** (not weighted into the total by default) but provides critical context for capability-focused decisions.

---

## 6. Evidence → Capability Mapping Rules

### 6.1 Mapping Strategy (3-tier)

Evidence is mapped to capabilities through a 3-tier strategy, applied in order:

#### Tier 1: Keyword Matching (Deterministic)

```python
# config/capability_keywords.yaml
capability_keywords:
  "Lead Qualification":
    keywords: ["lead", "qualification", "scoring", "routing", "mql", "sql", "lead score"]
    source_types: ["connector", "chat"]
    confidence_boost: 0.1

  "CI/CD Pipeline":
    keywords: ["ci/cd", "pipeline", "build", "deploy", "deployment", "github actions", "gitlab ci", "jenkins"]
    source_types: ["connector", "chat"]
    confidence_boost: 0.1

  "Code Review":
    keywords: ["code review", "pull request", "pr review", "review process", "approve"]
    source_types: ["connector", "chat"]
    confidence_boost: 0.1

  "Revenue Recognition":
    keywords: ["revenue", "mrr", "arr", "billing", "invoice", "payment", "receivable"]
    source_types: ["connector", "spreadsheet"]
    confidence_boost: 0.1
```

**Rule:** If ≥2 keywords match AND source_type is in the capability's allowed list, create a `CapabilityEvidence` link with `relevance_score = keyword_match_ratio × confidence_boost`.

#### Tier 2: LLM Classification (Augmented)

When keyword matching produces ambiguous results (1 keyword match, or no keywords but entity-to-capability path exists), invoke the LLM classifier:

```
Given:
  - Evidence structured_data: {source_type, key fields}
  - Capability Map: {all L0/L1/L2 capabilities}
  - Existing entity-to-capability mappings

Classify: Which capability is this evidence MOST relevant to?
Return: {capability_id, relevance_score, reasoning}
```

**Rule:** LLM classification confidence must be ≥ 0.7 to create a link. Below 0.7 → flag for manual review.

#### Tier 3: Manual Tagging (Human-in-the-loop)

Stakeholders can manually tag evidence to capabilities via the UI or API:

```python
POST /api/capabilities/{capability_id}/evidence
{
  "evidence_id": "01H...",
  "relevance_score": 0.9,
  "notes": "This Slack message directly discusses our lead scoring process"
}
```

### 6.2 Mapping Pipeline Integration

The mapping happens at **Stage 6 (Entity/Relationship Build)** in the existing pipeline, after entities are resolved:

```
Stage 5: Alias Resolve → entity_refs populated
Stage 6: Entity/Relationship Build
  ├── Create entity nodes + edges (existing)
  └── NEW: Run capability mapping
      ├── Tier 1: Keyword match on structured_data
      ├── Tier 2: LLM classify ambiguous matches
      └── Create EVIDENCE_LINKS_TO_CAPABILITY edges
Stage 7: Conflict Scan (existing)
```

### 6.3 Mapping Confidence Propagation

```
evidence_to_capability_confidence = 
    evidence.confidence           # [0.0, 1.0] from parser
  × mapping_method_weight        # keyword=0.8, llm=0.7, manual=1.0
  × keyword_match_ratio          # [0.0, 1.0] (keyword tier only)
  × relevance_score              # [0.0, 1.0] from classifier

capability_evidence_confidence = 
    weighted_avg(all evidence_to_capability_confidences)
    where weight = 1 / (days_since_evidence_timestamp + 1)
```

---

## 7. Capability Maturity Model

### 7.1 Maturity Levels (CMMI-Inspired, Simplified)

| Level | Name | Description | Evidence Indicators |
|-------|------|-------------|-------------------|
| **L1** | Initial | Ad hoc, chaotic, hero-driven | Few/no processes documented; inconsistent execution; high variance |
| **L2** | Managed | Repeatable at project level | Some processes documented; consistent within team; basic metrics |
| **L3** | Defined | Standardized across organization | Processes standardized; org-wide adoption; documented playbooks |
| **L4** | Quantified | Measured and data-driven | KPIs tracked; data-driven decisions; performance benchmarked |
| **L5** | Optimizing | Continuous improvement | Feedback loops active; experiments running; proactive optimization |

### 7.2 Maturity Score Computation

The maturity score is computed from 4 dimensions, each [0.0, 1.0]:

```python
def compute_maturity_score(capability_id: str, evidence: list[Evidence]) -> CapabilityScore:
    """Compute maturity score from evidence analysis."""
    
    # Dimension 1: Process Standardization (0.25 weight)
    # How standardized are the processes for this capability?
    process_evidence = [e for e in evidence if e.source_type == "connector" and "process" in e.structured_data]
    process_standardization = len(process_evidence) / max_expected_process_evidence
    
    # Dimension 2: Measurement Coverage (0.25 weight)
    # How well is this capability measured (KPIs, metrics)?
    kpi_evidence = [e for e in evidence if "kpi" in e.structured_data or "metric" in e.structured_data]
    measurement_coverage = len(kpi_evidence) / max_expected_kpi_evidence
    
    # Dimension 3: Improvement Activity (0.25 weight)
    # Is there active improvement work (projects, experiments)?
    project_evidence = [e for e in evidence if "project" in e.structured_data or "sprint" in e.structured_data]
    improvement_activity = len(project_evidence) / max_expected_project_evidence
    
    # Dimension 4: Documentation Coverage (0.25 weight)
    # Is the capability documented (playbooks, runbooks, wikis)?
    doc_evidence = [e for e in evidence if e.source_type == "connector" and "doc" in e.structured_data]
    documentation_coverage = len(doc_evidence) / max_expected_doc_evidence
    
    # Weighted maturity score
    maturity_score = (
        0.25 * process_standardization +
        0.25 * measurement_coverage +
        0.25 * improvement_activity +
        0.25 * documentation_coverage
    )
    
    # Map score to maturity level
    if maturity_score < 0.2:
        maturity_level = MaturityLevel.INITIAL
    elif maturity_score < 0.4:
        maturity_level = MaturityLevel.MANAGED
    elif maturity_score < 0.6:
        maturity_level = MaturityLevel.DEFINED
    elif maturity_score < 0.8:
        maturity_level = MaturityLevel.QUANTIFIED
    else:
        maturity_level = MaturityLevel.OPTIMIZING
    
    return CapabilityScore(
        capability_id=capability_id,
        maturity_score=maturity_score,
        maturity_level=maturity_level,
        process_standardization=process_standardization,
        measurement_coverage=measurement_coverage,
        improvement_activity=improvement_activity,
        # ... other fields
    )
```

### 7.3 Maturity Assessment Triggers

| Trigger | Action |
|---------|--------|
| New evidence linked to capability | Recompute maturity score |
| Capability relationship changed | Recompute downstream maturity |
| Manual maturity override | Store override, flag for review |
| Quarterly review cycle | Batch recompute all capabilities |

---

## 8. Capability Health Assessment

### 8.1 Health Score Dimensions

```python
class CapabilityHealthDimensions:
    """Health score computed from 5 evidence-derived dimensions."""
    
    # 1. Evidence Volume (0.20 weight)
    # How much evidence supports this capability?
    # Normalized: min(evidence_count / 20, 1.0)
    
    # 2. Evidence Freshness (0.20 weight)
    # How recent is the evidence?
    # Normalized: avg(1 / (days_since_evidence + 1)) clamped to [0, 1]
    
    # 3. Evidence Sentiment (0.20 weight)
    # What's the overall sentiment of evidence about this capability?
    # Computed: VADER/NER sentiment averaged across evidence
    
    # 4. Evidence Confidence (0.20 weight)
    # How confident is the evidence?
    # Computed: weighted_avg(evidence.confidence) where weight = freshness
    
    # 5. Risk Exposure (0.20 weight, inverted)
    # How many open risks/conflicts affect this capability?
    # Computed: 1.0 - (open_risks + open_conflicts) / max_expected_risks
```

### 8.2 Health Score Formula

```python
def compute_health_score(
    evidence_volume: float,
    evidence_freshness: float,
    evidence_sentiment: float,  # [-1, 1] → normalized to [0, 1]
    evidence_confidence: float,
    risk_exposure: float,       # inverted: 1.0 = no risk
) -> float:
    """Compute capability health score [0.0, 1.0]."""
    normalized_sentiment = (evidence_sentiment + 1.0) / 2.0  # [-1,1] → [0,1]
    
    return (
        0.20 * evidence_volume +
        0.20 * evidence_freshness +
        0.20 * normalized_sentiment +
        0.20 * evidence_confidence +
        0.20 * risk_exposure
    )
```

### 8.3 Health Tiers

| Tier | Score Range | Action |
|------|-------------|--------|
| **Healthy** | 0.75–1.0 | Monitor; no action needed |
| **Attention** | 0.50–0.74 | Investigate; generate gap report |
| **At Risk** | 0.25–0.49 | Escalate; generate decision options |
| **Critical** | 0.00–0.24 | Immediate HITL review; block dependent decisions |

---

## 9. Graph Schema (Neo4j)

### 9.1 Node Types

```cypher
// Capability nodes
CREATE CONSTRAINT FOR (c:Capability) REQUIRE c.id IS UNIQUE;
CREATE INDEX FOR (c:Capability) ON (c.tenant_id, c.name);
CREATE INDEX FOR (c:Capability) ON (c.domain);
CREATE INDEX FOR (c:Capability) ON (c.level);

// Properties
(:Capability {
  id: ULID,
  tenant_id: ULID,
  name: String,
  description: String,
  level: String,          // "L0", "L1", "L2"
  parent_id: ULID,
  domain: String,
  aliases: [String],
  maturity_level: Int,    // 1-5
  maturity_score: Float,
  health_score: Float,
  investment_level: String,
  owner_id: ULID,
  status: String,
  created_at: DateTime,
  updated_at: DateTime
})
```

### 9.2 Edge Types

```cypher
// Capability ↔ Capability
(:Capability)-[:ENABLES {strength: Float}]->(:Capability)
(:Capability)-[:DEPENDS_ON {strength: Float}]->(:Capability)
(:Capability)-[:CONFLICTS_WITH]->(:Capability)
(:Capability)-[:EVOLVES_TO]->(:Capability)
(:Capability)-[:REPLACES]->(:Capability)

// Capability ↔ Entity (extending V6 §2)
(:Capability)-[:CAPABILITY_OWNED_BY {role: String}]->(:Stakeholder)
(:Capability)-[:CAPABILITY_MEASURED_BY {baseline: Float, target: Float}]->(:KPI)
(:Capability)-[:CAPABILITY_GOVERNED_BY]->(:BusinessRule)
(:Capability)-[:CAPABILITY_REQUIRED_BY]->(:Requirement)
(:Capability)-[:CAPABILITY_AFFECTED_BY {severity: String}]->(:Risk)

// Evidence ↔ Capability
(:Evidence)-[:EVIDENCE_LINKS_TO_CAPABILITY {
  relevance_score: Float,
  mapping_method: String,
  mapped_by: String
}]->(:Capability)

// Process ↔ Capability
(:Process)-[:PROCESS_IMPLEMENTS]->(:Capability)

// System ↔ Capability
(:System)-[:SYSTEM_ENABLES {criticality: String}]->(:Capability)

// Decision ↔ Capability
(:Decision)-[:DECISION_TARGETS_CAPABILITY]->(:Capability)
(:Capability)-[:CAPABILITY_FEEDS_DECISION]->(:Decision)
(:Option)-[:OPTION_IMPROVES]->(:Capability)

// Project ↔ Capability
(:Project)-[:INVESTED_IN]->(:Capability)
```

### 9.3 Key Queries

```cypher
// Get capability health for a domain
MATCH (c:Capability {domain: $domain, level: "L1"})
OPTIONAL MATCH (e:Evidence)-[r:EVIDENCE_LINKS_TO_CAPABILITY]->(c)
RETURN c.name, c.maturity_score, c.health_score,
       count(e) as evidence_count,
       avg(r.relevance_score) as avg_relevance
ORDER BY c.health_score ASC;

// Get capability dependency chain
MATCH path = (start:Capability {id: $capability_id})-[:DEPENDS_ON*1..5]->(dep:Capability)
RETURN path;

// Get evidence gap: capabilities with no evidence
MATCH (c:Capability {tenant_id: $tenant_id})
WHERE NOT EXISTS {
  MATCH (e:Evidence)-[:EVIDENCE_LINKS_TO_CAPABILITY]->(c)
}
RETURN c.name, c.domain, c.level;

// Get investment impact: how does a project affect capabilities?
MATCH (p:Project {id: $project_id})-[:INVESTED_IN]->(c:Capability)
OPTIONAL MATCH (c)-[:DEPENDS_ON*]->(dep:Capability)
RETURN c.name, c.maturity_score, collect(dep.name) as dependencies;

// Get capability map (L0 → L1 → L2)
MATCH (l0:Capability {level: "L0", tenant_id: $tenant_id})
OPTIONAL MATCH (l0)<-[:PARENT]-(l1:Capability {level: "L1"})
OPTIONAL MATCH (l1)<-[:PARENT]-(l2:Capability {level: "L2"})
RETURN l0.name, l1.name, l2.name
ORDER BY l0.name, l1.name, l2.name;
```

---

## 10. Integration with Existing V6 Pipeline

### 10.1 Pipeline Stage Modifications

| Stage | Current V6 | + Capability Ontology |
|-------|-----------|----------------------|
| **Stage 6: Entity/Relationship Build** | Create entity nodes + edges | + Create capability nodes (auto-inferred from domain keywords) |
| **Stage 6: Entity/Relationship Build** | — | + Run evidence → capability mapping (Tier 1-3) |
| **Stage 8: Graph Update** | Write entity/relationship edges | + Write capability edges (ENABLES, DEPENDS_ON, etc.) |
| **Stage 9: Gap Analysis** | Compare entity types vs workspace | + Compare capability maturity vs target |
| **Stage 10: Decision Analysis** | Generate options from evidence gaps | + Frame decisions around capability investment |
| **Stage 11: Feasibility Scoring** | 8-dimension scoring | + 9th dimension: capability_maturity_lift |
| **Stage 12: Artifact Projection** | Per-entity/workspace artifacts | + Capability-level artifact sections |

### 10.2 New Pipeline Stage: Capability Health Computation

Insert after Stage 8 (Graph Update), before Stage 9 (Gap Analysis):

```
Stage 8: Graph Update (existing)
Stage 8.5: Capability Health Computation (NEW)
  ├── For each capability with new evidence:
  │   ├── Compute health_score (5 dimensions)
  │   ├── Compute maturity_score (4 dimensions)
  │   ├── Update CapabilityScore (append-only)
  │   └── Emit CapabilityHealthUpdated event
  └── Trigger downstream: Gap Analysis gets fresh scores
Stage 9: Gap Analysis (existing, enhanced with capability gaps)
```

### 10.3 New Event: CapabilityHealthUpdated

```python
@dataclass
class CapabilityHealthUpdated:
    """Emitted when a capability's health/maturity score changes."""
    capability_id: str
    tenant_id: str
    old_health_score: float
    new_health_score: float
    old_maturity_level: int
    new_maturity_level: int
    evidence_delta: int          # change in evidence count
    computed_at: str
```

### 10.4 Context Model Extension

Add a new layer to the context assembly (§10.1):

```
Layer 1:  Tenant Context
Layer 2:  Workspace Context
Layer 3:  Stakeholder Context
Layer 4:  Evidence Slice
Layer 5:  Knowledge Slice
Layer 5.5: Capability Slice (NEW)  ← capability map + health scores
Layer 6:  Decision Slice
Layer 7:  Artifact Slice
Layer 8:  Policy Slice
```

**Capability Slice** contains:
- Full capability map (L0 → L1 → L2)
- Health scores for all capabilities in workspace scope
- Maturity levels and trends
- Open risks/conflicts per capability
- Investment levels

Budget: ~2,000 tokens (capability map is compact)

---

## 11. ADR-013: Capability-Centric Reasoning

**Status:** Proposed

**Context:** V6's evidence-first architecture (ADR-008) ensures full traceability from artifact to raw evidence. However, the reasoning chain (Evidence → Entity → Decision → Artifact) is entity-centric, which is suboptimal for strategic planning. Strategic decisions are about *business capabilities* — "Should we invest in our CI/CD pipeline?" — not *entities* — "Should we act on this Slack message about CI/CD?" The current architecture forces decision-makers to mentally bridge the gap between entity-level evidence and capability-level strategy.

**Decision:** Introduce a **Capability Ontology** as the primary unit of business reasoning. Evidence maps to capabilities (in addition to entities). Feasibility analysis incorporates capability health. Artifacts are generated at the capability level. Decisions are framed as capability investments.

**Alternatives Considered:**

1. **Keep entity-centric reasoning, add capability views as artifacts.** Simpler — just add a "Capability Map" artifact type that aggregates entity data. But this doesn't change the reasoning chain; capabilities remain a projection, not a first-class concept. Decisions still aren't framed around capabilities.

2. **Replace entities with capabilities entirely.** Radical — remove entity types and reason only on capabilities. But entities provide essential granularity for evidence resolution, conflict detection, and traceability. Capabilities are too coarse for dedup and merge.

3. **Hybrid: Entities for evidence resolution, Capabilities for reasoning.** (Chosen) Keep the entity model for evidence ingestion and resolution. Add capabilities as a reasoning layer on top. Evidence links to both entities (for traceability) and capabilities (for business reasoning).

**Consequences:**

- Positive: Decisions are naturally framed as capability investments — executives understand this language.
- Positive: Maturity tracking gives a quantitative view of organizational capability over time.
- Positive: Gap analysis identifies *which capabilities* need investment, not just *which entities* are missing.
- Positive: Artifacts become capability-centric reports (capability maps, maturity assessments) — more useful for strategic planning.
- Negative: Increased complexity — evidence now links to both entities and capabilities.
- Negative: Mapping rules need tuning — incorrect evidence→capability mapping produces misleading maturity scores.
- Negative: New pipeline stage (8.5) adds latency (~500ms per capability recomputation).
- Negative: Capability map must be seeded/maintained — either auto-inferred or manually curated.

---

## 12. Example: Mockoon Data Mapping

### 12.1 Mockoon Data Sources

The 4 MVP connectors (ADR-010) produce evidence from:

| Source | Type | Example Evidence |
|--------|------|-----------------|
| **Notion** | connector | Product wiki pages, sprint retros, architecture docs |
| **Slack** | chat | Channel discussions, thread decisions, @mentions |
| **Jira/Linear** | connector | Tickets, stories, bugs, acceptance criteria |
| **Salesforce** | connector | Opportunities, contacts, pipeline stages |

### 12.2 Example Evidence Records → Capability Mapping

#### Evidence Record 1: Notion Page

```yaml
Evidence:
  id: "01H8X9..."
  source: "notion"
  source_type: "connector"
  structured_data:
    database_id: "sprint-retro-2026"
    title: "Sprint 42 Retrospective"
    properties:
      sprint_number: 42
      team: "Platform"
      deployment_failures: 3
      lead_time_days: 4.5
      notes: "CI pipeline flaky, need to invest in test isolation"
  confidence: 0.95
```

**Capability Mapping:**
- Tier 1 keyword match: "CI pipeline", "test isolation" → **CI/CD Pipeline** (L1)
- Relevance score: 0.92
- Mapping method: keyword

#### Evidence Record 2: Slack Message

```yaml
Evidence:
  id: "01H8Y2..."
  source: "slack"
  source_type: "chat"
  structured_data:
    channel_id: "C-SALES-OPS"
    sender: "sarah@company.com"
    text: "Deal with Acme Corp stuck in legal review for 2 weeks. Need faster contract turnaround."
    reactions: ["👍", "🔍"]
  confidence: 0.88
```

**Capability Mapping:**
- Tier 1 keyword match: "legal review", "contract turnaround" → **Close Deal** (L1)
- Relevance score: 0.85
- Mapping method: keyword

#### Evidence Record 3: Jira Ticket

```yaml
Evidence:
  id: "01H8Z1..."
  source: "jira"
  source_type: "connector"
  structured_data:
    external_id: "ENG-1234"
    title: "Implement automated lead scoring"
    status: "in_progress"
    priority: "high"
    acceptance_criteria:
      - "Leads scored automatically based on engagement"
      - "Score visible in CRM dashboard"
      - "Manual override available"
  confidence: 0.97
```

**Capability Mapping:**
- Tier 1 keyword match: "lead scoring", "leads scored" → **Lead Scoring** (L2, under Lead Qualification)
- Relevance score: 0.95
- Mapping method: keyword

#### Evidence Record 4: Salesforce Opportunity

```yaml
Evidence:
  id: "01H9A1..."
  source: "salesforce"
  source_type: "connector"
  structured_data:
    external_id: "SF-OPP-5678"
    account: "Acme Corp"
    stage: "Negotiation"
    amount: 125000
    close_date: "2026-08-30"
    next_step: "Legal review pending"
  confidence: 0.99
```

**Capability Mapping:**
- Tier 1 keyword match: "Negotiation", "Legal review" → **Negotiation** (L1) + **Close Deal** (L1)
- Relevance score: 0.88 (Negotiation), 0.82 (Close Deal)
- Mapping method: keyword

### 12.3 Capability Health After Mapping

```
Capability: CI/CD Pipeline (L1, Engineering)
  ├── Evidence: 8 records (3 Notion, 3 Slack, 2 Jira)
  ├── Health Score: 0.42 (At Risk)
  │   ├── Evidence Volume: 0.40 (8/20 normalized)
  │   ├── Evidence Freshness: 0.55 (avg 3.2 days old)
  │   ├── Evidence Sentiment: 0.20 (mixed — flaky pipeline concerns)
  │   ├── Evidence Confidence: 0.93 (high quality sources)
  │   └── Risk Exposure: 0.30 (2 open risks)
  ├── Maturity Level: L2 (Managed)
  │   ├── Process Standardization: 0.35 (some docs, inconsistent)
  │   ├── Measurement Coverage: 0.45 (lead time tracked, not failure rate)
  │   ├── Improvement Activity: 0.50 (ENG-1234 in progress)
  │   └── Documentation Coverage: 0.30 (partial runbooks)
  └── Investment Level: medium (1 active project)

Capability: Lead Qualification (L1, Sales)
  ├── Evidence: 5 records (2 Notion, 1 Slack, 2 Jira)
  ├── Health Score: 0.68 (Attention)
  ├── Maturity Level: L2 (Managed)
  └── Investment Level: high (2 active projects)

Capability: Close Deal (L1, Sales)
  ├── Evidence: 6 records (1 Notion, 2 Slack, 1 Jira, 2 Salesforce)
  ├── Health Score: 0.55 (Attention)
  ├── Maturity Level: L2 (Managed)
  └── Investment Level: low

Capability: Negotiation (L1, Sales)
  ├── Evidence: 4 records (1 Slack, 1 Jira, 2 Salesforce)
  ├── Health Score: 0.72 (Attention)
  ├── Maturity Level: L3 (Defined)
  └── Investment Level: low
```

### 12.4 Decision Framing from Capability Analysis

```
Decision: "Invest in CI/CD Pipeline Test Automation"
  ├── Targets: CI/CD Pipeline (L1)
  ├── Current Maturity: L2 (Managed)
  ├── Target Maturity: L4 (Quantified)
  ├── Gap: Test automation coverage at 45%, deployment manual
  ├── Evidence: 8 records (sentiment: mixed, confidence: high)
  ├── Options:
  │   ├── Option A: GitHub Actions + test isolation investment
  │   │   ├── Feasibility: 72/100 (Caveats tier)
  │   │   ├── Capability Maturity Lift: +15 points
  │   │   └── Cost: $2K/mo + 2 engineer-months
  │   ├── Option B: GitLab CI migration
  │   │   ├── Feasibility: 65/100 (Review tier)
  │   │   ├── Capability Maturity Lift: +12 points
  │   │   └── Cost: $1.5K/mo + 4 engineer-months
  │   └── Option C: Do nothing
  │       ├── Feasibility: N/A
  │       ├── Capability Maturity Lift: 0 points
  │       └── Risk: Maturity stays at L2, deployment failures continue
  └── Recommendation: Option A (highest maturity lift per dollar)
```

### 12.5 Artifact: Capability Map (Current-State Pack)

The existing "Current-State Pack" artifact (V6 §6.2.4) gets a new section:

```yaml
# Extended artifact config for capability-aware Current-State Pack
sections:
  # ... existing sections ...

  - name: "Capability Health Matrix"
    type: table
    source: "capabilities.health_matrix"
    config:
      columns: [capability, domain, level, maturity, health, evidence_count, investment, risks]
      sort_by: health
      min_evidence: 1
    llm_augment: false  # deterministic from scores

  - name: "Capability Dependency Map"
    type: diagram_placeholder
    source: "capabilities.dependency_graph"
    config:
      diagram_type: "capability_map"
      show_evidence_links: true
      highlight_at_risk: true
    llm_augment: true  # LLM narrates dependency implications

  - name: "Investment Recommendations"
    type: recommendation_list
    source: "capabilities.gap_analysis"
    llm_augment: true
```

---

## Appendix A: Pydantic Model Summary

| Model | Purpose | Persistence | Key Fields |
|-------|---------|-------------|------------|
| `Capability` | Business capability entity | Neo4j node | id, name, level, domain, maturity_score, health_score |
| `CapabilityRelationship` | Typed edge between capabilities | Neo4j edge | source_id, target_id, relationship_type, strength |
| `CapabilityEvidence` | Evidence → capability link | Neo4j edge | evidence_id, capability_id, relevance_score, mapping_method |
| `CapabilityScore` | Computed health/maturity/investment | Postgres (append-only) | capability_id, health_score, maturity_level, maturity_score |

## Appendix B: Configuration Files

| File | Purpose |
|------|---------|
| `config/capability_keywords.yaml` | Keyword → capability mapping rules |
| `config/capability_weights.yaml` | Health/maturity dimension weights |
| `config/capability_domains.yaml` | L0 domain definitions |
| `config/capability_templates.yaml` | Default capability hierarchies per domain |

## Appendix C: Migration Path

1. **Phase 1 (MVP):** Add `Capability` entity + `EVIDENCE_LINKS_TO_CAPABILITY` edge. Auto-infer capabilities from domain keywords. Compute health scores deterministically.

2. **Phase 2:** Add LLM-based capability classification. Add maturity tracking. Extend artifact DSL with capability sections.

3. **Phase 3:** Add capability-decision bridge. Frame all decisions as capability investments. Add capability-scoped feasibility dimension.

---

*End of Capability Ontology Design*

# ADR-006: Knowledge Catalog Schema for OntologyAI V6

**Status:** Proposed  
**Date:** 2026-08-04  
**Deciders:** Architecture Team  
**Technical Story:** Design a Knowledge Catalog that indexes ALL enterprise knowledge artifacts across 10 categories, enabling unified search, navigation, and relationship traversal.

---

## Context

### Problem Statement

The platform currently has 24 entity types, 4 connectors producing evidence, and a Decision Intelligence pipeline (feasibility + validation + artifacts). However, there is no unified index that allows users to:

1. Browse all enterprise knowledge by category
2. Search across disparate entity types with a single query
3. Traverse relationships between capabilities, decisions, systems, and stakeholders
4. Understand the provenance and confidence of any knowledge artifact
5. Navigate from a high-level business capability down to the raw evidence that supports it

### Current State

The existing schema (migration 004_v6_entities.sql) defines tables for:
- **workspaces** / **decision_workspaces** — workspace containers
- **sources** — evidence-producing connectors
- **stakeholders** — people and roles
- **org_units** — organizational hierarchy
- **systems** — technical systems
- **constraints** — business constraints
- **kpis** — key performance indicators
- **projects** — active and completed projects
- **artifacts** / **artifact_versions** — generated documents
- **validation_results** / **feasibility_scores** — decision intelligence
- **audit_events** — audit trail
- **policies** — rules and compliance
- **enterprise_knowledge** — interpreted business state
- **entity_confidence** — confidence scores from evidence

The existing ontology layer (object_types.py, link_types.py) defines 7 canonical Object Types and 11 semantic links. The governance layer (governance.py) enforces HITL approval for consequential writes.

### Gap Analysis

The existing tables are **operational** — they store the current state of each entity type. What's missing is a **catalog layer** that:

1. Provides a unified search index across all entity types
2. Tracks relationships between categories (not just between objects of the same type)
3. Manages lifecycle transitions with version history
4. Enforces access control at the category level
5. Supports faceted navigation (browse by category, filter by capability/stakeholder/date/confidence)

---

## Decision

### Architecture: Separate Catalog Tables

We add **catalog-specific tables** that complement (not replace) the existing operational tables. The catalog is a **read-optimized, search-oriented projection** of the operational data.

**Rationale:**
- Operational tables (workspaces, projects, etc.) serve transactional workloads
- Catalog tables serve search, navigation, and analytics workloads
- Separation allows independent scaling and indexing strategies
- Catalog can be rebuilt from operational tables (eventual consistency)

---

## Entity Schemas for All 10 Categories

### 1. Capabilities

Business capabilities and their maturity levels.

```sql
CREATE TABLE IF NOT EXISTS catalog_capabilities (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id       TEXT NOT NULL,
    name            TEXT NOT NULL,
    description     TEXT,
    maturity_level  TEXT NOT NULL DEFAULT 'initial'
        CHECK (maturity_level IN ('initial', 'developing', 'defined', 'managed', 'optimizing')),
    status          TEXT NOT NULL DEFAULT 'draft'
        CHECK (status IN ('draft', 'active', 'archived', 'deprecated')),
    owner_id        UUID REFERENCES stakeholders(id) ON DELETE SET NULL,
    parent_id       UUID REFERENCES catalog_capabilities(id) ON DELETE SET NULL,
    domain          TEXT,                    -- business domain (e.g., 'Sales', 'Finance', 'Operations')
    tags            JSONB NOT NULL DEFAULT '[]'::jsonb,
    confidence      REAL NOT NULL DEFAULT 0.0 CHECK (confidence >= 0 AND confidence <= 1),
    evidence_ids    JSONB NOT NULL DEFAULT '[]'::jsonb,  -- links to evidence records
    metadata        JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    created_by      TEXT,
    updated_by      TEXT,
    version         INT NOT NULL DEFAULT 1
);

CREATE INDEX IF NOT EXISTS idx_catalog_caps_tenant ON catalog_capabilities(tenant_id);
CREATE INDEX IF NOT EXISTS idx_catalog_caps_status ON catalog_capabilities(status);
CREATE INDEX IF NOT EXISTS idx_catalog_caps_domain ON catalog_capabilities(domain);
CREATE INDEX IF NOT EXISTS idx_catalog_caps_maturity ON catalog_capabilities(maturity_level);
CREATE INDEX IF NOT EXISTS idx_catalog_caps_owner ON catalog_capabilities(owner_id);
CREATE INDEX IF NOT EXISTS idx_catalog_caps_parent ON catalog_capabilities(parent_id);
CREATE INDEX IF NOT EXISTS idx_catalog_caps_gin_tags ON catalog_capabilities USING GIN(tags);
```

**Query Patterns:**
- "What capabilities do we have in the Sales domain?" → `WHERE domain = 'Sales'`
- "Which capabilities are at Maturity Level 3 or higher?" → `WHERE maturity_level IN ('defined','managed','optimizing')`
- "Who owns the Authentication capability?" → Join with stakeholders
- "What capabilities depend on the CRM system?" → Through `catalog_capability_system_links`

### 2. Decisions

Past and pending decisions with evidence chains.

```sql
CREATE TABLE IF NOT EXISTS catalog_decisions (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id       TEXT NOT NULL,
    title           TEXT NOT NULL,
    description     TEXT,
    decision_type   TEXT NOT NULL  -- 'strategic', 'tactical', 'operational', 'technical'
        CHECK (decision_type IN ('strategic', 'tactical', 'operational', 'technical')),
    status          TEXT NOT NULL DEFAULT 'proposed'
        CHECK (status IN ('proposed', 'in_review', 'approved', 'rejected', 'implemented', 'superseded', 'archived')),
    decision_date   TIMESTAMPTZ,
    owner_id        UUID REFERENCES stakeholders(id) ON DELETE SET NULL,
    workspace_id    TEXT REFERENCES workspaces(id) ON DELETE SET NULL,
    rationale       TEXT,
    alternatives    JSONB NOT NULL DEFAULT '[]'::jsonb,  -- list of alternatives considered
    outcome         TEXT,                               -- actual outcome after implementation
    confidence      REAL NOT NULL DEFAULT 0.0 CHECK (confidence >= 0 AND confidence <= 1),
    evidence_ids    JSONB NOT NULL DEFAULT '[]'::jsonb,
    impact_score    REAL,                              -- 0-1 scale
    tags            JSONB NOT NULL DEFAULT '[]'::jsonb,
    metadata        JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    created_by      TEXT,
    updated_by      TEXT,
    version         INT NOT NULL DEFAULT 1
);

CREATE INDEX IF NOT EXISTS idx_catalog_decisions_tenant ON catalog_decisions(tenant_id);
CREATE INDEX IF NOT EXISTS idx_catalog_decisions_status ON catalog_decisions(status);
CREATE INDEX IF NOT EXISTS idx_catalog_decisions_type ON catalog_decisions(decision_type);
CREATE INDEX IF NOT EXISTS idx_catalog_decisions_date ON catalog_decisions(decision_date);
CREATE INDEX IF NOT EXISTS idx_catalog_decisions_owner ON catalog_decisions(owner_id);
CREATE INDEX IF NOT EXISTS idx_catalog_decisions_workspace ON catalog_decisions(workspace_id);
```

**Query Patterns:**
- "What decisions were made about our sales capability this quarter?" → Join with `catalog_decision_capability_links` + date filter
- "Show me all decisions approved by Sarah" → `WHERE owner_id = ? AND status = 'approved'`
- "What's the evidence chain for the pricing decision?" → Through `catalog_decision_evidence_links`
- "What decisions are pending review?" → `WHERE status = 'in_review'`

### 3. Processes

Business processes and their documentation.

```sql
CREATE TABLE IF NOT EXISTS catalog_processes (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id       TEXT NOT NULL,
    name            TEXT NOT NULL,
    description     TEXT,
    process_type    TEXT NOT NULL  -- 'core', 'support', 'management'
        CHECK (process_type IN ('core', 'support', 'management')),
    status          TEXT NOT NULL DEFAULT 'draft'
        CHECK (status IN ('draft', 'active', 'archived', 'deprecated')),
    owner_id        UUID REFERENCES stakeholders(id) ON DELETE SET NULL,
    frequency       TEXT,           -- 'daily', 'weekly', 'monthly', 'ad_hoc', 'continuous'
    inputs          JSONB NOT NULL DEFAULT '[]'::jsonb,   -- list of input artifacts/capabilities
    outputs         JSONB NOT NULL DEFAULT '[]'::jsonb,   -- list of output artifacts/capabilities
    steps           JSONB NOT NULL DEFAULT '[]'::jsonb,   -- ordered list of process steps
    documentation_url TEXT,
    confidence      REAL NOT NULL DEFAULT 0.0 CHECK (confidence >= 0 AND confidence <= 1),
    evidence_ids    JSONB NOT NULL DEFAULT '[]'::jsonb,
    tags            JSONB NOT NULL DEFAULT '[]'::jsonb,
    metadata        JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    created_by      TEXT,
    updated_by      TEXT,
    version         INT NOT NULL DEFAULT 1
);

CREATE INDEX IF NOT EXISTS idx_catalog_processes_tenant ON catalog_processes(tenant_id);
CREATE INDEX IF NOT EXISTS idx_catalog_processes_status ON catalog_processes(status);
CREATE INDEX IF NOT EXISTS idx_catalog_processes_type ON catalog_processes(process_type);
CREATE INDEX IF NOT EXISTS idx_catalog_processes_owner ON catalog_processes(owner_id);
```

**Query Patterns:**
- "What processes support the Order Fulfillment capability?" → Join with `catalog_process_capability_links`
- "Which processes are documented but not yet active?" → `WHERE status = 'draft' AND documentation_url IS NOT NULL`
- "What are the inputs to the Invoice Processing process?" → `SELECT inputs FROM catalog_processes WHERE name = 'Invoice Processing'`

### 4. Policies

Rules, regulations, standards, compliance requirements.

```sql
CREATE TABLE IF NOT EXISTS catalog_policies (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id       TEXT NOT NULL,
    name            TEXT NOT NULL,
    description     TEXT,
    policy_type     TEXT NOT NULL  -- 'regulation', 'standard', 'guideline', 'constraint'
        CHECK (policy_type IN ('regulation', 'standard', 'guideline', 'constraint')),
    severity        TEXT NOT NULL DEFAULT 'block'
        CHECK (severity IN ('block', 'warn', 'info')),
    status          TEXT NOT NULL DEFAULT 'active'
        CHECK (status IN ('draft', 'active', 'superseded', 'deprecated', 'archived')),
    owner_id        UUID REFERENCES stakeholders(id) ON DELETE SET NULL,
    effective_date  TIMESTAMPTZ,
    expiry_date     TIMESTAMPTZ,
    rule_expression TEXT NOT NULL,            -- machine-readable rule
    applies_to      JSONB NOT NULL DEFAULT '[]'::jsonb,  -- list of entity types/capabilities this applies to
    enforcement     TEXT NOT NULL DEFAULT 'mandatory'
        CHECK (enforcement IN ('mandatory', 'advisory', 'optional')),
    source_ref      TEXT,                     -- link to external regulation/standard
    confidence      REAL NOT NULL DEFAULT 0.0 CHECK (confidence >= 0 AND confidence <= 1),
    evidence_ids    JSONB NOT NULL DEFAULT '[]'::jsonb,
    tags            JSONB NOT NULL DEFAULT '[]'::jsonb,
    metadata        JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    created_by      TEXT,
    updated_by      TEXT,
    version         INT NOT NULL DEFAULT 1
);

CREATE INDEX IF NOT EXISTS idx_catalog_policies_tenant ON catalog_policies(tenant_id);
CREATE INDEX IF NOT EXISTS idx_catalog_policies_status ON catalog_policies(status);
CREATE INDEX IF NOT EXISTS idx_catalog_policies_type ON catalog_policies(policy_type);
CREATE INDEX IF NOT EXISTS idx_catalog_policies_severity ON catalog_policies(severity);
CREATE INDEX IF NOT EXISTS idx_catalog_policies_owner ON catalog_policies(owner_id);
CREATE INDEX IF NOT EXISTS idx_catalog_policies_gin_applies ON catalog_policies USING GIN(applies_to);
```

**Query Patterns:**
- "What policies apply to our data processing pipeline?" → `WHERE applies_to @> '["data_processing"]'`
- "Which regulations are expiring this quarter?" → `WHERE expiry_date BETWEEN ? AND ?`
- "What block-level policies affect the Finance domain?" → `WHERE severity = 'block' AND applies_to @> '["finance"]'`
- "Show me all mandatory policies" → `WHERE enforcement = 'mandatory'`

### 5. Risks

Identified risks, their mitigation status, owners.

```sql
CREATE TABLE IF NOT EXISTS catalog_risks (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id       TEXT NOT NULL,
    title           TEXT NOT NULL,
    description     TEXT,
    risk_category   TEXT NOT NULL  -- 'strategic', 'operational', 'financial', 'technical', 'compliance'
        CHECK (risk_category IN ('strategic', 'operational', 'financial', 'technical', 'compliance')),
    likelihood      TEXT NOT NULL DEFAULT 'medium'
        CHECK (likelihood IN ('low', 'medium', 'high', 'very_high')),
    impact          TEXT NOT NULL DEFAULT 'medium'
        CHECK (impact IN ('low', 'medium', 'high', 'critical')),
    risk_score      REAL NOT NULL DEFAULT 0.0,  -- computed: likelihood * impact
    status          TEXT NOT NULL DEFAULT 'identified'
        CHECK (status IN ('identified', 'assessed', 'mitigating', 'mitigated', 'accepted', 'closed', 'realized')),
    owner_id        UUID REFERENCES stakeholders(id) ON DELETE SET NULL,
    mitigation_plan TEXT,
    mitigation_status TEXT
        CHECK (mitigation_status IN ('planned', 'in_progress', 'completed', 'not_required')),
    target_close_date TIMESTAMPTZ,
    actual_close_date TIMESTAMPTZ,
    related_capability_ids JSONB NOT NULL DEFAULT '[]'::jsonb,
    related_project_ids   JSONB NOT NULL DEFAULT '[]'::jsonb,
    confidence      REAL NOT NULL DEFAULT 0.0 CHECK (confidence >= 0 AND confidence <= 1),
    evidence_ids    JSONB NOT NULL DEFAULT '[]'::jsonb,
    tags            JSONB NOT NULL DEFAULT '[]'::jsonb,
    metadata        JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    created_by      TEXT,
    updated_by      TEXT,
    version         INT NOT NULL DEFAULT 1
);

CREATE INDEX IF NOT EXISTS idx_catalog_risks_tenant ON catalog_risks(tenant_id);
CREATE INDEX IF NOT EXISTS idx_catalog_risks_status ON catalog_risks(status);
CREATE INDEX IF NOT EXISTS idx_catalog_risks_category ON catalog_risks(risk_category);
CREATE INDEX IF NOT EXISTS idx_catalog_risks_owner ON catalog_risks(owner_id);
CREATE INDEX IF NOT EXISTS idx_catalog_risks_score ON catalog_risks(risk_score);
```

**Query Patterns:**
- "Show me all evidence supporting the risk that GlobalTech might churn" → Through `catalog_risk_evidence_links`
- "What are the top 5 risks by score?" → `ORDER BY risk_score DESC LIMIT 5`
- "Which risks are mitigating but not yet completed?" → `WHERE status = 'mitigating' AND mitigation_status = 'in_progress'`
- "What risks affect the Customer Portal project?" → `WHERE related_project_ids @> '["project-id"]'`

### 6. Artifacts

Generated documents, reports, briefs, analyses.

```sql
CREATE TABLE IF NOT EXISTS catalog_artifacts (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id       TEXT NOT NULL,
    name            TEXT NOT NULL,
    description     TEXT,
    artifact_category TEXT NOT NULL  -- 'report', 'brief', 'analysis', 'spec', 'diagram', 'contract', 'policy_doc'
        CHECK (artifact_category IN ('report', 'brief', 'analysis', 'spec', 'diagram', 'contract', 'policy_doc', 'other')),
    artifact_type   TEXT,            -- specific type (e.g., 'investor_update', 'risk_analysis', 'current_state')
    status          TEXT NOT NULL DEFAULT 'draft'
        CHECK (status IN ('draft', 'review', 'published', 'superseded', 'archived')),
    workspace_id    TEXT REFERENCES workspaces(id) ON DELETE SET NULL,
    owner_id        UUID REFERENCES stakeholders(id) ON DELETE SET NULL,
    project_id      UUID REFERENCES projects(id) ON DELETE SET NULL,
    content_ref     TEXT,            -- pointer to content storage (S3, etc.)
    content_hash    TEXT,            -- for deduplication
    format          TEXT,            -- 'markdown', 'html', 'pdf', 'json', 'yaml'
    producer        TEXT,            -- workflow/agent that produced this
    confidence      REAL NOT NULL DEFAULT 0.0 CHECK (confidence >= 0 AND confidence <= 1),
    evidence_ids    JSONB NOT NULL DEFAULT '[]'::jsonb,
    tags            JSONB NOT NULL DEFAULT '[]'::jsonb,
    metadata        JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    created_by      TEXT,
    updated_by      TEXT,
    version         INT NOT NULL DEFAULT 1
);

CREATE INDEX IF NOT EXISTS idx_catalog_artifacts_tenant ON catalog_artifacts(tenant_id);
CREATE INDEX IF NOT EXISTS idx_catalog_artifacts_status ON catalog_artifacts(status);
CREATE INDEX IF NOT EXISTS idx_catalog_artifacts_category ON catalog_artifacts(artifact_category);
CREATE INDEX IF NOT EXISTS idx_catalog_artifacts_type ON catalog_artifacts(artifact_type);
CREATE INDEX IF NOT EXISTS idx_catalog_artifacts_workspace ON catalog_artifacts(workspace_id);
CREATE INDEX IF NOT EXISTS idx_catalog_artifacts_project ON catalog_artifacts(project_id);
CREATE INDEX IF NOT EXISTS idx_catalog_artifacts_owner ON catalog_artifacts(owner_id);
```

**Query Patterns:**
- "What artifacts were generated for the Customer Portal project?" → `WHERE project_id = ?`
- "Show me all risk analyses published this month" → `WHERE artifact_type = 'risk_analysis' AND status = 'published' AND created_at >= ?`
- "Which artifacts are superseded?" → `WHERE status = 'superseded'`
- "What did the StrategyWorkflow produce?" → `WHERE producer = 'StrategyWorkflow'`

### 7. Stakeholders

People, roles, responsibilities, expertise areas.

```sql
CREATE TABLE IF NOT EXISTS catalog_stakeholders (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id       TEXT NOT NULL,
    name            TEXT NOT NULL,
    email           TEXT,
    role            TEXT,
    department      TEXT,
    expertise_areas JSONB NOT NULL DEFAULT '[]'::jsonb,  -- list of capability domains
    responsibility_areas JSONB NOT NULL DEFAULT '[]'::jsonb,  -- list of entity types/capabilities
    status          TEXT NOT NULL DEFAULT 'active'
        CHECK (status IN ('active', 'inactive', 'on_leave', 'departed')),
    org_unit_id     UUID REFERENCES org_units(id) ON DELETE SET NULL,
    confidence      REAL NOT NULL DEFAULT 1.0 CHECK (confidence >= 0 AND confidence <= 1),
    metadata        JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    created_by      TEXT,
    updated_by      TEXT,
    version         INT NOT NULL DEFAULT 1
);

CREATE INDEX IF NOT EXISTS idx_catalog_stakeholders_tenant ON catalog_stakeholders(tenant_id);
CREATE INDEX IF NOT EXISTS idx_catalog_stakeholders_status ON catalog_stakeholders(status);
CREATE INDEX IF NOT EXISTS idx_catalog_stakeholders_role ON catalog_stakeholders(role);
CREATE INDEX IF NOT EXISTS idx_catalog_stakeholders_org ON catalog_stakeholders(org_unit_id);
CREATE INDEX IF NOT EXISTS idx_catalog_stakeholders_gin_expertise ON catalog_stakeholders USING GIN(expertise_areas);
```

**Query Patterns:**
- "Which stakeholders are involved in the authentication capability?" → Join with `catalog_stakeholder_capability_links`
- "Who has expertise in Finance?" → `WHERE expertise_areas @> '["finance"]'`
- "What are Sarah's responsibility areas?" → `WHERE name = 'Sarah' AND responsibility_areas`
- "Which stakeholders are in the Engineering department?" → `WHERE department = 'Engineering'`

### 8. Evidence

Raw evidence records with provenance.

```sql
CREATE TABLE IF NOT EXISTS catalog_evidence (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id       TEXT NOT NULL,
    title           TEXT NOT NULL,
    description     TEXT,
    evidence_type   TEXT NOT NULL  -- 'connector_output', 'manual_input', 'system_event', 'document', 'interview'
        CHECK (evidence_type IN ('connector_output', 'manual_input', 'system_event', 'document', 'interview', 'derived')),
    source_id       UUID REFERENCES sources(id) ON DELETE SET NULL,  -- which connector produced this
    content         TEXT,            -- raw content or summary
    content_hash    TEXT,            -- for deduplication
    confidence      REAL NOT NULL DEFAULT 0.0 CHECK (confidence >= 0 AND confidence <= 1),
    reliability     REAL NOT NULL DEFAULT 0.5 CHECK (reliability >= 0 AND reliability <= 1),  -- from source reliability
    timestamp       TIMESTAMPTZ NOT NULL DEFAULT NOW(),  -- when the evidence was observed
    expires_at      TIMESTAMPTZ,     -- when this evidence becomes stale
    tags            JSONB NOT NULL DEFAULT '[]'::jsonb,
    metadata        JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    created_by      TEXT,
    updated_by      TEXT,
    version         INT NOT NULL DEFAULT 1
);

CREATE INDEX IF NOT EXISTS idx_catalog_evidence_tenant ON catalog_evidence(tenant_id);
CREATE INDEX IF NOT EXISTS idx_catalog_evidence_type ON catalog_evidence(evidence_type);
CREATE INDEX IF NOT EXISTS idx_catalog_evidence_source ON catalog_evidence(source_id);
CREATE INDEX IF NOT EXISTS idx_catalog_evidence_confidence ON catalog_evidence(confidence);
CREATE INDEX IF NOT EXISTS idx_catalog_evidence_timestamp ON catalog_evidence(timestamp);
CREATE INDEX IF NOT EXISTS idx_catalog_evidence_gin_tags ON catalog_evidence USING GIN(tags);
```

**Query Patterns:**
- "Show me all evidence from the Stripe connector" → `WHERE source_id = ?`
- "What evidence supports the claim that churn is increasing?" → Through `catalog_evidence_claim_links`
- "Show me low-confidence evidence that needs review" → `WHERE confidence < 0.3`
- "What evidence was collected this week?" → `WHERE timestamp >= ?`

### 9. Systems

Technical systems, their capabilities, integrations.

```sql
CREATE TABLE IF NOT EXISTS catalog_systems (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id       TEXT NOT NULL,
    name            TEXT NOT NULL,
    description     TEXT,
    system_type     TEXT NOT NULL  -- 'saas', 'internal', 'legacy', 'infrastructure', 'data_store'
        CHECK (system_type IN ('saas', 'internal', 'legacy', 'infrastructure', 'data_store')),
    status          TEXT NOT NULL DEFAULT 'active'
        CHECK (status IN ('active', 'planned', 'sunset', 'decommissioned', 'migrating')),
    owner_id        UUID REFERENCES stakeholders(id) ON DELETE SET NULL,
    vendor          TEXT,
    version         TEXT,           -- system version (e.g., 'v2.3.1')
    url             TEXT,           -- system URL or endpoint
    capabilities    JSONB NOT NULL DEFAULT '[]'::jsonb,  -- list of capabilities this system provides
    integrations    JSONB NOT NULL DEFAULT '[]'::jsonb,  -- list of systems this integrates with
    data_class      TEXT            -- 'public', 'internal', 'confidential', 'restricted'
        CHECK (data_class IN ('public', 'internal', 'confidential', 'restricted')),
    confidence      REAL NOT NULL DEFAULT 0.0 CHECK (confidence >= 0 AND confidence <= 1),
    evidence_ids    JSONB NOT NULL DEFAULT '[]'::jsonb,
    tags            JSONB NOT NULL DEFAULT '[]'::jsonb,
    metadata        JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    created_by      TEXT,
    updated_by      TEXT,
    catalog_version INT NOT NULL DEFAULT 1  -- renamed from 'version' to avoid conflict with system.version
);

CREATE INDEX IF NOT EXISTS idx_catalog_systems_tenant ON catalog_systems(tenant_id);
CREATE INDEX IF NOT EXISTS idx_catalog_systems_status ON catalog_systems(status);
CREATE INDEX IF NOT EXISTS idx_catalog_systems_type ON catalog_systems(system_type);
CREATE INDEX IF NOT EXISTS idx_catalog_systems_owner ON catalog_systems(owner_id);
CREATE INDEX IF NOT EXISTS idx_catalog_systems_gin_capabilities ON catalog_systems USING GIN(capabilities);
```

**Query Patterns:**
- "Which systems support the Authentication capability?" → Join with `catalog_system_capability_links`
- "What systems are integrated with the CRM?" → `WHERE integrations @> '["crm"]'`
- "Show me all sunset systems" → `WHERE status = 'sunset'`
- "What data class is the Payment System?" → `WHERE name = 'Payment System' SELECT data_class`

### 10. Projects

Active and completed projects, their goals, outcomes.

```sql
CREATE TABLE IF NOT EXISTS catalog_projects (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id       TEXT NOT NULL,
    name            TEXT NOT NULL,
    description     TEXT,
    project_type    TEXT NOT NULL  -- 'strategic', 'tactical', 'operational', 'maintenance'
        CHECK (project_type IN ('strategic', 'tactical', 'operational', 'maintenance')),
    status          TEXT NOT NULL DEFAULT 'initiated'
        CHECK (status IN ('initiated', 'planning', 'executing', 'monitoring', 'completed', 'cancelled', 'on_hold')),
    owner_id        UUID REFERENCES stakeholders(id) ON DELETE SET NULL,
    start_date      TIMESTAMPTZ,
    target_end_date TIMESTAMPTZ,
    actual_end_date TIMESTAMPTZ,
    goals           JSONB NOT NULL DEFAULT '[]'::jsonb,
    outcomes        JSONB NOT NULL DEFAULT '[]'::jsonb,
    budget          REAL,
    actual_cost     REAL,
    progress_pct    REAL NOT NULL DEFAULT 0.0 CHECK (progress_pct >= 0 AND progress_pct <= 100),
    related_capability_ids JSONB NOT NULL DEFAULT '[]'::jsonb,
    related_risk_ids       JSONB NOT NULL DEFAULT '[]'::jsonb,
    confidence      REAL NOT NULL DEFAULT 0.0 CHECK (confidence >= 0 AND confidence <= 1),
    evidence_ids    JSONB NOT NULL DEFAULT '[]'::jsonb,
    tags            JSONB NOT NULL DEFAULT '[]'::jsonb,
    metadata        JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    created_by      TEXT,
    updated_by      TEXT,
    version         INT NOT NULL DEFAULT 1
);

CREATE INDEX IF NOT EXISTS idx_catalog_projects_tenant ON catalog_projects(tenant_id);
CREATE INDEX IF NOT EXISTS idx_catalog_projects_status ON catalog_projects(status);
CREATE INDEX IF NOT EXISTS idx_catalog_projects_type ON catalog_projects(project_type);
CREATE INDEX IF NOT EXISTS idx_catalog_projects_owner ON catalog_projects(owner_id);
CREATE INDEX IF NOT EXISTS idx_catalog_projects_dates ON catalog_projects(start_date, target_end_date);
```

**Query Patterns:**
- "Show me all active strategic projects" → `WHERE status IN ('executing','monitoring') AND project_type = 'strategic'`
- "What projects are behind schedule?" → `WHERE target_end_date < NOW() AND status != 'completed'`
- "Which projects affect the Sales capability?" → `WHERE related_capability_ids @> '["cap-id"]'`
- "What's the total budget for all projects?" → `SELECT SUM(budget) FROM catalog_projects`

---

## Relationship Definitions Between Categories

### Cross-Category Link Tables

```sql
-- Capability ↔ System (which capabilities depend on which systems)
CREATE TABLE IF NOT EXISTS catalog_capability_system_links (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id       TEXT NOT NULL,
    capability_id   UUID NOT NULL REFERENCES catalog_capabilities(id) ON DELETE CASCADE,
    system_id       UUID NOT NULL REFERENCES catalog_systems(id) ON DELETE CASCADE,
    relationship    TEXT NOT NULL DEFAULT 'depends_on'
        CHECK (relationship IN ('depends_on', 'supports', 'replaced_by', 'integrates_with')),
    strength        TEXT NOT NULL DEFAULT 'required'
        CHECK (strength IN ('required', 'preferred', 'optional')),
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE(tenant_id, capability_id, system_id, relationship)
);

-- Capability ↔ Stakeholder (who is involved in which capabilities)
CREATE TABLE IF NOT EXISTS catalog_stakeholder_capability_links (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id       TEXT NOT NULL,
    stakeholder_id  UUID NOT NULL REFERENCES catalog_stakeholders(id) ON DELETE CASCADE,
    capability_id   UUID NOT NULL REFERENCES catalog_capabilities(id) ON DELETE CASCADE,
    role_in_capability TEXT NOT NULL DEFAULT 'participant'
        CHECK (role_in_capability IN ('owner', 'lead', 'participant', 'reviewer', 'adviser')),
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE(tenant_id, stakeholder_id, capability_id, role_in_capability)
);

-- Decision ↔ Capability (which decisions affect which capabilities)
CREATE TABLE IF NOT EXISTS catalog_decision_capability_links (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id       TEXT NOT NULL,
    decision_id     UUID NOT NULL REFERENCES catalog_decisions(id) ON DELETE CASCADE,
    capability_id   UUID NOT NULL REFERENCES catalog_capabilities(id) ON DELETE CASCADE,
    impact_type     TEXT NOT NULL DEFAULT 'affects'
        CHECK (impact_type IN ('affects', 'creates', 'modifies', 'deprecates')),
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE(tenant_id, decision_id, capability_id, impact_type)
);

-- Decision ↔ Evidence (evidence chain for decisions)
CREATE TABLE IF NOT EXISTS catalog_decision_evidence_links (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id       TEXT NOT NULL,
    decision_id     UUID NOT NULL REFERENCES catalog_decisions(id) ON DELETE CASCADE,
    evidence_id     UUID NOT NULL REFERENCES catalog_evidence(id) ON DELETE CASCADE,
    role_in_decision TEXT NOT NULL DEFAULT 'supporting'
        CHECK (role_in_decision IN ('supporting', 'contradicting', 'contextual', 'prerequisite')),
    weight          REAL NOT NULL DEFAULT 1.0,  -- how much this evidence influenced the decision
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE(tenant_id, decision_id, evidence_id, role_in_decision)
);

-- Risk ↔ Evidence (evidence chain for risks)
CREATE TABLE IF NOT EXISTS catalog_risk_evidence_links (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id       TEXT NOT NULL,
    risk_id         UUID NOT NULL REFERENCES catalog_risks(id) ON DELETE CASCADE,
    evidence_id     UUID NOT NULL REFERENCES catalog_evidence(id) ON DELETE CASCADE,
    role_in_risk    TEXT NOT NULL DEFAULT 'supporting'
        CHECK (role_in_risk IN ('supporting', 'mitigating', 'contradicting', 'contextual')),
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE(tenant_id, risk_id, evidence_id, role_in_risk)
);

-- Process ↔ Capability (which processes support which capabilities)
CREATE TABLE IF NOT EXISTS catalog_process_capability_links (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id       TEXT NOT NULL,
    process_id      UUID NOT NULL REFERENCES catalog_processes(id) ON DELETE CASCADE,
    capability_id   UUID NOT NULL REFERENCES catalog_capabilities(id) ON DELETE CASCADE,
    relationship    TEXT NOT NULL DEFAULT 'implements'
        CHECK (relationship IN ('implements', 'supports', 'depends_on')),
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE(tenant_id, process_id, capability_id, relationship)
);

-- Policy ↔ Capability (which policies apply to which capabilities)
CREATE TABLE IF NOT EXISTS catalog_policy_capability_links (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id       TEXT NOT NULL,
    policy_id       UUID NOT NULL REFERENCES catalog_policies(id) ON DELETE CASCADE,
    capability_id   UUID NOT NULL REFERENCES catalog_capabilities(id) ON DELETE CASCADE,
    enforcement     TEXT NOT NULL DEFAULT 'mandatory'
        CHECK (enforcement IN ('mandatory', 'advisory', 'optional')),
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE(tenant_id, policy_id, capability_id)
);

-- Artifact ↔ Capability (which artifacts document which capabilities)
CREATE TABLE IF NOT EXISTS catalog_artifact_capability_links (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id       TEXT NOT NULL,
    artifact_id     UUID NOT NULL REFERENCES catalog_artifacts(id) ON DELETE CASCADE,
    capability_id   UUID NOT NULL REFERENCES catalog_capabilities(id) ON DELETE CASCADE,
    relationship    TEXT NOT NULL DEFAULT 'documents'
        CHECK (relationship IN ('documents', 'specifies', 'analyzes', 'depicts')),
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE(tenant_id, artifact_id, capability_id, relationship)
);

-- Artifact ↔ Decision (which artifacts support which decisions)
CREATE TABLE IF NOT EXISTS catalog_artifact_decision_links (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id       TEXT NOT NULL,
    artifact_id     UUID NOT NULL REFERENCES catalog_artifacts(id) ON DELETE CASCADE,
    decision_id     UUID NOT NULL REFERENCES catalog_decisions(id) ON DELETE CASCADE,
    relationship    TEXT NOT NULL DEFAULT 'supports'
        CHECK (relationship IN ('supports', 'informs', 'supersedes')),
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE(tenant_id, artifact_id, decision_id, relationship)
);

-- Project ↔ Capability (which projects affect which capabilities)
CREATE TABLE IF NOT EXISTS catalog_project_capability_links (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id       TEXT NOT NULL,
    project_id      UUID NOT NULL REFERENCES catalog_projects(id) ON DELETE CASCADE,
    capability_id   UUID NOT NULL REFERENCES catalog_capabilities(id) ON DELETE CASCADE,
    impact_type     TEXT NOT NULL DEFAULT 'improves'
        CHECK (impact_type IN ('improves', 'creates', 'modifies', 'deprecates', 'replaces')),
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE(tenant_id, project_id, capability_id, impact_type)
);

-- Stakeholder ↔ Decision (who participated in which decisions)
CREATE TABLE IF NOT EXISTS catalog_stakeholder_decision_links (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id       TEXT NOT NULL,
    stakeholder_id  UUID NOT NULL REFERENCES catalog_stakeholders(id) ON DELETE CASCADE,
    decision_id     UUID NOT NULL REFERENCES catalog_decisions(id) ON DELETE CASCADE,
    role_in_decision TEXT NOT NULL DEFAULT 'participant'
        CHECK (role_in_decision IN ('decision_maker', 'reviewer', 'participant', 'informed')),
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE(tenant_id, stakeholder_id, decision_id, role_in_decision)
);
```

### Relationship Graph Summary

```
                    ┌──────────────┐
                    │   CAPABILITY │
                    └──────┬───────┘
                           │
        ┌──────────────────┼──────────────────┐
        │                  │                  │
        ▼                  ▼                  ▼
  ┌──────────┐      ┌──────────┐      ┌──────────┐
  │  SYSTEM  │      │ PROCESS  │      │ POLICY   │
  └──────────┘      └──────────┘      └──────────┘
        │                  │                  │
        ▼                  ▼                  ▼
  ┌──────────┐      ┌──────────┐      ┌──────────┐
  │ EVIDENCE │      │ ARTIFACT │      │  RISK    │
  └──────────┘      └──────────┘      └──────────┘
        │                  │                  │
        └──────────────────┼──────────────────┘
                           │
                           ▼
                    ┌──────────┐
                    │ DECISION │
                    └────┬─────┘
                         │
              ┌──────────┼──────────┐
              │          │          │
              ▼          ▼          ▼
        ┌──────────┐ ┌──────────┐ ┌──────────┐
        │STAKEHOLDER│ │ PROJECT  │ │ EVIDENCE │
        └──────────┘ └──────────┘ └──────────┘
```

---

## Lifecycle State Machines

### Universal Lifecycle Pattern

All categories follow a consistent lifecycle pattern with category-specific states:

```
┌─────────┐     ┌──────────┐     ┌──────────┐     ┌──────────┐
│  draft  │────▶│  active  │────▶│ archived │────▶│deprecated│
└─────────┘     └──────────┘     └──────────┘     └──────────┘
     │               │
     │               ▼
     │          ┌──────────┐
     └─────────▶│ rejected │
                └──────────┘
```

### Category-Specific Lifecycle Details

#### Capabilities
```
initial → developing → defined → managed → optimizing
   │          │           │         │          │
   └──────────┴───────────┴─────────┴──────────┘
                         ↓
                    archived/deprecated
```

#### Decisions
```
proposed → in_review → approved → implemented → superseded
    │          │           │            │
    └──────────┴───────────┴────────────┘
                    ↓
               rejected/archived
```

#### Processes
```
draft → active → archived/deprecated
  │       │
  └───────┴──→ under_review → updated → active
```

#### Policies
```
draft → active → superseded/deprecated/archived
  │       │
  └───────┴──→ under_review → updated → active
```

#### Risks
```
identified → assessed → mitigating → mitigated → closed
    │           │           │            │
    └───────────┴───────────┴────────────┘
                         ↓
                    realized (risk materialized)
                    accepted (conscious decision to accept)
```

#### Artifacts
```
draft → review → published → superseded → archived
  │       │
  └───────┴──→ rejected
```

#### Evidence
```
collected → validated → stale → archived
    │
    └──→ disputed (contradicted by other evidence)
```

#### Systems
```
planned → active → sunset → decommissioned
              │
              └──→ migrating
```

#### Projects
```
initiated → planning → executing → monitoring → completed
    │           │           │           │
    └───────────┴───────────┴───────────┘
                         ↓
                    cancelled/on_hold
```

---

## Access Control Model

### Role-Based Access Control (RBAC)

```sql
-- Catalog roles
CREATE TABLE IF NOT EXISTS catalog_roles (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id       TEXT NOT NULL,
    name            TEXT NOT NULL,
    description     TEXT,
    permissions     JSONB NOT NULL DEFAULT '{}'::jsonb,  -- category → permission set
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE(tenant_id, name)
);

-- Role assignments
CREATE TABLE IF NOT EXISTS catalog_role_assignments (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id       TEXT NOT NULL,
    role_id         UUID NOT NULL REFERENCES catalog_roles(id) ON DELETE CASCADE,
    user_id         TEXT NOT NULL,  -- references users table
    scope           JSONB NOT NULL DEFAULT '{}'::jsonb,  -- optional scope constraints
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE(tenant_id, role_id, user_id)
);
```

### Permission Schema

```json
{
  "capabilities": {
    "read": true,
    "write": true,
    "delete": false,
    "admin": false
  },
  "decisions": {
    "read": true,
    "write": true,
    "approve": false,
    "delete": false
  },
  "evidence": {
    "read": true,
    "write": true,
    "delete": false
  },
  "policies": {
    "read": true,
    "write": false,
    "admin": false
  }
}
```

### Default Roles

1. **Catalog Viewer** — Read-only access to all categories
2. **Catalog Editor** — Read/write access to assigned categories
3. **Catalog Admin** — Full access including admin and delete
4. **Domain Expert** — Read/write access to specific domains (e.g., Finance, Sales)
5. **Decision Maker** — Read access to all, write access to Decisions and Artifacts

### Access Control Enforcement

```python
class CatalogAccessControl:
    """Enforces access control for catalog operations."""
    
    def check_permission(
        self,
        user_id: str,
        category: str,
        operation: str,  # 'read', 'write', 'delete', 'admin'
        resource_id: str | None = None,
        tenant_id: str = "default",
    ) -> bool:
        """Check if user has permission for the operation on the category."""
        # 1. Look up user's roles
        # 2. Check if any role grants the permission
        # 3. Apply scope constraints if any
        # 4. Return True/False
        pass
    
    def filter_query(
        self,
        user_id: str,
        category: str,
        query: dict,
        tenant_id: str = "default",
    ) -> dict:
        """Filter a query based on user's access control scope."""
        # If user has full access, return query unchanged
        # If user has domain scope, add domain filter
        # If user has entity scope, add entity filter
        pass
```

---

## API Design for Catalog Operations

### REST Endpoints

```
GET    /api/v1/catalog/{category}                    # List all items in category
GET    /api/v1/catalog/{category}/{id}               # Get single item
POST   /api/v1/catalog/{category}                    # Create new item
PUT    /api/v1/catalog/{category}/{id}               # Update item
DELETE /api/v1/catalog/{category}/{id}               # Delete item (soft delete)

GET    /api/v1/catalog/search                         # Cross-category search
GET    /api/v1/catalog/{category}/relationships/{id}  # Get relationships for item
POST   /api/v1/catalog/links                          # Create relationship link
DELETE /api/v1/catalog/links/{link_id}                # Remove relationship link

GET    /api/v1/catalog/graph/{category}/{id}          # Get relationship graph
GET    /api/v1/catalog/stats                          # Get catalog statistics
GET    /api/v1/catalog/{category}/export              # Export category data
```

### Query Parameters

```
# Filtering
?domain=Sales
?status=active
?owner_id=uuid
?confidence_min=0.7
?confidence_max=1.0
?created_after=2026-01-01
?created_before=2026-06-30
?tags=finance,quarterly

# Pagination
?page=1
?page_size=20
?sort_by=name
?sort_order=asc

# Search
?q=authentication
?q=decision:pricing
?q=risk:churn

# Relationships
?include=stakeholders,systems,evidence
?depth=2
```

### GraphQL Schema (Optional)

```graphql
type Query {
  catalog(
    category: CatalogCategory
    filter: CatalogFilter
    pagination: PaginationInput
  ): CatalogConnection!
  
  catalogItem(
    category: CatalogCategory!
    id: ID!
  ): CatalogItem
  
  searchCatalog(
    query: String!
    categories: [CatalogCategory!]
    filter: CatalogFilter
  ): CatalogConnection!
  
  relationshipGraph(
    category: CatalogCategory!
    id: ID!
    depth: Int
  ): RelationshipGraph!
}

type CatalogItem {
  id: ID!
  category: CatalogCategory!
  name: String!
  description: String
  status: String!
  confidence: Float
  owner: Stakeholder
  evidence: [Evidence!]!
  relationships: RelationshipConnection!
  metadata: JSON
  createdAt: DateTime!
  updatedAt: DateTime!
}

enum CatalogCategory {
  CAPABILITY
  DECISION
  PROCESS
  POLICY
  RISK
  ARTIFACT
  STAKEHOLDER
  EVIDENCE
  SYSTEM
  PROJECT
}
```

### Python SDK Interface

```python
class KnowledgeCatalog:
    """Client for the Knowledge Catalog API."""
    
    def __init__(self, base_url: str, auth: AuthProvider):
        self.base_url = base_url
        self.auth = auth
    
    def list_capabilities(
        self,
        domain: str | None = None,
        status: str | None = None,
        owner_id: str | None = None,
        page: int = 1,
        page_size: int = 20,
    ) -> PaginatedResult[Capability]:
        """List capabilities with optional filters."""
        pass
    
    def get_capability(self, capability_id: str) -> Capability:
        """Get a single capability by ID."""
        pass
    
    def search(
        self,
        query: str,
        categories: list[str] | None = None,
        filters: dict | None = None,
    ) -> SearchResults:
        """Search across all categories."""
        pass
    
    def get_relationships(
        self,
        category: str,
        item_id: str,
        relationship_type: str | None = None,
        depth: int = 1,
    ) -> RelationshipGraph:
        """Get relationships for an item."""
        pass
    
    def get_evidence_chain(
        self,
        category: str,
        item_id: str,
    ) -> EvidenceChain:
        """Get the full evidence chain for an item."""
        pass
```

---

## Catalog Navigation Model

### Browse by Category

```
/catalog
  /capabilities          → List view with maturity indicators
  /decisions             → List view with decision date and status
  /processes             → List view with process type
  /policies              → List view with severity and enforcement
  /risks                 → List view with risk score heatmap
  /artifacts             → List view with artifact type icons
  /stakeholders          → List view with role and department
  /evidence              → List view with confidence scores
  /systems               → List view with status indicators
  /projects              → List view with progress bars
```

### Filter Panel

```
┌─────────────────────────────────────────────────────┐
│  FILTER BY                                          │
├─────────────────────────────────────────────────────┤
│  Domain:        [Sales ▼] [Finance ▼] [Ops ▼]     │
│  Status:        [Active ☑] [Draft ☐] [Archived ☐] │
│  Owner:         [Sarah ▼] [Mike ▼] [Any ▼]        │
│  Confidence:    [━━━━━━━━━●━━━] 0.7 - 1.0          │
│  Date Range:    [2026-01-01] to [2026-06-30]       │
│  Tags:          [quarterly] [pricing] [risk]        │
│                                                      │
│  ┌──────────────────────────────────────────────┐   │
│  │  APPLY FILTERS                               │   │
│  └──────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────┘
```

### Search Bar

```
┌─────────────────────────────────────────────────────┐
│  🔍 Search across all knowledge...                   │
│                                                      │
│  Quick Filters: [Decisions] [Risks] [Evidence]      │
└─────────────────────────────────────────────────────┘
```

### Relationship Graph View

```
┌─────────────────────────────────────────────────────┐
│  CAPABILITY: Authentication                         │
├─────────────────────────────────────────────────────┤
│                                                      │
│  ┌──────────┐    depends_on    ┌──────────┐        │
│  │   Auth   │─────────────────▶│  CRM     │        │
│  │  Cap.    │                  │  System  │        │
│  └────┬─────┘                  └──────────┘        │
│       │                                              │
│       │ implements                                   │
│       ▼                                              │
│  ┌──────────┐    supports     ┌──────────┐        │
│  │ Login    │◀────────────────│  OAuth   │        │
│  │ Process  │                 │  Policy  │        │
│  └──────────┘                 └──────────┘        │
│                                                      │
└─────────────────────────────────────────────────────┘
```

---

## Implementation Plan

### Phase 1: Core Tables (Week 1-2)
1. Create all 10 category tables
2. Create cross-category link tables
3. Add indexes for common query patterns
4. Create migration script

### Phase 2: Data Ingestion (Week 3-4)
1. Build catalog sync service (operational → catalog)
2. Implement evidence chain linking
3. Add confidence score computation
4. Create data quality checks

### Phase 3: API Layer (Week 5-6)
1. Build REST API endpoints
2. Implement search functionality
3. Add relationship traversal
4. Build GraphQL schema (optional)

### Phase 4: UI Integration (Week 7-8)
1. Add catalog navigation to HTMX UI
2. Build category list views
3. Add filter panel
4. Build relationship graph visualization

### Phase 5: Access Control (Week 9)
1. Implement RBAC
2. Add role assignments
3. Test access control enforcement

---

## Consequences

### Positive
1. **Unified Search** — Single query across all knowledge categories
2. **Relationship Traversal** — Navigate from capabilities to evidence chains
3. **Provenance Tracking** — Full audit trail for every knowledge artifact
4. **Confidence Scoring** — Quantified trust in every piece of knowledge
5. **Access Control** — Fine-grained permissions by category and domain
6. **Scalability** — Catalog tables can be independently indexed and scaled

### Negative
1. **Data Duplication** — Catalog tables duplicate operational data
2. **Sync Complexity** — Need to keep catalog in sync with operational tables
3. **Storage Overhead** — Additional tables and indexes
4. **Query Complexity** — Cross-category joins can be expensive

### Mitigations
1. **Event-Driven Sync** — Use existing event bus to update catalog incrementally
2. **Materialized Views** — Pre-compute expensive joins for common queries
3. **Read-Optimized** — Catalog tables designed for read-heavy workloads
4. ** eventual Consistency** — Catalog can lag operational tables by seconds

---

## References

- Migration 004_v6_entities.sql — Existing V6 entity tables
- object_types.py — Canonical Object Type definitions
- link_types.py — Existing 11 semantic links
- governance.py — HITL approval enforcement
- ba_artifact.py — BA artifact lifecycle states

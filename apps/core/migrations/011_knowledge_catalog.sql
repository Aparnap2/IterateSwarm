-- OntologyAI V6 — Knowledge Catalog Schema
-- Migration: 011
-- Date: 2026-08-04
-- This migration creates the Knowledge Catalog tables that index ALL
-- enterprise knowledge artifacts across 10 categories.

-- =============================================
-- Updated-at trigger function (idempotent)
-- =============================================
CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ language 'plpgsql';

-- =============================================
-- 1. Capabilities
-- =============================================
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
    domain          TEXT,
    tags            JSONB NOT NULL DEFAULT '[]'::jsonb,
    confidence      REAL NOT NULL DEFAULT 0.0 CHECK (confidence >= 0 AND confidence <= 1),
    evidence_ids    JSONB NOT NULL DEFAULT '[]'::jsonb,
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

DROP TRIGGER IF EXISTS trg_catalog_capabilities_updated_at ON catalog_capabilities;
CREATE TRIGGER trg_catalog_capabilities_updated_at
    BEFORE UPDATE ON catalog_capabilities
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

-- =============================================
-- 2. Decisions
-- =============================================
CREATE TABLE IF NOT EXISTS catalog_decisions (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id       TEXT NOT NULL,
    title           TEXT NOT NULL,
    description     TEXT,
    decision_type   TEXT NOT NULL DEFAULT 'tactical'
        CHECK (decision_type IN ('strategic', 'tactical', 'operational', 'technical')),
    status          TEXT NOT NULL DEFAULT 'proposed'
        CHECK (status IN ('proposed', 'in_review', 'approved', 'rejected', 'implemented', 'superseded', 'archived')),
    decision_date   TIMESTAMPTZ,
    owner_id        UUID REFERENCES stakeholders(id) ON DELETE SET NULL,
    workspace_id    TEXT REFERENCES workspaces(id) ON DELETE SET NULL,
    rationale       TEXT,
    alternatives    JSONB NOT NULL DEFAULT '[]'::jsonb,
    outcome         TEXT,
    confidence      REAL NOT NULL DEFAULT 0.0 CHECK (confidence >= 0 AND confidence <= 1),
    evidence_ids    JSONB NOT NULL DEFAULT '[]'::jsonb,
    impact_score    REAL,
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

DROP TRIGGER IF EXISTS trg_catalog_decisions_updated_at ON catalog_decisions;
CREATE TRIGGER trg_catalog_decisions_updated_at
    BEFORE UPDATE ON catalog_decisions
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

-- =============================================
-- 3. Processes
-- =============================================
CREATE TABLE IF NOT EXISTS catalog_processes (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id       TEXT NOT NULL,
    name            TEXT NOT NULL,
    description     TEXT,
    process_type    TEXT NOT NULL DEFAULT 'core'
        CHECK (process_type IN ('core', 'support', 'management')),
    status          TEXT NOT NULL DEFAULT 'draft'
        CHECK (status IN ('draft', 'active', 'archived', 'deprecated')),
    owner_id        UUID REFERENCES stakeholders(id) ON DELETE SET NULL,
    frequency       TEXT,
    inputs          JSONB NOT NULL DEFAULT '[]'::jsonb,
    outputs         JSONB NOT NULL DEFAULT '[]'::jsonb,
    steps           JSONB NOT NULL DEFAULT '[]'::jsonb,
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

DROP TRIGGER IF EXISTS trg_catalog_processes_updated_at ON catalog_processes;
CREATE TRIGGER trg_catalog_processes_updated_at
    BEFORE UPDATE ON catalog_processes
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

-- =============================================
-- 4. Policies
-- =============================================
CREATE TABLE IF NOT EXISTS catalog_policies (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id       TEXT NOT NULL,
    name            TEXT NOT NULL,
    description     TEXT,
    policy_type     TEXT NOT NULL DEFAULT 'guideline'
        CHECK (policy_type IN ('regulation', 'standard', 'guideline', 'constraint')),
    severity        TEXT NOT NULL DEFAULT 'info'
        CHECK (severity IN ('block', 'warn', 'info')),
    status          TEXT NOT NULL DEFAULT 'active'
        CHECK (status IN ('draft', 'active', 'superseded', 'deprecated', 'archived')),
    owner_id        UUID REFERENCES stakeholders(id) ON DELETE SET NULL,
    effective_date  TIMESTAMPTZ,
    expiry_date     TIMESTAMPTZ,
    rule_expression TEXT NOT NULL DEFAULT '',
    applies_to      JSONB NOT NULL DEFAULT '[]'::jsonb,
    enforcement     TEXT NOT NULL DEFAULT 'mandatory'
        CHECK (enforcement IN ('mandatory', 'advisory', 'optional')),
    source_ref      TEXT,
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

DROP TRIGGER IF EXISTS trg_catalog_policies_updated_at ON catalog_policies;
CREATE TRIGGER trg_catalog_policies_updated_at
    BEFORE UPDATE ON catalog_policies
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

-- =============================================
-- 5. Risks
-- =============================================
CREATE TABLE IF NOT EXISTS catalog_risks (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id       TEXT NOT NULL,
    title           TEXT NOT NULL,
    description     TEXT,
    risk_category   TEXT NOT NULL DEFAULT 'operational'
        CHECK (risk_category IN ('strategic', 'operational', 'financial', 'technical', 'compliance')),
    likelihood      TEXT NOT NULL DEFAULT 'medium'
        CHECK (likelihood IN ('low', 'medium', 'high', 'very_high')),
    impact          TEXT NOT NULL DEFAULT 'medium'
        CHECK (impact IN ('low', 'medium', 'high', 'critical')),
    risk_score      REAL NOT NULL DEFAULT 0.0,
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

DROP TRIGGER IF EXISTS trg_catalog_risks_updated_at ON catalog_risks;
CREATE TRIGGER trg_catalog_risks_updated_at
    BEFORE UPDATE ON catalog_risks
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

-- =============================================
-- 6. Artifacts
-- =============================================
CREATE TABLE IF NOT EXISTS catalog_artifacts (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id       TEXT NOT NULL,
    name            TEXT NOT NULL,
    description     TEXT,
    artifact_category TEXT NOT NULL DEFAULT 'other'
        CHECK (artifact_category IN ('report', 'brief', 'analysis', 'spec', 'diagram', 'contract', 'policy_doc', 'other')),
    artifact_type   TEXT,
    status          TEXT NOT NULL DEFAULT 'draft'
        CHECK (status IN ('draft', 'review', 'published', 'superseded', 'archived')),
    workspace_id    TEXT REFERENCES workspaces(id) ON DELETE SET NULL,
    owner_id        UUID REFERENCES stakeholders(id) ON DELETE SET NULL,
    project_id      UUID REFERENCES projects(id) ON DELETE SET NULL,
    content_ref     TEXT,
    content_hash    TEXT,
    format          TEXT,
    producer        TEXT,
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

DROP TRIGGER IF EXISTS trg_catalog_artifacts_updated_at ON catalog_artifacts;
CREATE TRIGGER trg_catalog_artifacts_updated_at
    BEFORE UPDATE ON catalog_artifacts
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

-- =============================================
-- 7. Stakeholders
-- =============================================
CREATE TABLE IF NOT EXISTS catalog_stakeholders (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id       TEXT NOT NULL,
    name            TEXT NOT NULL,
    email           TEXT,
    role            TEXT,
    department      TEXT,
    expertise_areas JSONB NOT NULL DEFAULT '[]'::jsonb,
    responsibility_areas JSONB NOT NULL DEFAULT '[]'::jsonb,
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

DROP TRIGGER IF EXISTS trg_catalog_stakeholders_updated_at ON catalog_stakeholders;
CREATE TRIGGER trg_catalog_stakeholders_updated_at
    BEFORE UPDATE ON catalog_stakeholders
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

-- =============================================
-- 8. Evidence
-- =============================================
CREATE TABLE IF NOT EXISTS catalog_evidence (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id       TEXT NOT NULL,
    title           TEXT NOT NULL,
    description     TEXT,
    evidence_type   TEXT NOT NULL DEFAULT 'manual_input'
        CHECK (evidence_type IN ('connector_output', 'manual_input', 'system_event', 'document', 'interview', 'derived')),
    source_id       UUID REFERENCES sources(id) ON DELETE SET NULL,
    content         TEXT,
    content_hash    TEXT,
    confidence      REAL NOT NULL DEFAULT 0.0 CHECK (confidence >= 0 AND confidence <= 1),
    reliability     REAL NOT NULL DEFAULT 0.5 CHECK (reliability >= 0 AND reliability <= 1),
    timestamp       TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    expires_at      TIMESTAMPTZ,
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

DROP TRIGGER IF EXISTS trg_catalog_evidence_updated_at ON catalog_evidence;
CREATE TRIGGER trg_catalog_evidence_updated_at
    BEFORE UPDATE ON catalog_evidence
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

-- =============================================
-- 9. Systems
-- =============================================
CREATE TABLE IF NOT EXISTS catalog_systems (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id       TEXT NOT NULL,
    name            TEXT NOT NULL,
    description     TEXT,
    system_type     TEXT NOT NULL DEFAULT 'internal'
        CHECK (system_type IN ('saas', 'internal', 'legacy', 'infrastructure', 'data_store')),
    status          TEXT NOT NULL DEFAULT 'active'
        CHECK (status IN ('active', 'planned', 'sunset', 'decommissioned', 'migrating')),
    owner_id        UUID REFERENCES stakeholders(id) ON DELETE SET NULL,
    vendor          TEXT,
    system_version  TEXT,
    url             TEXT,
    capabilities    JSONB NOT NULL DEFAULT '[]'::jsonb,
    integrations    JSONB NOT NULL DEFAULT '[]'::jsonb,
    data_class      TEXT DEFAULT 'internal'
        CHECK (data_class IN ('public', 'internal', 'confidential', 'restricted')),
    confidence      REAL NOT NULL DEFAULT 0.0 CHECK (confidence >= 0 AND confidence <= 1),
    evidence_ids    JSONB NOT NULL DEFAULT '[]'::jsonb,
    tags            JSONB NOT NULL DEFAULT '[]'::jsonb,
    metadata        JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    created_by      TEXT,
    updated_by      TEXT,
    catalog_version INT NOT NULL DEFAULT 1
);

CREATE INDEX IF NOT EXISTS idx_catalog_systems_tenant ON catalog_systems(tenant_id);
CREATE INDEX IF NOT EXISTS idx_catalog_systems_status ON catalog_systems(status);
CREATE INDEX IF NOT EXISTS idx_catalog_systems_type ON catalog_systems(system_type);
CREATE INDEX IF NOT EXISTS idx_catalog_systems_owner ON catalog_systems(owner_id);
CREATE INDEX IF NOT EXISTS idx_catalog_systems_gin_capabilities ON catalog_systems USING GIN(capabilities);

DROP TRIGGER IF EXISTS trg_catalog_systems_updated_at ON catalog_systems;
CREATE TRIGGER trg_catalog_systems_updated_at
    BEFORE UPDATE ON catalog_systems
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

-- =============================================
-- 10. Projects
-- =============================================
CREATE TABLE IF NOT EXISTS catalog_projects (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id       TEXT NOT NULL,
    name            TEXT NOT NULL,
    description     TEXT,
    project_type    TEXT NOT NULL DEFAULT 'tactical'
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

DROP TRIGGER IF EXISTS trg_catalog_projects_updated_at ON catalog_projects;
CREATE TRIGGER trg_catalog_projects_updated_at
    BEFORE UPDATE ON catalog_projects
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

-- =============================================
-- Cross-Category Link Tables
-- =============================================

-- Capability ↔ System
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

CREATE INDEX IF NOT EXISTS idx_cap_sys_links_cap ON catalog_capability_system_links(capability_id);
CREATE INDEX IF NOT EXISTS idx_cap_sys_links_sys ON catalog_capability_system_links(system_id);

-- Stakeholder ↔ Capability
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

CREATE INDEX IF NOT EXISTS idx_stk_cap_links_stk ON catalog_stakeholder_capability_links(stakeholder_id);
CREATE INDEX IF NOT EXISTS idx_stk_cap_links_cap ON catalog_stakeholder_capability_links(capability_id);

-- Decision ↔ Capability
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

CREATE INDEX IF NOT EXISTS idx_dec_cap_links_dec ON catalog_decision_capability_links(decision_id);
CREATE INDEX IF NOT EXISTS idx_dec_cap_links_cap ON catalog_decision_capability_links(capability_id);

-- Decision ↔ Evidence
CREATE TABLE IF NOT EXISTS catalog_decision_evidence_links (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id       TEXT NOT NULL,
    decision_id     UUID NOT NULL REFERENCES catalog_decisions(id) ON DELETE CASCADE,
    evidence_id     UUID NOT NULL REFERENCES catalog_evidence(id) ON DELETE CASCADE,
    role_in_decision TEXT NOT NULL DEFAULT 'supporting'
        CHECK (role_in_decision IN ('supporting', 'contradicting', 'contextual', 'prerequisite')),
    weight          REAL NOT NULL DEFAULT 1.0,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE(tenant_id, decision_id, evidence_id, role_in_decision)
);

CREATE INDEX IF NOT EXISTS idx_dec_evi_links_dec ON catalog_decision_evidence_links(decision_id);
CREATE INDEX IF NOT EXISTS idx_dec_evi_links_evi ON catalog_decision_evidence_links(evidence_id);

-- Risk ↔ Evidence
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

CREATE INDEX IF NOT EXISTS idx_rsk_evi_links_rsk ON catalog_risk_evidence_links(risk_id);
CREATE INDEX IF NOT EXISTS idx_rsk_evi_links_evi ON catalog_risk_evidence_links(evidence_id);

-- Process ↔ Capability
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

CREATE INDEX IF NOT EXISTS idx_prs_cap_links_prs ON catalog_process_capability_links(process_id);
CREATE INDEX IF NOT EXISTS idx_prs_cap_links_cap ON catalog_process_capability_links(capability_id);

-- Policy ↔ Capability
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

CREATE INDEX IF NOT EXISTS idx_pol_cap_links_pol ON catalog_policy_capability_links(policy_id);
CREATE INDEX IF NOT EXISTS idx_pol_cap_links_cap ON catalog_policy_capability_links(capability_id);

-- Artifact ↔ Capability
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

CREATE INDEX IF NOT EXISTS idx_art_cap_links_art ON catalog_artifact_capability_links(artifact_id);
CREATE INDEX IF NOT EXISTS idx_art_cap_links_cap ON catalog_artifact_capability_links(capability_id);

-- Artifact ↔ Decision
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

CREATE INDEX IF NOT EXISTS idx_art_dec_links_art ON catalog_artifact_decision_links(artifact_id);
CREATE INDEX IF NOT EXISTS idx_art_dec_links_dec ON catalog_artifact_decision_links(decision_id);

-- Project ↔ Capability
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

CREATE INDEX IF NOT EXISTS idx_prj_cap_links_prj ON catalog_project_capability_links(project_id);
CREATE INDEX IF NOT EXISTS idx_prj_cap_links_cap ON catalog_project_capability_links(capability_id);

-- Stakeholder ↔ Decision
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

CREATE INDEX IF NOT EXISTS idx_stk_dec_links_stk ON catalog_stakeholder_decision_links(stakeholder_id);
CREATE INDEX IF NOT EXISTS idx_stk_dec_links_dec ON catalog_stakeholder_decision_links(decision_id);

-- =============================================
-- Access Control Tables
-- =============================================

CREATE TABLE IF NOT EXISTS catalog_roles (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id       TEXT NOT NULL,
    name            TEXT NOT NULL,
    description     TEXT,
    permissions     JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE(tenant_id, name)
);

CREATE TABLE IF NOT EXISTS catalog_role_assignments (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id       TEXT NOT NULL,
    role_id         UUID NOT NULL REFERENCES catalog_roles(id) ON DELETE CASCADE,
    user_id         TEXT NOT NULL,
    scope           JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE(tenant_id, role_id, user_id)
);

-- =============================================
-- Full-Text Search Index (PostgreSQL)
-- =============================================

-- Create a unified search view for cross-category search
CREATE OR REPLACE VIEW catalog_search_index AS
SELECT
    id, tenant_id, name, description, 'capability' as category,
    status, confidence, created_at, updated_at
FROM catalog_capabilities
UNION ALL
SELECT
    id, tenant_id, title as name, description, 'decision' as category,
    status, confidence, created_at, updated_at
FROM catalog_decisions
UNION ALL
SELECT
    id, tenant_id, name, description, 'process' as category,
    status, confidence, created_at, updated_at
FROM catalog_processes
UNION ALL
SELECT
    id, tenant_id, name, description, 'policy' as category,
    status, confidence, created_at, updated_at
FROM catalog_policies
UNION ALL
SELECT
    id, tenant_id, title as name, description, 'risk' as category,
    status, confidence, created_at, updated_at
FROM catalog_risks
UNION ALL
SELECT
    id, tenant_id, name, description, 'artifact' as category,
    status, confidence, created_at, updated_at
FROM catalog_artifacts
UNION ALL
SELECT
    id, tenant_id, name, NULL as description, 'stakeholder' as category,
    status, confidence, created_at, updated_at
FROM catalog_stakeholders
UNION ALL
SELECT
    id, tenant_id, title as name, description, 'evidence' as category,
    'active' as status, confidence, created_at, updated_at
FROM catalog_evidence
UNION ALL
SELECT
    id, tenant_id, name, description, 'system' as category,
    status, confidence, created_at, updated_at
FROM catalog_systems
UNION ALL
SELECT
    id, tenant_id, name, description, 'project' as category,
    status, confidence, created_at, updated_at
FROM catalog_projects;

-- Add GIN indexes for JSONB tag search on categories that need it
-- (Already added above for capabilities, policies, evidence, systems)

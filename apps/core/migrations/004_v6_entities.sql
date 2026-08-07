-- OntologyAI V6 — Entity Tables
-- Migration: 004
-- Date: 2026-07-27
-- This migration creates all V6 entity tables for the Decision Intelligence Platform.
-- Existing V5.2 tables remain unchanged for backward compatibility.

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
-- Workspace
-- =============================================
CREATE TABLE IF NOT EXISTS workspaces (
    id              TEXT PRIMARY KEY,
    tenant_id       TEXT NOT NULL,
    name            TEXT NOT NULL,
    purpose         TEXT,
    status          TEXT NOT NULL DEFAULT 'active' CHECK (status IN ('active', 'archived', 'closed')),
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_workspaces_tenant ON workspaces(tenant_id);
CREATE INDEX IF NOT EXISTS idx_workspaces_status ON workspaces(status);

DROP TRIGGER IF EXISTS trg_workspaces_updated_at ON workspaces;
CREATE TRIGGER trg_workspaces_updated_at
    BEFORE UPDATE ON workspaces
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

-- =============================================
-- DecisionWorkspace (V6: evolved workspace with decision state)
-- =============================================
CREATE TABLE IF NOT EXISTS decision_workspaces (
    id              TEXT PRIMARY KEY REFERENCES workspaces(id) ON DELETE CASCADE,
    current_phase   TEXT,
    approval_state  TEXT NOT NULL DEFAULT 'draft' CHECK (approval_state IN ('draft', 'in_review', 'approved', 'rejected')),
    active_decisions JSONB NOT NULL DEFAULT '[]'::jsonb,
    kpi_refs        JSONB NOT NULL DEFAULT '[]'::jsonb,
    history         JSONB NOT NULL DEFAULT '[]'::jsonb,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

DROP TRIGGER IF EXISTS trg_decision_workspaces_updated_at ON decision_workspaces;
CREATE TRIGGER trg_decision_workspaces_updated_at
    BEFORE UPDATE ON decision_workspaces
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

-- =============================================
-- Source
-- =============================================
CREATE TABLE IF NOT EXISTS sources (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id       TEXT NOT NULL,
    name            TEXT NOT NULL,
    source_type     TEXT NOT NULL,
    reliability     REAL NOT NULL DEFAULT 0.5 CHECK (reliability >= 0 AND reliability <= 1),
    status          TEXT NOT NULL DEFAULT 'active' CHECK (status IN ('active', 'degraded', 'disconnected')),
    config          JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_sources_tenant ON sources(tenant_id);
CREATE INDEX IF NOT EXISTS idx_sources_status ON sources(status);
CREATE INDEX IF NOT EXISTS idx_sources_type ON sources(source_type);

DROP TRIGGER IF EXISTS trg_sources_updated_at ON sources;
CREATE TRIGGER trg_sources_updated_at
    BEFORE UPDATE ON sources
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

-- =============================================
-- Stakeholder
-- =============================================
CREATE TABLE IF NOT EXISTS stakeholders (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id       TEXT NOT NULL,
    name            TEXT NOT NULL,
    email           TEXT,
    role            TEXT,
    status          TEXT NOT NULL DEFAULT 'identified' CHECK (status IN ('identified', 'engaged', 'at_risk', 'blocked')),
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_stakeholders_tenant ON stakeholders(tenant_id);
CREATE INDEX IF NOT EXISTS idx_stakeholders_status ON stakeholders(status);

DROP TRIGGER IF EXISTS trg_stakeholders_updated_at ON stakeholders;
CREATE TRIGGER trg_stakeholders_updated_at
    BEFORE UPDATE ON stakeholders
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

-- =============================================
-- OrgUnit
-- =============================================
CREATE TABLE IF NOT EXISTS org_units (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id       TEXT NOT NULL,
    name            TEXT NOT NULL,
    parent_id       UUID REFERENCES org_units(id) ON DELETE SET NULL,
    status          TEXT NOT NULL DEFAULT 'active' CHECK (status IN ('active', 'restructuring', 'dissolved')),
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_org_units_tenant ON org_units(tenant_id);
CREATE INDEX IF NOT EXISTS idx_org_units_parent ON org_units(parent_id);

DROP TRIGGER IF EXISTS trg_org_units_updated_at ON org_units;
CREATE TRIGGER trg_org_units_updated_at
    BEFORE UPDATE ON org_units
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

-- =============================================
-- System
-- =============================================
CREATE TABLE IF NOT EXISTS systems (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id       TEXT NOT NULL,
    name            TEXT NOT NULL,
    system_type     TEXT,
    status          TEXT NOT NULL DEFAULT 'live' CHECK (status IN ('live', 'sunset', 'migrating')),
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_systems_tenant ON systems(tenant_id);

DROP TRIGGER IF EXISTS trg_systems_updated_at ON systems;
CREATE TRIGGER trg_systems_updated_at
    BEFORE UPDATE ON systems
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

-- =============================================
-- Constraint
-- =============================================
CREATE TABLE IF NOT EXISTS constraints (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id       TEXT NOT NULL,
    description     TEXT NOT NULL,
    constraint_type TEXT,
    status          TEXT NOT NULL DEFAULT 'active' CHECK (status IN ('active', 'waived', 'removed')),
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_constraints_tenant ON constraints(tenant_id);
CREATE INDEX IF NOT EXISTS idx_constraints_status ON constraints(status);

DROP TRIGGER IF EXISTS trg_constraints_updated_at ON constraints;
CREATE TRIGGER trg_constraints_updated_at
    BEFORE UPDATE ON constraints
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

-- =============================================
-- KPI
-- =============================================
CREATE TABLE IF NOT EXISTS kpis (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id       TEXT NOT NULL,
    name            TEXT NOT NULL,
    target_value    REAL NOT NULL,
    baseline_value  REAL,
    unit            TEXT,
    owner_id        UUID REFERENCES stakeholders(id) ON DELETE SET NULL,
    status          TEXT NOT NULL DEFAULT 'baseline_set' CHECK (status IN ('baseline_set', 'tracking', 'met', 'missed')),
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_kpis_tenant ON kpis(tenant_id);
CREATE INDEX IF NOT EXISTS idx_kpis_owner ON kpis(owner_id);
CREATE INDEX IF NOT EXISTS idx_kpis_status ON kpis(status);

DROP TRIGGER IF EXISTS trg_kpis_updated_at ON kpis;
CREATE TRIGGER trg_kpis_updated_at
    BEFORE UPDATE ON kpis
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

-- =============================================
-- Project
-- =============================================
CREATE TABLE IF NOT EXISTS projects (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id       TEXT NOT NULL,
    name            TEXT NOT NULL,
    status          TEXT NOT NULL DEFAULT 'initiated' CHECK (status IN ('initiated', 'planning', 'executing', 'monitoring', 'closed')),
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_projects_tenant ON projects(tenant_id);
CREATE INDEX IF NOT EXISTS idx_projects_status ON projects(status);

DROP TRIGGER IF EXISTS trg_projects_updated_at ON projects;
CREATE TRIGGER trg_projects_updated_at
    BEFORE UPDATE ON projects
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

-- =============================================
-- Artifact
-- =============================================
CREATE TABLE IF NOT EXISTS artifacts (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id       TEXT NOT NULL,
    workspace_id    TEXT NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
    name            TEXT NOT NULL,
    artifact_type   TEXT NOT NULL,
    status          TEXT NOT NULL DEFAULT 'draft' CHECK (status IN ('draft', 'valid', 'published', 'superseded')),
    dsl_config_id   TEXT,
    content         JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_artifacts_tenant ON artifacts(tenant_id);
CREATE INDEX IF NOT EXISTS idx_artifacts_workspace ON artifacts(workspace_id);
CREATE INDEX IF NOT EXISTS idx_artifacts_status ON artifacts(status);
CREATE INDEX IF NOT EXISTS idx_artifacts_type ON artifacts(artifact_type);

DROP TRIGGER IF EXISTS trg_artifacts_updated_at ON artifacts;
CREATE TRIGGER trg_artifacts_updated_at
    BEFORE UPDATE ON artifacts
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

-- =============================================
-- ArtifactVersion
-- =============================================
CREATE TABLE IF NOT EXISTS artifact_versions (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    artifact_id     UUID NOT NULL REFERENCES artifacts(id) ON DELETE CASCADE,
    version_number  INT NOT NULL,
    content         JSONB NOT NULL,
    status          TEXT NOT NULL DEFAULT 'current' CHECK (status IN ('current', 'archived')),
    published_at    TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE(artifact_id, version_number)
);

CREATE INDEX IF NOT EXISTS idx_artifact_versions_artifact ON artifact_versions(artifact_id);

-- =============================================
-- ValidationResult
-- =============================================
CREATE TABLE IF NOT EXISTS validation_results (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    artifact_id     UUID REFERENCES artifacts(id) ON DELETE CASCADE,
    rule_id         TEXT NOT NULL,
    status          TEXT NOT NULL DEFAULT 'pending' CHECK (status IN ('pending', 'passed', 'failed', 'blocked')),
    details         TEXT,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_validation_results_artifact ON validation_results(artifact_id);
CREATE INDEX IF NOT EXISTS idx_validation_results_status ON validation_results(status);

-- =============================================
-- FeasibilityScore
-- =============================================
CREATE TABLE IF NOT EXISTS feasibility_scores (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    option_id       TEXT NOT NULL,
    dimensions      JSONB NOT NULL DEFAULT '{}'::jsonb,
    weighted_total  REAL NOT NULL,
    readiness_tier  TEXT NOT NULL CHECK (readiness_tier IN ('publish', 'caveat', 'review', 'block')),
    computed_at     TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_feasibility_scores_option ON feasibility_scores(option_id);

-- =============================================
-- AuditEvent
-- =============================================
CREATE TABLE IF NOT EXISTS audit_events (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id       TEXT NOT NULL,
    entity_type     TEXT NOT NULL,
    entity_id       TEXT NOT NULL,
    action          TEXT NOT NULL,
    actor_id        TEXT,
    details         JSONB NOT NULL DEFAULT '{}'::jsonb,
    timestamp       TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_audit_events_tenant ON audit_events(tenant_id);
CREATE INDEX IF NOT EXISTS idx_audit_events_entity ON audit_events(tenant_id, entity_type, entity_id);
CREATE INDEX IF NOT EXISTS idx_audit_events_timestamp ON audit_events(tenant_id, timestamp);

-- =============================================
-- WorkspaceEntity (join table)
-- =============================================
CREATE TABLE IF NOT EXISTS workspace_entities (
    workspace_id    TEXT NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
    entity_id       TEXT NOT NULL,
    entity_type     TEXT NOT NULL,
    added_at        TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (workspace_id, entity_id)
);

CREATE INDEX IF NOT EXISTS idx_workspace_entities_type ON workspace_entities(entity_type);

-- =============================================
-- Policy
-- =============================================
CREATE TABLE IF NOT EXISTS policies (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id       TEXT NOT NULL,
    name            TEXT NOT NULL,
    rule_expression TEXT NOT NULL,
    severity        TEXT NOT NULL DEFAULT 'block' CHECK (severity IN ('block', 'warn', 'info')),
    applies_to      TEXT,
    status          TEXT NOT NULL DEFAULT 'active' CHECK (status IN ('active', 'superseded', 'deprecated')),
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_policies_tenant ON policies(tenant_id);
CREATE INDEX IF NOT EXISTS idx_policies_status ON policies(status);
CREATE INDEX IF NOT EXISTS idx_policies_applies_to ON policies(applies_to);

DROP TRIGGER IF EXISTS trg_policies_updated_at ON policies;
CREATE TRIGGER trg_policies_updated_at
    BEFORE UPDATE ON policies
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

-- =============================================
-- WorkflowDefinition (workflow versioning)
-- =============================================
CREATE TABLE IF NOT EXISTS workflow_definitions (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name            TEXT NOT NULL,
    version         INT NOT NULL,
    definition      JSONB NOT NULL,
    status          TEXT NOT NULL DEFAULT 'active' CHECK (status IN ('active', 'deprecated', 'retired')),
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE(name, version)
);

CREATE INDEX IF NOT EXISTS idx_workflow_definitions_name ON workflow_definitions(name);
CREATE INDEX IF NOT EXISTS idx_workflow_definitions_status ON workflow_definitions(status);

DROP TRIGGER IF EXISTS trg_workflow_definitions_updated_at ON workflow_definitions;
CREATE TRIGGER trg_workflow_definitions_updated_at
    BEFORE UPDATE ON workflow_definitions
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

-- =============================================
-- ConnectorManifest (stored state per tenant)
-- =============================================
CREATE TABLE IF NOT EXISTS connector_manifests (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id       TEXT NOT NULL,
    connector_name  TEXT NOT NULL,
    manifest        JSONB NOT NULL,
    last_sync_at    TIMESTAMPTZ,
    status          TEXT NOT NULL DEFAULT 'connected' CHECK (status IN ('connected', 'disconnected', 'error')),
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE(tenant_id, connector_name)
);

CREATE INDEX IF NOT EXISTS idx_connector_manifests_tenant ON connector_manifests(tenant_id);
CREATE INDEX IF NOT EXISTS idx_connector_manifests_status ON connector_manifests(status);

DROP TRIGGER IF EXISTS trg_connector_manifests_updated_at ON connector_manifests;
CREATE TRIGGER trg_connector_manifests_updated_at
    BEFORE UPDATE ON connector_manifests
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

-- =============================================
-- Entity confidence table (derived from evidence)
-- =============================================
CREATE TABLE IF NOT EXISTS entity_confidence (
    entity_id       TEXT NOT NULL,
    entity_type     TEXT NOT NULL,
    tenant_id       TEXT NOT NULL,
    confidence      REAL NOT NULL DEFAULT 0.0 CHECK (confidence >= 0 AND confidence <= 1),
    confidence_history JSONB NOT NULL DEFAULT '[]'::jsonb,
    last_updated    TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (entity_id, entity_type)
);

CREATE INDEX IF NOT EXISTS idx_entity_confidence_tenant ON entity_confidence(tenant_id);
CREATE INDEX IF NOT EXISTS idx_entity_confidence_level ON entity_confidence(confidence);

-- =============================================
-- Enterprise Knowledge Model — interpreted business state
-- =============================================
CREATE TABLE IF NOT EXISTS enterprise_knowledge (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id       TEXT NOT NULL,
    entity_id       TEXT NOT NULL,
    entity_type     TEXT NOT NULL,
    interpreted_state JSONB NOT NULL DEFAULT '{}'::jsonb,
    confidence      REAL NOT NULL DEFAULT 0.0,
    source_evidence_ids JSONB NOT NULL DEFAULT '[]'::jsonb,
    version         INT NOT NULL DEFAULT 1,
    valid_from      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    valid_to        TIMESTAMPTZ,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_enterprise_knowledge_tenant ON enterprise_knowledge(tenant_id);
CREATE INDEX IF NOT EXISTS idx_enterprise_knowledge_entity ON enterprise_knowledge(entity_id, entity_type);
CREATE INDEX IF NOT EXISTS idx_enterprise_knowledge_valid ON enterprise_knowledge(valid_from, valid_to);

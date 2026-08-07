// OntologyAI V6 — Neo4j Schema Initialization
// Run once at database creation via docker-compose volume mount.

// ── Constraints (uniqueness) ──────────────────────────────────────────
// Entity nodes are identified by ULID (id). Source type + external_id
// ensures we never double-create the same business entity.

CREATE CONSTRAINT entity_id_unique IF NOT EXISTS
FOR (n:Entity) REQUIRE n.id IS UNIQUE;

CREATE CONSTRAINT evidence_id_unique IF NOT EXISTS
FOR (n:Evidence) REQUIRE n.id IS UNIQUE;

CREATE CONSTRAINT stakeholder_id_unique IF NOT EXISTS
FOR (n:Stakeholder) REQUIRE n.id IS UNIQUE;

CREATE CONSTRAINT capability_id_unique IF NOT EXISTS
FOR (n:Capability) REQUIRE n.id IS UNIQUE;

CREATE CONSTRAINT process_id_unique IF NOT EXISTS
FOR (n:Process) REQUIRE n.id IS UNIQUE;

CREATE CONSTRAINT requirement_id_unique IF NOT EXISTS
FOR (n:Requirement) REQUIRE n.id IS UNIQUE;

CREATE CONSTRAINT business_rule_id_unique IF NOT EXISTS
FOR (n:BusinessRule) REQUIRE n.id IS UNIQUE;

CREATE CONSTRAINT assumption_id_unique IF NOT EXISTS
FOR (n:Assumption) REQUIRE n.id IS UNIQUE;

CREATE CONSTRAINT risk_id_unique IF NOT EXISTS
FOR (n:Risk) REQUIRE n.id IS UNIQUE;

CREATE CONSTRAINT decision_id_unique IF NOT EXISTS
FOR (n:Decision) REQUIRE n.id IS UNIQUE;

CREATE CONSTRAINT option_id_unique IF NOT EXISTS
FOR (n:Option) REQUIRE n.id IS UNIQUE;

CREATE CONSTRAINT conflict_id_unique IF NOT EXISTS
FOR (n:Conflict) REQUIRE n.id IS UNIQUE;

CREATE CONSTRAINT workspace_id_unique IF NOT EXISTS
FOR (n:Workspace) REQUIRE n.id IS UNIQUE;

// ── Indexes (performance) ────────────────────────────────────────────

CREATE INDEX entity_type_index IF NOT EXISTS
FOR (n:Entity) ON (n.type);

CREATE INDEX evidence_tenant_index IF NOT EXISTS
FOR (n:Evidence) ON (n.tenant_id);

CREATE INDEX evidence_source_index IF NOT EXISTS
FOR (n:Evidence) ON (n.source);

CREATE INDEX evidence_timestamp_index IF NOT EXISTS
FOR (n:Evidence) ON (n.timestamp);

CREATE INDEX decision_status_index IF NOT EXISTS
FOR (n:Decision) ON (n.status);

CREATE INDEX risk_severity_index IF NOT EXISTS
FOR (n:Risk) ON (n.severity);

CREATE INDEX stakeholder_tenant_index IF NOT EXISTS
FOR (n:Stakeholder) ON (n.tenant_id);

// ── Full-text indexes ─────────────────────────────────────────────────

CREATE FULLTEXT INDEX entity_text_index IF NOT EXISTS
FOR (n:Entity) ON EACH [n.name, n.description];

CREATE FULLTEXT INDEX evidence_content_index IF NOT EXISTS
FOR (n:Evidence) ON EACH [n.raw_content];

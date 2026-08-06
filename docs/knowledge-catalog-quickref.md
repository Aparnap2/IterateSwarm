# Knowledge Catalog — Quick Reference

## 10 Categories

| # | Category | Table | Key Fields | Status Enum |
|---|----------|-------|------------|-------------|
| 1 | Capabilities | `catalog_capabilities` | maturity_level, domain, parent_id | draft/active/archived/deprecated |
| 2 | Decisions | `catalog_decisions` | decision_type, rationale, alternatives | proposed/in_review/approved/rejected/implemented/superseded |
| 3 | Processes | `catalog_processes` | process_type, frequency, steps, inputs/outputs | draft/active/archived/deprecated |
| 4 | Policies | `catalog_policies` | policy_type, severity, rule_expression, enforcement | draft/active/superseded/deprecated |
| 5 | Risks | `catalog_risks` | risk_category, likelihood, impact, risk_score | identified/assessed/mitigating/mitigated/accepted/closed/realized |
| 6 | Artifacts | `catalog_artifacts` | artifact_category, producer, content_ref | draft/review/published/superseded |
| 7 | Stakeholders | `catalog_stakeholders` | expertise_areas, responsibility_areas, department | active/inactive/on_leave/departed |
| 8 | Evidence | `catalog_evidence` | evidence_type, source_id, reliability, expires_at | collected/validated/stale/disputed |
| 9 | Systems | `catalog_systems` | system_type, vendor, data_class, integrations | active/planned/sunset/decommissioned/migrating |
| 10 | Projects | `catalog_projects` | project_type, budget, progress_pct, goals/outcomes | initiated/planning/executing/completed/cancelled |

## 11 Cross-Category Link Tables

| Link | Source | Target | Relationship Types |
|------|--------|--------|-------------------|
| capability_system | Capability | System | depends_on, supports, replaced_by, integrates_with |
| stakeholder_capability | Stakeholder | Capability | owner, lead, participant, reviewer, adviser |
| decision_capability | Decision | Capability | affects, creates, modifies, deprecates |
| decision_evidence | Decision | Evidence | supporting, contradicting, contextual, prerequisite |
| risk_evidence | Risk | Evidence | supporting, mitigating, contradicting, contextual |
| process_capability | Process | Capability | implements, supports, depends_on |
| policy_capability | Policy | Capability | mandatory, advisory, optional |
| artifact_capability | Artifact | Capability | documents, specifies, analyzes, depicts |
| artifact_decision | Artifact | Decision | supports, informs, supersedes |
| project_capability | Project | Capability | improves, creates, modifies, deprecates, replaces |
| stakeholder_decision | Stakeholder | Decision | decision_maker, reviewer, participant, informed |

## Common Query Patterns

### "What decisions were made about our sales capability this quarter?"
```sql
SELECT d.* FROM catalog_decisions d
JOIN catalog_decision_capability_links dc ON d.id = dc.decision_id
JOIN catalog_capabilities c ON dc.capability_id = c.id
WHERE c.domain = 'Sales'
  AND d.decision_date >= '2026-04-01'
  AND d.decision_date < '2026-07-01';
```

### "Show me all evidence supporting the risk that GlobalTech might churn"
```sql
SELECT e.* FROM catalog_evidence e
JOIN catalog_risk_evidence_links re ON e.id = re.evidence_id
JOIN catalog_risks r ON re.risk_id = r.id
WHERE r.title ILIKE '%churn%'
  AND re.role_in_risk = 'supporting';
```

### "What artifacts were generated for the Customer Portal project?"
```sql
SELECT a.* FROM catalog_artifacts a
WHERE a.project_id = (SELECT id FROM catalog_projects WHERE name = 'Customer Portal');
```

### "Which stakeholders are involved in the authentication capability?"
```sql
SELECT s.* FROM catalog_stakeholders s
JOIN catalog_stakeholder_capability_links sc ON s.id = sc.stakeholder_id
JOIN catalog_capabilities c ON sc.capability_id = c.id
WHERE c.name = 'Authentication';
```

### "What policies apply to our data processing pipeline?"
```sql
SELECT p.* FROM catalog_policies p
WHERE p.applies_to @> '["data_processing"]'
  AND p.status = 'active';
```

## API Endpoints

```
GET    /api/v1/catalog/{category}                    # List
GET    /api/v1/catalog/{category}/{id}               # Get
POST   /api/v1/catalog/{category}                    # Create
PUT    /api/v1/catalog/{category}/{id}               # Update
DELETE /api/v1/catalog/{category}/{id}               # Delete

GET    /api/v1/catalog/search?q=...                  # Search
GET    /api/v1/catalog/{category}/relationships/{id} # Relationships
GET    /api/v1/catalog/graph/{category}/{id}         # Graph
```

## Files

| File | Purpose |
|------|---------|
| `apps/core/migrations/011_knowledge_catalog.sql` | SQL schema (10 tables + 11 link tables) |
| `apps/ai/src/schemas/knowledge_catalog.py` | Python Pydantic models |
| `docs/ADR-006-knowledge-catalog.md` | Architecture Decision Record |

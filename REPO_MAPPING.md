# OntologyAI V6 — Repo → Spec Mapping

**Status:** Phase 1 (grounded audit, contextscout)
**Branch base:** `feat/v5.2-architectural-cleanup`
**Spec inputs:** `V6_DOMAIN_SPEC.md`, `PLAN_V6.md`, `CAPABILITY_ONTOLOGY_V6.md`

Verdict per file: **Preserve** (reuse) · **Refactor** (adapt) · **Replace** · **Remove**.

---

## 1. Connectors

| File | Verdict | Note |
|------|---------|------|
| `connectors/v6_contract.py` | **Preserve** | V6Connector Protocol + ConnectorManifest/SyncStrategy/Capability. |
| `connectors/v6_base.py` | **Preserve** | BaseV6Connector ABC, HttpxTransport injection, `_build_evidence`. |
| `connectors/transport.py` | **Preserve** | HttpxTransport (retry/backoff) + MockTransport. |
| `connectors/sync_state.py` | **Preserve** | ConnectorSyncState + SyncStateStore (cursor/etag/backoff). |
| `connectors/registry.py` | **Preserve** | V6ConnectorRegistry register/run_all. |
| `connectors/notion.py` (:3001), `slack_v6.py` (:3002), `jira.py` (:3003), `salesforce_v6.py` (:3004) | **Preserve** | All import `EvidenceRecord` from `src/entities/models.py` (V6 canonical). |
| `connectors/mock_notion_connector.py` + `_test_constants.py` | **Preserve** | Deterministic test evidence. |
| `connectors/base.py` (V5.2 ABC + ConnectorConfig) | **Refactor** | Deprecate unless legacy consumers remain. |
| `connectors/__init__.py` | **Refactor** | Re-export V6 connectors; gate V5.2 registry. |

## 2. Schemas

| File | Verdict | Note |
|------|---------|------|
| `entities/models.py` + `entities/__init__.py` | **Preserve** | **Single source of truth**: 24 entities + canonical `EvidenceRecord` + `Provenance` (`extra=forbid`, `strict`, `from_attributes`). |
| `schemas/semantic_layer.py` | **Preserve** | CanonicalEntity, EntityAlias, EntityLineage, AttributeConflict, ResolutionTier, ConflictStatus. |
| `schemas/capability.py` | **Preserve** | Capability, CapabilityRelationship. |
| `schemas/knowledge_catalog.py` | **Preserve** | CatalogCapability/Decision/Risk/Relationship. |
| `schemas/ba_artifact.py`, `strategy_artifacts.py`, `engagement_state.py`, `specialist_response.py` | **Preserve** | V5.2 canonical contracts. |
| `schemas/__init__.py` | **Refactor** | ⚠️ Exports `semantic_layer` but omits `capability` + `knowledge_catalog`. Add `Capability`, `CapabilityRelationship`, `KnowledgeCatalogEntry` to imports+`__all__`. |

## 3. Pipeline

| File | Verdict | Note |
|------|---------|------|
| `pipeline/artifact_engine.py` | **Preserve** | Deterministic exec-brief projection. ⚠️ existing LLM call site (audit in P5). |
| `pipeline/decision_engine.py` | **Preserve** | ULID decision/option IDs, A/B options. Deterministic. |
| `pipeline/feasibility_engine.py` | **Preserve** | 8-dim weighted scoring; tiers Publish≥85/Caveats70-84/Review60-69/Block<60. |
| `pipeline/validation_engine.py` | **Preserve** | Rules V001-V008. |
| `pipeline/vertical_slice.py` | **Refactor** | 10 stages vs 14 spec. Missing: evidence-store persistence, conflict detection, graph enrichment (real Neo4j), artifact versioning. Stage 1 holds evidence in-memory. |
| `knowledge/entity_resolver.py` | **Refactor** | Levenshtein >0.85 + **hardcoded** extraction (Interview→Sarah Chen etc.) — must become data-driven. |
| `knowledge/graph_builder.py` | **Refactor** | `neo4j_available` flag + **in-memory fallback**; real path thin. |
| `knowledge/enterprise_knowledge_model.py` | **Refactor** | **in-memory dict fallback**; needs Postgres-backed persistence. |
| `knowledge/conflict_resolver.py` | **Preserve** | Source-of-truth hierarchy per entity type. |
| `knowledge/semantic_layer.py` + `connector_bridge.py` | **Preserve** (unwire→wire) | Proper 5-tier resolution (EXACT/FUZZY/ATTRIBUTE/RELATIONSHIP/LLM_ASSISTED). ⚠️ NOT wired into pipeline. Tier-5 stub. |
| `context/agent_context.py` | **Preserve** | 8-layer, 32K budget. |

## 4. Artifacts

| File | Verdict | Note |
|------|---------|------|
| `artifacts/dsl_loader.py` | **Preserve** | ArtifactDSL, ArtifactSection, 15 section types. |
| `artifacts/template_engine.py` | **Preserve** | Jinja2 SandboxedEnvironment. |
| `artifacts/projection_engine.py` | **Preserve** | project("executive-decision-brief", ...). |
| `artifacts/registry/executive_brief.yaml` | **Preserve** | 7 sections; `llm_augment` flags. |

## 5. Infra

| File | Verdict | Note |
|------|---------|------|
| `config/neo4j/init.cypher` | **Refactor** | ⚠️ 13 constraints (not 24). Reconcile with ontology + add constraint-count test. |
| `scripts/setup_qdrant_collections.py` | **Preserve** | Qdrant 768-dim collections. |
| `apps/core/migrations/004_v6_entities.sql` | **Preserve** | 20 V6 tables + updated_at trigger. |
| `apps/core/migrations/011_knowledge_catalog.sql` | **Preserve** | 10-category catalog + GIN indexes. |
| `temporal/queues.py` | **Preserve** | 3 queues defined (PIPELINE/AGENT/VALIDATION). |
| `worker.py` | **Refactor** | ⚠️ still single legacy `ONTOLOGYAI-MAIN-QUEUE`. Wire 3 queues + activity boundaries early. |

## 6. Mockoon (Highest Operational Risk)

| Mechanism | Current | Target |
|-----------|---------|--------|
| `scripts/start-mockoon.sh` | single cli on :3000, wrong config | cli per-config on :3001-:3004 + health loop |
| `scripts/stop-mockoon.sh` | kills `:3000` only | kill all 4 |
| Makefile `mock-up` (`:8097-9`) | Docker mockoon | ⚠️ **retire per V6 directive (cli, not docker)** |
| `tests/integration/conftest.py` | cli on :3333 | ⚠️ retire/redirect to :3001-:3004 |
| `mockoon/*.json` | :3001-:3004 | **Preserve** — correct per-connector configs |

---

## Key Decisions (from review)

- **Standardize Silver** on `semantic_layer` + `connector_bridge` (data-driven, 5-tier); retire `entity_resolver` hardcoded extraction **before P6**.
- **Evidence store (Bronze)** = append-only Postgres + `hash` dedup; make it a real Stage 1 (not in-memory list).
- **LLM rule:** LLM→JSON→Pydantic→Canonical Model. LLM never writes graph/decision/evidence stores directly; only read-model or low-confidence human-review candidate.
- **Temporal:** land queue routing + activity boundaries early; prove replay via Temporal test framework in P4; defer `continueAsNew` tuning to after P5.
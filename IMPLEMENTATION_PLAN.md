# OntologyAI V6 — Implementation Plan (Risk-First)

**Status:** Phase 1 → Active
**Owner:** Principal Implementation Agent
**Review verdict:** 7/10 APPROVE WITH CONDITIONS (architect-reviewer). 5 smallest-safe first actions adopted.

Execution is **risk-reduction-first**, not feature-first:
> Prove the architecture survives real data and stays deterministic with a real LLM **before** wiring additional entity breadth.

---

## Execution Workstreams

| # | Phase | Workstream | Risk De-risked | Status |
|---|-------|-----------|----------------|--------|
| P1 | Mapping | REPO_MAPPING.md / IMPLEMENTATION_PLAN.md / RISK_REGISTER.md | — | ✅ |
| P2 | Dev Env | **WS-P1** Mockoon Docker→cli on :3001-:3004, health checks, fixture versioning; schema `__init__` fix; queue routing + activity boundaries | R-01, R-08, R-06, R-02 | ▶️ |
| P3 | Connector Validation | **WS-P2** 4 connectors = 100% deterministic integration tests (pagination/retry/rate-limit/auth/malformed/dupe/checkpoint); build+wire evidence store (Bronze) | R-02, R-10 | ⏳ |
| P4 | Real Infra | **WS-P5(part)** Neo4j+Postgres+Qdrant real containers; graph traversal, vector search, tx boundaries, tenant isolation, replay via Temporal test framework; reconcile init.cypher (13→24); persistence-asserted tests | R-04, R-07, R-06 | ⏳ |
| P5 | Real LLM | **WS-P3** Groq llama-3.3-70b; parse/extract/summarize/narrate only; LLM→JSON→Pydantic→Canonical; gate against `artifact_engine`/`relevance_gate` leaks | R-05 | ⏳ |
| P5.5 | Knowledge Pipeline Validation | Medallion Bronze→Silver→Gold; dupe/out-of-order/stale/conflict/missing-FK/partial-failure/replay/idempotent/tenant-isolation; unify Silver on `semantic_layer`; add conflict stage | R-03, R-09 | ⏳ |
| P6 | Entity Wiring | **WS-P4** CanonicalEntity+EntityAlias+Capability+CapabilityRelationship+KnowledgeCatalogEntry through Evidence→Entity→Graph→Workspace→Artifact | R-03 | ⏳ |
| P7 | Production Validation | **WS-P5** Connector→Bronze→Silver→Gold→KG→Decision→Artifact on real infra; QA golden datasets | — | ⏳ |

---

## Subagent Plan

| Agent | Role | Workstream |
|-------|------|-----------|
| **1 Repository Architect** | Preserve/Refactor/Replace/Remove map | P1 (done, contextscout) |
| **2 Infrastructure Engineer** | Mockoon cli, Neo4j, Qdrant, Postgres, Temporal queues | WS-P1, P4 |
| **3 Connector Engineer** | Salesforce/Slack/Jira/Notion determinism | WS-P2 |
| **4 Knowledge Engineer** | Ontology, entities, relationships, Neo4j | P5.5, WS-P4 |
| **5 LLM Engineer** | Groq structured outputs, Pydantic, prompt contracts, retry | WS-P3 |
| **6 Workflow Engineer** | Temporal activities, state, replay | P4, P5.5 |
| **7 QA Engineer** | Golden datasets, property tests, regression | WS-P5 |
| **8 Release Engineer** | GitHub issues, PRs, CI, changelog | All |

---

## Smallest-Safe First Actions (adopted from review)

1. Fix `schemas/__init__.py` — export `Capability`, `CapabilityRelationship`, `KnowledgeCatalogEntry`.
2. Rewrite `start-mockoon.sh`/`stop-mockoon.sh` — cli on :3001-:3004 + per-port health loop; retire Makefile Docker targets + `:3000`/`:3333` paths.
3. Add append-only evidence store (Bronze, Postgres, `hash`-dedup); make it real Stage 1.
4. Reconcile `config/neo4j/init.cypher` (13→24) + constraint-count test.
5. Add persistence-asserted tests (query back store after write).

---

## Verification Gates (no phase done without these)

- **Static:** ruff, mypy, dead-code, import cycles, secrets scan
- **Unit:** domain, entities, pipeline, validation
- **Integration:** connectors, Neo4j, Qdrant, Postgres, Temporal
- **Workflow:** replay, retry, pause/resume, DLQ
- **AI:** golden datasets, schema adherence, hallucination, determinism, cost
- **Release:** OpenAPI, docker-compose, dev bootstrap, README, ADRs

---

## Definition of Done

Spec-conformant · reuses existing code · has tests (TDD) · passes verification ·
documented · committed atomically · tracked in GitHub · safe to merge.
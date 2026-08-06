# OntologyAI V6 — Implementation Plan (Risk-First)

**Status:** Phase 1 → Active
**Owner:** Principal Implementation Agent
**Review verdict:** 7/10 APPROVE WITH CONDITIONS (architect-reviewer). 5 smallest-safe first actions adopted.

> **V6 Frozen 9-Runtime Model (see `docs/v6-runtime-architecture.md` v2.0):** The target architecture is the **Enterprise Decision Runtime** — 5 layers (Observe → Understand → Decide → Act → Learn), **9 Runtimes** (Evidence, Knowledge, Decision Context, Policy, Workspace, Action, Simulation, Learning, reserved), and agents are an implementation detail inside runtimes. This supersedes the "Shared Platform Agent + 5 Skills" framing in `PLAN_V6.md` ADR-004 and the V5.2 agent roster. The execution workstreams below remain valid; they now build toward the 9-runtime model. Key additions: the **Decision Context Runtime** (minimal high-signal context per decision, `docs/decision-context-runtime.md`), the **Policy Runtime** (deterministic gate: Validation → Policy → Governance → Execution), and the **Simulation Runtime** (placeholder — executive what-if). Governance is a deterministic policy gate, not an agent; the Execution agent never reasons.

Execution is **risk-reduction-first**, not feature-first:
> Prove the architecture survives real data and stays deterministic with a real LLM **before** wiring additional entity breadth.

---

## Execution Workstreams

| # | Phase | Workstream | Risk De-risked | Status |
|---|-------|-----------|----------------|--------|
| P1 | Mapping | **WS-ARCH** (Platform Runtime Freeze) — FastAPI, Temporal, Redpanda, Retry, DLQ, Circuit Breaker, Governance, Observability, Connector SDK, Workspace Store, Evidence SDK, Validation Framework frozen; never rewrite | — | ✅ |
| P2 | Dev Env | **WS-EVIDENCE** (Evidence Runtime) — Mockoon Docker→cli on :3001-:3004, health checks, fixture versioning; Evidence Runtime stages Ingest→Gap; evidence store (Bronze); schema `__init__` fix; queue routing + activity boundaries | R-01, R-08, R-06, R-02 | ▶️ |
| P3 | Connector Validation | **WS-KNOWLEDGE** (Knowledge Runtime) — 4 connectors = 100% deterministic integration tests (pagination/retry/rate-limit/auth/malformed/dupe/checkpoint); build+wire evidence store (Bronze); Entity Resolver, Ontology Mapper, Conflict Detector, Capability Mapper | R-02, R-10 | ⏳ |
| P4 | Real Infra | **WS-CONTEXT** (Decision Context Runtime) — Neo4j+Postgres+Qdrant real containers; graph traversal, vector search, tx boundaries, tenant isolation, replay via Temporal test framework; reconcile init.cypher (13→24); persistence-asserted tests; Decision Context Runtime assembly algorithm | R-04, R-07, R-06 | ⏳ |
| P5 | Real LLM | **WS-DECISION** (Decision Runtime) — Groq llama-3.3-70b; parse/extract/summarize/narrate only; LLM→JSON→Pydantic→Canonical; gate against `artifact_engine`/`relevance_gate` leaks; Decision agent + Feasibility engine + Autonomy classifier | R-05 | ⏳ |
| P5.5 | Knowledge Pipeline Validation | Medallion Bronze→Silver→Gold; dupe/out-of-order/stale/conflict/missing-FK/partial-failure/replay/idempotent/tenant-isolation; unify Silver on `semantic_layer`; add conflict stage | R-03, R-09 | ⏳ |
| P6 | Entity Wiring | **WS-WORKSPACE** (Workspace Runtime) — CanonicalEntity+EntityAlias+Capability+CapabilityRelationship+KnowledgeCatalogEntry through Evidence→Entity→Graph→Workspace→Artifact; Artifact DSL projection; validation orchestration (V001–V008); SSEHub fan-out | R-03 | ⏳ |
| P7 | Production Validation | Connector→Bronze→Silver→Gold→KG→Decision→Policy Gate→Workspace→Artifact on real infra; QA golden datasets | — | ⏳ |
| P8 | Policy Runtime | **WS-POLICY** (Policy Runtime — placeholder) — Basic approval rules; autonomy-by-risk (Low/Medium/High); tier recomputed in gate; `AuditEvent` per action; High-risk denylist | — | ⏳ |
| P9 | Simulation Runtime | **WS-SIMULATION** (Simulation Runtime — placeholder) — Executive what-if "what happens if..." scenario simulation; placeholder interface only | — | ⏳ |
| P10 | Learning Runtime | **WS-LEARNING** (Learning Runtime — placeholder) — Metrics + outcome logging; Continuous Decision Monitoring; drift detection; placeholder interface only | — | ⏳ |
| P11 | Action Runtime | **WS-ACTION** (Action Runtime — placeholder/draft) — Draft actions, no real side effects; zero-LLM action path; typed payloads | — | ⏳ |

---

## Subagent Plan

| Agent | Role | Workstream |
|-------|------|-----------|
| **1 Repository Architect** | Preserve/Refactor/Replace/Remove map | P1 (done, contextscout) |
| **2 Infrastructure Engineer** | Mockoon cli, Neo4j, Qdrant, Postgres, Temporal queues | WS-EVIDENCE, P4 |
| **3 Connector Engineer** | Salesforce/Slack/Jira/Notion determinism | WS-KNOWLEDGE |
| **4 Knowledge Engineer** | Ontology, entities, relationships, Neo4j | P5.5, WS-WORKSPACE |
| **5 LLM Engineer** | Groq structured outputs, Pydantic, prompt contracts, retry | WS-DECISION |
| **6 Workflow Engineer** | Temporal activities, state, replay | P4, P5.5 |
| **7 QA Engineer** | Golden datasets, property tests, regression | WS-ACTION |
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

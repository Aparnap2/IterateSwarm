# ADR-009: Platform Runtime Architecture Freeze

**Status:** ACCEPTED (frozen)
**Date:** 2026-08-06
**Deciders:** Architecture Team
**Technical Story:** Freeze the platform infrastructure stack for the V6 9-runtime Enterprise Decision Runtime so that implementation conforms and the architecture does not change from this point.

---

## Context

The V6 architecture is the **Enterprise Decision Runtime** — a closed loop of five layers (Observe → Understand → Decide → Act → Learn) realized as **9 Runtimes** (Evidence, Knowledge, Decision Context, Decision, Simulation, Policy, Workspace, Action, Learning). The 9-runtime model is already frozen in `docs/v6-runtime-architecture.md` (v2.0).

What remained open was the **platform infrastructure** on which the runtimes execute: compute runtime, workflow engine, streaming, object storage, relational store, analytics, graph, vector, search, AI providers, OCR, monitoring, feature flags, auth, and email. Multiple candidate components had been evaluated (e.g., Cloud Workflows vs Temporal, Pub/Sub vs Redpanda, GCS vs R2, Qdrant vs pgvector, MinIO, Spark, Cloud SQL). The team has now made a definitive platform decision that must be frozen so that implementation conforms and no further platform churn occurs.

This ADR records that decision and the boundaries that govern it.

---

## Decision

The platform infrastructure stack is **frozen** as follows. Production runs on **Google Cloud** with managed services; local development is **free (no cloud spend)** and mirrors production through **MiniSky** as the local GCP control plane.

### Production (Google Cloud)

| Concern | Component | Notes |
|---|---|---|
| Runtime | **Cloud Run** | Serverless containers; FastAPI API |
| API | **FastAPI** | Preserved core |
| Workflow | **Temporal** | NOT Cloud Workflows; 3 queues + retry/DLQ/idempotency + `continueAsNew` |
| Streaming | **Redpanda** | NOT Pub/Sub — code already uses it |
| Object storage | **Cloudflare R2** | NOT GCS; GCS supported later via adapter |
| Relational (OLTP) | **Neon PostgreSQL** | Transactional system of record |
| Analytics | **BigQuery Sandbox** | Analytics/KPI/historical reporting/dashboards ONLY — never the app DB |
| Graph | **Neo4j Aura** | Never self-host in prod |
| Vector | **pgvector** (primary) | Qdrant REMOVED for MVP; optional later behind the same interface if a dedicated vector-engine comparison is needed |
| Search | **Enterprise Retrieval** | BM25 + pgvector + Neo4j traversal + metadata filters + reranking |
| AI | **Gemini, Groq, OpenRouter** | OpenRouter as fallback |
| OCR | **Sarvam OCR**, Docling fallback | |
| Monitoring | **OpenTelemetry → Langfuse → Sentry** | Cloud Monitoring optional |
| Feature flags | **Flagsmith** | |
| Auth | **Better Auth** | |
| Email | **Resend** | |

### Local Development (MiniSky + Docker + Mockoon)

Free, no cloud spend. Everything through `localhost:8080` exactly like production.

| Component | Local | Notes |
|---|---|---|
| GCP control plane | **MiniSky** | Already running: API gateway `http://localhost:8080`, console `http://localhost:8081`. Emulates Cloud Storage, Pub/Sub, BigQuery, IAM, LRO, Cloud Run API |
| Docker Compose (non-GCP) | **Neo4j, Postgres, Temporal, Redpanda, Redis, Langfuse** | NOT MinIO (MiniSky covers local GCS); NOT Qdrant (pgvector primary) |
| SaaS mocks | **Mockoon** (cli, ports 3001–3004) | Mocks Slack/Jira/Salesforce/Notion |

**Explicitly removed from the stack:** MinIO, Qdrant (MVP), Spark, Cloud SQL, Cloud Workflows. The transformation engine is abstracted — it may be backed by Polars (preferred) or Spark (very large datasets only) later.

---

## Runtime Boundaries

The **9 Runtimes** are the ownership boundaries of the architecture. Runtimes map to Temporal queues and deterministic workers. **Agents are an implementation detail** inside runtimes — they are not architectural boundaries.

| # | Runtime | Layer | Determinism |
|---|---------|-------|-------------|
| R1 | Evidence Runtime | Observe | Deterministic except Parse (S2) + Entity/Relationship Build (S6), both LLM-augmented with typed I/O |
| R2 | Knowledge Runtime | Understand | Deterministic (rule + similarity resolution); LLM only as stage-5 fallback classifier |
| R3 | Decision Context Runtime | Decide | Deterministic assembly; LLM only for context enrichment (retrieval, not reasoning) |
| R4 | Decision Runtime | Decide | LLM-led, deterministic gates (feasibility math, blocking rules, risk classification) |
| R5 | Simulation Runtime | Decide (future) | Deterministic simulation; placeholder |
| R6 | Policy Runtime | Act (gate) | **Fully deterministic.** No LLM in the policy path |
| R7 | Workspace Runtime | Act (projection) | Projection/validation deterministic; LLM only in `llm_augment: true` narrative fields |
| R8 | Action Runtime | Act (execution) | **Fully deterministic.** No LLM in the execution path |
| R9 | Learning Runtime | Learn | Deterministic measurement; LLM only for narrative retrospective |

---

## Infrastructure Boundaries

The following infrastructure components are frozen and **never rewritten**:

- **Cloud Run** — compute runtime (serverless)
- **Temporal** — workflow orchestration (NOT Cloud Workflows)
- **Redpanda** — event streaming (NOT Pub/Sub)
- **pgvector** (in Neon PostgreSQL) — primary vector store (Qdrant removed for MVP)
- **Neo4j Aura** — graph store (never self-host in prod)
- **Neon PostgreSQL** — relational OLTP system of record
- **Cloudflare R2** — object storage (GCS supported later via adapter)
- **BigQuery Sandbox** — analytics/KPI/historical reporting/dashboards ONLY, never the app DB
- **Langfuse** — LLM observability
- **Sentry** — error monitoring
- **Flagsmith** — feature flags
- **Better Auth** — authentication
- **Resend** — email

**Removed:** MinIO, Qdrant (MVP), Spark, Cloud SQL, Cloud Workflows.

---

## LLM Boundaries

**LLM exists ONLY inside Evidence, Knowledge, and Decision runtimes.** Everything else is deterministic.

| Runtime | LLM Allowed? | LLM Use |
|---------|-------------|---------|
| Evidence Runtime | ✅ Allowed | Parse (S2), Entity/Relationship Build (S6) — typed input → typed output only |
| Knowledge Runtime | ✅ Allowed | Stage-5 fallback classifier only |
| Decision Context Runtime | ✅ Allowed | Decision agent reasoning over assembled context |
| Policy Runtime | ❌ Forbidden | Fully deterministic policy evaluation |
| Workspace Runtime | ❌ Forbidden | Projection/validation deterministic; LLM only in `llm_augment: true` narrative fields |
| Action Runtime | ❌ Forbidden | Fully deterministic execution path |
| Simulation Runtime | ❌ Forbidden (MVP) | Future: LLM may assist with scenario narration |
| Learning Runtime | ❌ Forbidden | Deterministic measurement; LLM only for narrative retrospective (future) |

**Allowed/Forbidden contract:** ALLOWED — extraction, classification, summarization, reasoning, recommendation, narrative. FORBIDDEN — business rules, ontology, policy, state, execution, validation, permissions.

---

## Deterministic Boundaries

- **Policy Runtime** (R6) is the deterministic gate: allowed? approval required? confidence threshold? autonomy level? escalation? compliance? The risk tier is **recomputed inside the gate** — never trusted from the LLM.
- **Action Runtime** (R8) is fully deterministic — the Execution agent **never reasons**; no LLM call in the execution path.
- **Workspace Runtime** (R7) projection/validation is deterministic.
- **Core Platform is never rewritten** — only the Business Layer [Evidence→Knowledge→Decision→Workspace] is rewritten.

---

## Preserve vs Rewrite

| Preserve (production runtime) | Replace (business-intelligence layer only) | Add (Decision Intelligence layer) |
|---|---|---|
| FastAPI services | V5.2 agent roster (`authority_manifest.py`) | **Decision Context Runtime** |
| Temporal (3 queues + retry/DLQ/idempotency + `continueAsNew`) | "Shared Platform Agent + 5 skills" plan (`PLAN_V6.md` ADR-004) | **Risk-tiered autonomy model** + **Policy Runtime** gate |
| Redpanda event bus (`apps/ai/src/events/`) | Specialist @mention workflows in `command_center_chat.go` | **Deterministic Action Scheduler** |
| Connector SDK (`connect/fetch/health` → `list[EvidenceRecord]`) | — | **Simulation Runtime** interface (placeholder) |
| Evidence pipeline (14 stages) + `EvidenceRecord` | — | **Policy Runtime** gate (Validation → Policy → Governance → Execution) |
| Governance decorators (`@governed_write`) | — | **Learning Runtime** metrics + outcome logging |
| Workspace store (`session/workspace_store.py`) | — | — |
| Validation framework (V001–V008) | — | — |
| Observability, circuit breakers, retry, DLQ, idempotency | — | — |
| SSEHub event-type filtering + `SignalWorkflow("hitl-approval")` | — | — |
| **Core Platform** (FastAPI, Temporal, Redpanda, Retry, DLQ, Circuit Breaker, Governance, Observability, Connector SDK, Workspace Store, Evidence SDK, Validation Framework) | — | — |
| **Data platform** (Neon PostgreSQL + pgvector primary, Cloudflare R2, BigQuery Sandbox, Neo4j Aura) | — | — |
| **Enterprise Retrieval** (BM25 + pgvector + Neo4j traversal + metadata filters + reranking) | — | — |

**Core Platform (NEVER rewrite):** FastAPI, Temporal, Redpanda, Retry, DLQ, Circuit Breaker, Governance, Observability, Connector SDK, Workspace Store, Evidence SDK, Validation Framework, plus the frozen platform stack — Neon PostgreSQL, Cloudflare R2, BigQuery Sandbox, pgvector, Neo4j Aura, Redpanda, Temporal, Langfuse, Sentry, Flagsmith, Better Auth, Resend.

**Business Layer (rewrite):** Evidence → Knowledge → Decision → Workspace.

**V5.2 manifest** (`authority_manifest.py`) is retained as a **compatibility shim** behind `ENABLE_V6_RUNTIME=on` — it is not rewritten, it is gated.

---

## Local Development Architecture

- **MiniSky** (already running) is the local GCP control plane: API gateway `http://localhost:8080`, console `http://localhost:8081`. It emulates Cloud Storage, Pub/Sub, BigQuery, IAM, LRO, and the Cloud Run API. Everything goes through `localhost:8080` exactly like production.
- **Docker Compose** (non-GCP): Neo4j, Postgres, Temporal, Redpanda, Redis, Langfuse. NOT MinIO (MiniSky covers local GCS); NOT Qdrant (pgvector primary).
- **Mockoon** (cli, ports 3001–3004) mocks Slack/Jira/Salesforce/Notion.

---

## Production Architecture

- **Cloud Run** hosts the FastAPI API (serverless, per-request scaling).
- **Temporal** orchestrates the 9 runtimes (3 queues + retry/DLQ/idempotency + `continueAsNew`).
- **Redpanda** is the event bus.
- **Neon PostgreSQL** is the transactional system of record; **pgvector** (in Postgres) is the primary vector store.
- **Neo4j Aura** is the graph store (never self-host in prod).
- **Cloudflare R2** is object storage; **BigQuery Sandbox** is analytics-only.
- **Enterprise Retrieval** = BM25 + pgvector + Neo4j traversal + metadata filters + reranking.
- **OpenTelemetry → Langfuse → Sentry** for monitoring; **Flagsmith** feature flags; **Better Auth** auth; **Resend** email.

---

## Impact

- **No new features beyond the approved MVP.** The MVP core loop stays **Evidence → Knowledge → Decision → Workspace**.
- **Domain-expanding features are deferred to V6.5** (NOT part of this freeze): **Decision Store, Feature Store, Knowledge Cache**.
- The platform stack is frozen — no further platform component churn is permitted.
- Qdrant, MinIO, Spark, Cloud SQL, and Cloud Workflows are removed from the stack; pgvector is the primary vector store.

---

## Follow-on Contracts

- `docs/v6-runtime-architecture.md` (v3.0 — platform freeze)
- `docs/decision-context-runtime.md`
- `docs/autonomy-model.md`
- `docs/llm-boundary.md`
- `IMPLEMENTATION_PLAN.md`
- `RISK_REGISTER.md`
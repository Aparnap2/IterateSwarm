# OntologyAI V6 — Virtual COO Office for B2B SaaS Founders

<p align="center">
<img width="200" height="200" alt="ki-logo-1784785049927" src="https://github.com/user-attachments/assets/dbcd807b-06f5-4fc8-a8f8-f33a429b1951" />
</p>

> **OntologyAI is a portfolio-scale Virtual COO Office for B2B SaaS founders** that continuously understands the company's operating system, monitors live business activity, assigns scoped work to AI employees, executes approved digital work, and maintains organizational memory.
>
> **V6 thesis:** 3 AI employees × 9 canonical missions × frozen V6 domain model.
>
> **Platform status:** #1 Foundation Hygiene → #2 V6 Domain Model [FROZEN] → #3 Employee Runtime → #4 Mission + Autonomy → #5 Operational Workspace → #6 E2E + Reliability.

[![Build](https://img.shields.io/badge/build-clean-brightgreen)](#getting-started)
[![Tests](https://img.shields.io/badge/tests-V6%20Virtual%20COO%20Office-blue)](#test-coverage)
[![Go](https://img.shields.io/badge/Go-1.24-blue?logo=go&logoColor=white)](https://go.dev)
[![Python](https://img.shields.io/badge/Python-3.13-green?logo=python&logoColor=white)](https://www.python.org)
[![Version](https://img.shields.io/badge/version-6.0-blue)](#implementation-status)

---

## Table of Contents

- [Problem](#problem)
- [Product Principle](#product-principle)
- [AI Workforce](#ai-workforce)
- [Integrations](#integrations)
- [Founder Experience](#founder-experience)
- [Work Classification & Autonomy](#work-classification--autonomy)
- [Architecture](#architecture)
- [Project Structure](#project-structure)
- [Implementation Status](#implementation-status)
- [Getting Started](#getting-started)
- [Test Coverage](#test-coverage)
- [Key Docs](#key-docs)
- [Conventions & Contributing](#conventions--contributing)

---

## Problem

Founder-led B2B SaaS companies develop four recurring dependencies:

1. **Information dependency** — important knowledge lives in the founder's/team's head or scattered across tools.
2. **Standards dependency** — quality expectations and definitions of done are inconsistent or undocumented.
3. **Decision dependency** — routine decisions repeatedly return to the founder.
4. **Execution dependency** — the founder personally performs work that could be delegated or automated.

Result: context switching, operational bottlenecks, inconsistent execution, excessive founder involvement.

## Product Principle

Not another chatbot or dashboard. OntologyAI turns the company's operating model into a continuously maintained digital system:

```
Business Pillar
→ Process
→ SOP
→ Owner
→ KPI
→ Live Evidence
→ Mission
→ AI Employee
→ Capability
→ Action
→ Outcome
→ Review
```

Four MVP pillars: **Marketing, Sales, Operations, Finance**. Each system = Input → Process → Output → Feedback Loop. Processes additionally carry: owner, objective, scope, SOP, decision rules, definition of done, KPIs, dependencies, allowed actions, review cadence.

## AI Workforce

Exactly **three AI employees**. These are role configurations over ONE shared Employee Runtime (reusable skills, capabilities, policies, memory, mission orchestration) — not three hard-coded workflow graphs.

| AI Employee | Focus | Primary systems |
|-------------|-------|-----------------|
| **RevOps Intern** | Marketing/Sales handoff, pipeline health, CRM hygiene, stalled opportunities, follow-up coordination, revenue operational issues | Salesforce + Slack |
| **ProductOps Intern** | Operational work tracking, blockers, delivery/roadmap health, process adherence, standards/DoD, documentation synchronization | Jira + Notion + Slack |
| **Organizational Intelligence Intern** | Organizational memory, decision capture, SOP freshness, ownership gaps, communication patterns, cross-functional context | Slack + Notion + Jira |

**Do not create a Finance Intern to make the pillar coverage symmetric.** The four pillars (Marketing, Sales, Operations, Finance) are covered by the three interns because none of the nine canonical missions is a finance mission; a finance intern is not a priority unless a finance mission is authored.

## Integrations

Exactly four integrations for MVP — no additional connectors.

| Connector | Purpose |
|-----------|---------|
| **Salesforce** | CRM data, opportunities, pipeline health |
| **Jira** | Issues, epics, tickets, sprint data |
| **Slack** | Conversations, decisions, async coordination |
| **Notion** | Docs, product specs, meeting notes, wikis |

**Implementation status:** the V6 connector SDK lives in `apps/ai/src/connectors/` (V6Connector Protocol, transport with retry/backoff + mock transport, sync state, registry) with mock connectors for all four systems and `apps/ai/src/integrations/jira.py` present. Linear is not included. Legacy V5.2 integrations (Stripe, Plaid, Slack, ERPNext, HubSpot, QuickBooks) are still present under `apps/ai/src/integrations/`.

## Founder Experience

The primary UI is an **Operational Workspace**, not a conventional dashboard. It exposes:

- Morning Brief
- Active Missions
- Bottlenecks
- Recommendations
- AI Employee Activity
- Evidence Timeline
- Process/SOP status
- Approval Queue
- Mission History

**Chat is an interaction layer**: asking questions, investigating, redirecting missions, approving/rejecting actions, changing priorities, interrupting work, requesting evidence.

The workspace keeps the existing **Go + HTMX + SSE** architecture (no React/GenUI for MVP). SSE provides live updates; the workspace renders typed workspace state and is not the source of business logic.

**Implementation status:** `apps/core/internal/web/` serves the command center (Fiber + HTMX + SSE) with `handler.go`, `sse.go` + `sse_hub.go` (per-tenant Subscribe with event-type filtering), `command_center_*.go` panels, `telemetry_handler.go`, and `templates/command_center.html` + `partials/`. The `/v6` routes are **PLANNED** — currently 501 Not Implemented stubs in `apps/core/internal/v6/`.

## Work Classification & Autonomy

Two different classifications, applied at different stages:

1. **Work design decision — Automate / Delegate / Eliminate.** Decides WHAT should happen to a piece of work. Produced by Process Review.
   - **Automate** — safe, deterministic, repeatable digital work.
   - **Delegate** — work an AI employee can perform within defined authority.
   - **Eliminate** — redundant or low-value process steps identified during review.
2. **Runtime risk policy — LOW / MEDIUM / HIGH / CRITICAL.** Decides HOW MUCH AUTHORITY the AI has for a given action.

**The automation decision (Automate/Delegate/Eliminate) is NOT the same as the risk tier (LOW/MEDIUM/HIGH/CRITICAL).**

Cascade (ordered flow):

```
Process Review
→ Automate / Delegate / Eliminate
→ if automated or delegated: Action
→ Risk Classification → LOW / MEDIUM / HIGH / CRITICAL
→ Policy Decision → Execute / Recommend / Approve / Block
```

Autonomy is risk-based: LOW = auto-execute if policy allows; MEDIUM = recommend + approval or configured auto-execution; HIGH = mandatory human approval; CRITICAL = no automatic execution. **Human approval is mandatory for actions outside the employee's authority or above the risk threshold.** Every action records: reason, evidence, confidence, authority, policy decision, idempotency key, result, rollback/recovery metadata.

**MVP control patterns are exactly:** Sequential, Parallel, Branch, Loop, Wait/Human-signal, Replan, Verify. Delegate and Reflect are behavior WITHIN the loop, not separate infrastructure. **Guardrail: do not build a generic workflow engine** (a LangGraph/Temporal clone).

**Implementation status:** HITL approvals and Temporal signals exist (`apps/ai/src/hitl/`, `@governed_write` in `apps/ai/src/ontology/governance.py`, `SignalWorkflow("hitl-approval")`). The work-classification layer (Automate/Delegate/Eliminate) and the risk-tier policy layer are **PLANNED**.

## Architecture

```mermaid
flowchart LR
    CB["Connected Business<br/>(Salesforce · Jira · Slack · Notion)"] --> EF["Event Fabric"]
    EF --> EV["Evidence Runtime"]
    EV --> KR["Knowledge Runtime"]
    KR --> PM["Process / SOP Model"]
    PM --> MR["Mission Runtime"]
    MR --> ER["Employee Runtime"]
    ER --> CR["Capability Runtime"]
    CR --> TA["Tool / API"]
    TA --> VF["Verify"]
    VF --> MS["Mission State / Outcome"]
    MS --> CB

    SK["Skill Model"] --> CR
    CX["Context Engineering"] --> CR
    PO["Policy / Autonomy"] --> CR

    MS --> MT["Memory / Timeline"]
    MT --> FW["Founder Workspace"]
    SS["HTMX / SSE"] --> FW
    FW --> CB
```

### Components

| Runtime / layer | Code location |
|-----------------|---------------|
| **Connected Business** (connectors) | `apps/ai/src/connectors/` — V6Connector Protocol (`v6_contract.py`, `v6_base.py`), `transport.py` (HttpxTransport retry/backoff + MockTransport), `sync_state.py`, `registry.py`; `apps/ai/src/integrations/jira.py`; mock connectors |
| **Event Fabric** | `apps/ai/src/events/` — Redis Streams event bus today; Redpanda provisioned in `docker-compose.yml` (target per PRD §16) |
| **Evidence Runtime** | `apps/ai/src/evidence/` — `runtime.py`, `normalizer.py`, `normalizer_registry.py`, `models.py` |
| **Knowledge Runtime** | `apps/ai/src/knowledge/` — `entity_resolver.py`, `graph_builder.py`, `conflict_resolver.py`, `semantic_layer.py`; ontology in `apps/ai/src/ontology/` (`object_types.py`, `link_types.py`, `adapter.py`, `governance.py`) |
| **Process / SOP Model** | PLANNED — no SOP module/contract yet; BusinessPillar/SOP entities missing from `apps/ai/src/entities/models.py` |
| **Mission Runtime** | `apps/ai/src/mission/` — `timeline.py`, `decision.py`, `storage.py`, `runtime.py`, `orchestrator.py`, `coordinator.py`; `apps/ai/src/session/` (`mission_state.py`, `relevance_gate.py`); write path `POST /api/mission-state` → PostgreSQL |
| **Employee Runtime** | `apps/ai/src/mission/employee.py` — DigitalEmployee + intern classes (hard-coded today; config-driven runtime PLANNED) |
| **Capability Runtime** | `apps/ai/src/mission/capability.py`; capability model in `apps/ai/src/ontology/capability_*.py` |
| **Tool / API** | Connector SDK + mock connectors (see Connected Business); capability execution via `apps/ai/src/mission/capability.py` |
| **Verify** | `apps/ai/src/pipeline/validation_engine.py` (rules V001–V008); mission outcome verification PLANNED |
| **Mission State / Outcome** | `apps/ai/src/mission/timeline.py` — append-only `timeline_events`, versioned `mission_snapshots`, diff; `POST /api/mission-state` → PostgreSQL |
| **Skill Model** | PLANNED — composable skill definitions over the shared Employee Runtime |
| **Context Engineering** | `apps/ai/src/memory/` — `spine.py` (Qdrant L2/L5, threshold 0.82), Graphiti, Qdrant; stack under ADR-009 review |
| **Policy / Autonomy** | `apps/ai/src/ontology/governance.py` (`@governed_write`); `apps/ai/src/hitl/` (`approval_queue.py`, `manager.py`, `confidence.py`); `apps/ai/src/services/` (`trust_battery.py`, `alert_gate.py`); work-classification + risk-tier policy layer PLANNED |
| **Memory / Timeline** | `apps/ai/src/memory/` (spine, Qdrant, Graphiti); `apps/ai/src/mission/timeline.py` — append-only `timeline_events`, versioned `mission_snapshots`, diff |
| **Founder Workspace** | `apps/core/internal/web/` — `handler.go`, `sse.go` + `sse_hub.go`, `command_center_*.go`, `telemetry_handler.go`, `templates/command_center.html` + `partials/` |
| **HTMX / SSE** | `apps/core/internal/web/sse.go` + `sse_hub.go` — SSEHub per-tenant Subscribe with event-type filtering; HTMX partials in `templates/partials/` |

## Project Structure

```
apps/
  core/                         # Go Modular Monolith (Fiber + HTMX + SSE)
    cmd/
      server/                   # HTTP server entrypoint
      worker/                   # Temporal worker entrypoint
      consumer/                 # Consumer entrypoint
    internal/
      web/                      # HTTP handlers (Fiber + HTMX + SSE)
        handler.go              # Endpoints, @mention routing, SSE broadcast
        sse.go / sse_hub.go     # SSEHub per-tenant Subscribe, event-type filtering
        command_center_*.go     # Mission state, approvals, timeline, agents panels
        telemetry_handler.go
        handler_v6.go           # /v6 routes (501 stubs)
        templates/
          command_center.html
          partials/             # HTMX partials
      v6/                       # STUBBED — /v6 routes return 501 Not Implemented
      workflow/                 # Temporal workflows & stubs
      temporal/                 # Temporal client (SignalWorkflow, ExecuteWorkflow)
      agents/                   # Mostly empty (compile stubs)
      db/                       # sqlc generated code
      database/                 # Connection utilities
      config/                   # LLM configuration
      redpanda/ events/ api/ webhooks/ security/ memory/ grpc/ integrations/ debug/ retry/ tracing/ logging/
  ai/                           # Python AI Worker
    src/
      entities/                 # Canonical entity model (models.py)
      ontology/                 # Object types, link types, adapter, governance (@governed_write)
      connectors/               # V6 connector SDK + mock connectors + jira.py
      mission/                  # Timeline, decision, employee, storage, runtime, orchestrator, coordinator, capability
      session/                  # MissionState + relevance gate
      evidence/                 # Evidence runtime + normalizers
      pipeline/                 # Artifact / decision / feasibility / validation engines
      knowledge/                # Entity resolver, graph builder, conflict resolver, semantic layer
      memory/                   # Spine (Qdrant), Graphiti
      observability/            # TraceContext, PipelineRun / run_stage
      events/                   # Redis Streams event bus
      hitl/                     # Approval queue, manager, confidence
      services/                 # Trust battery, alert gate
      workflows/                # Temporal workflow definitions
      activities/               # Temporal activities
      orchestration/            # Pipeline orchestrators
      schemas/                  # Pydantic models (knowledge_catalog.py, ...)
      worker.py                 # Temporal worker registration
    tests/
      test_mission_timeline.py  # Deterministic timeline/diff unit tests
      test_mission_postgres.py  # Mission state against Postgres
      test_digital_employee.py  # DigitalEmployee / intern classes
      integration/              # Live-infra suites (skip when DB/LLM absent)
        test_mission_live_infra.py       # Postgres + real LLM
        hardening/
          test_pipeline_e2e.py           # E2E observability (live Postgres + real LLM)
apps/core/migrations/           # FRAGMENTED — see Implementation status
scripts/
  hardening/
    chaos_smoke.sh              # Restart postgres+temporal, assert recovery
    README.md
mockoon/                        # Mock connector servers (jira :3003, slack :3002, salesforce :3004, notion :3001)
docs/                           # See Key Docs
```

## Implementation Status

| Area | Status | Notes |
|------|--------|-------|
| Canonical entity model | DONE | `apps/ai/src/entities/models.py` — strict Pydantic entities (Evidence, Source, KPI, Decision, Policy, Workspace, ...). BusinessPillar/SOP/Mission/Action/Review/AIEmployee entities PLANNED |
| Ontology + governed writes | DONE | `apps/ai/src/ontology/` — `object_types.py`, `link_types.py`, `adapter.py` (`mission_state_to_ontology()`), `governance.py` (`@governed_write`) |
| Mission timeline + state write path | DONE | `apps/ai/src/mission/timeline.py` (append-only events, versioned snapshots, diff); `POST /api/mission-state` → PostgreSQL |
| Mission decisioning | DONE | `apps/ai/src/mission/decision.py` — real LLM via `apps/ai/src/config/llm.py`, json_mode |
| Evidence / pipeline / knowledge | DONE | `apps/ai/src/evidence/`, `apps/ai/src/pipeline/` (rules V001–V008), `apps/ai/src/knowledge/` |
| Observability | DONE | `apps/ai/src/observability/` — typed TraceContext, PipelineRun/run_stage; Langfuse traces |
| Event bus | DONE | `apps/ai/src/events/` (Redis Streams) |
| HITL approvals | DONE | `@governed_write`; Temporal `SignalWorkflow("hitl-approval")`; `apps/ai/src/hitl/` |
| Employee runtime | PARTIAL | `apps/ai/src/mission/employee.py` — DigitalEmployee + intern classes, hard-coded today; config-driven shared runtime PLANNED |
| Connectors (4 MVP) | PARTIAL | `apps/ai/src/connectors/` — V6Connector Protocol + mock connectors for all 4; `apps/ai/src/integrations/jira.py` present; Linear absent; legacy V5.2 integrations still present |
| Workspace (Go + HTMX + SSE) | PARTIAL | `apps/core/internal/web/` — command center panels + SSEHub work; `/v6` routes are 501 stubs |
| Missions (V6 set) | PARTIAL | 5+ Temporal workflows exist; no frozen V6 nine-mission config set |
| Risk-based autonomy | PLANNED | HITL approvals + Temporal signals exist; no risk-tier policy layer |
| SOP module / contract | PLANNED | Missing entirely |
| BusinessPillar entities | PLANNED | Missing from `apps/ai/src/entities/models.py` |
| Go `/v6` routes | PLANNED | `apps/core/internal/v6/` — 20+ routes return 501 Not Implemented |
| Migrations | PLANNED | Fragmented — see Implementation status |
| Memory stack | REVIEW | Qdrant-based today; ADR-009 points toward pgvector (unresolved) |

## Getting Started

### Prerequisites

- **Docker** (Temporal, Qdrant, PostgreSQL, Neo4j/Graphiti, Redpanda)
- **Go 1.24**
- **Python 3.13** with [`uv`](https://github.com/astral-sh/uv)

### Quickstart

```bash
# 1. Start infrastructure
make up

# 2. Run the Go server
cd apps/core && go run cmd/server/main.go

# 3. Run the Go Temporal worker
cd apps/core && go run cmd/worker/main.go

# 4. Install Python deps and run the Python worker
cd apps/ai && uv sync
cd apps/ai && uv run python -m src.worker

# 5. Open the Operational Workspace
#    http://localhost:8080
```

### Run the tests

```bash
# Go — all packages
cd apps/core && go test ./...

# Python — full suite
cd apps/ai && uv run pytest tests/ -v

# Python — hardening + live-infra suites (need Postgres up + GROQ_API_KEY)
cd apps/ai && set -a && . ../../.env && set +a && \
  uv run pytest tests/integration/hardening/test_pipeline_e2e.py -q -p no:cacheprovider
cd apps/ai && uv run pytest tests/integration/test_mission_live_infra.py -q -p no:cacheprovider
```

### Environment variables

| Provider | Variables |
|----------|-----------|
| **Azure AI Foundry** | `AZURE_OPENAI_ENDPOINT`, `AZURE_OPENAI_API_KEY` |
| **Groq** | `GROQ_API_KEY` |
| **OpenAI** | `OPENAI_API_KEY` |
| **Ollama** (local) | `OLLAMA_BASE_URL`, `OLLAMA_API_KEY` |

| Control | Variable | Default |
|---------|----------|---------|
| Temporal task queue | `ONTOLOGYAI-MAIN-QUEUE` | `TRACKGUARD-MAIN-QUEUE` |
| Live Postgres DSN | `ITERATESWARM_DATABASE_URL` | `postgresql://iterateswarm:iterateswarm@localhost:5433/iterateswarm` |

Secrets live in a local `.env` file (never committed).

## Test Coverage

| Suite | Scope |
|-------|-------|
| **Go build** | Clean |
| **Go HTMX handler tests** | 74+ historically claimed (command center, business, founder, LLMops, onboarding, watchlist, telegram, razorpay, alert lineage, operating layer) — unverified in this audit |
| **Python — mission timeline/diff** | Deterministic unit tests (`tests/test_mission_timeline.py`) |
| **Python — mission state** | Postgres-backed mission state tests (`tests/test_mission_postgres.py`) |
| **Python — live-infra mission** | Postgres + real LLM (`tests/integration/test_mission_live_infra.py`) |
| **Python — hardening E2E** | E2E observability, live Postgres + real LLM (`tests/integration/hardening/test_pipeline_e2e.py`) |
| **Python — pipeline/connectors/feasibility/validation** | Rule and contract suites (V001–V008) |

Note: the historical "901 passing / 26 skipped / 0 failed" claim in `AGENTS.md` is V4.2-era and unverified. Precise current pass counts are not asserted here.

## Key Docs

| Doc | Note |
|-----|------|
| [`docs/evidence-contracts.md`](docs/evidence-contracts.md) | Evidence typing and normalization contracts |
| [`docs/llm-boundary.md`](docs/llm-boundary.md) | LLM input/output boundary rules |
| [`docs/autonomy-model.md`](docs/autonomy-model.md) | Autonomy and approval model |
| [`docs/decision-context-runtime.md`](docs/decision-context-runtime.md) | Decision context assembly |
| [`docs/replay-engine.md`](docs/replay-engine.md) | Replay and idempotency |
| [`docs/event_contracts.md`](docs/event_contracts.md) | Event envelope contracts |
| [`docs/v6-runtime-architecture.md`](docs/v6-runtime-architecture.md) | Runtime architecture notes |
| [`docs/ADR-009-platform-runtime-freeze.md`](docs/ADR-009-platform-runtime-freeze.md) | Platform runtime freeze; memory stack (Qdrant vs pgvector) under review |

## Conventions & Contributing

- **Feature branches:** `git checkout -b feature/description` — never commit directly to `main`.
- **Conventional Commits:** `feat:`, `fix:`, `refactor:`, `docs:`, `test:`, `chore:`.
- **Never commit to `main`.** Open a PR from your feature branch.
- **Secrets:** use a local `.env` file; never commit secrets.
- **Coding standards:** full coding standards and build/test commands in [`AGENTS.md`](./AGENTS.md).
- **Canonical PRD:** [`prd.md`](./prd.md) — OntologyAI V6 "Virtual COO Office for B2B SaaS Founders".
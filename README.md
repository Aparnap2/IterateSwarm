# OntologyAI Workspace

<p align="center">
<img width="200" height="200" alt="ki-logo-1784785049927" src="https://github.com/user-attachments/assets/dbcd807b-06f5-4fc8-a8f8-f33a429b1951" />
</p> 



> 
>
> **An enterprise AI operations workspace.** OntologyAI Workspace turns messy business evidence into a shared business map, surfaces operational truth, and drafts governed workflow pilots for review and deployment planning. It is designed as a self-serve FDE companion and a multi-agent FDE operating system — not a small-business dashboard, generic chatbot, or no-code automation builder.

[![Build](https://img.shields.io/badge/build-clean-brightgreen)](#getting-started)
[![Tests](https://img.shields.io/badge/tests-V5.2%20Enterprise%20Discovery-blue)](#test-coverage)
[![Go](https://img.shields.io/badge/Go-1.24-blue?logo=go&logoColor=white)](https://go.dev)
[![Python](https://img.shields.io/badge/Python-3.13-green?logo=python&logoColor=white)](https://www.python.org)
[![Version](https://img.shields.io/badge/version-5.2-blue)](#v52-active-roster-vs-legacy-compatibility)

---

## Table of Contents

- [What changed](#what-changed)
- [Product position](#product-position)
- [Who it is for](#who-it-is-for)
- [Product pillars](#product-pillars)
- [User-facing workflow](#user-facing-workflow)
- [Core architecture](#core-architecture)
- [Why enterprise focus](#why-enterprise-focus)
- [UI language remaster](#ui-language-remaster)
- [Navigation](#navigation)
- [Current V5.2 scope](#current-v52-scope)
- [Build principle](#build-principle)
- [Architecture](#architecture)
- [Request / Response Flow](#request--response-flow)
- [Ontology Layer](#ontology-layer)
- [Project Structure](#project-structure)
- [Getting Started](#getting-started)
- [Architecture Decision Records](#architecture-decision-records)
- [V5.2 Active Roster vs Legacy Compatibility](#v52-active-roster-vs-legacy-compatibility)
- [Contributing & Conventions](#contributing--conventions)
- [Test Coverage](#test-coverage)

---

## What changed

V5.2 reframes the product as an AI Discovery and Solution Design Platform. OntologyAI is no longer positioned as an "FDE companion + multi-agent OS" — it is now a discovery-first platform that ingests messy business evidence, builds a validated Enterprise Knowledge Model, maps capabilities to solution patterns, and generates an Enterprise Architecture Pack (12 artifacts) for handoff. The core value appears when organizations have fragmented systems, cross-functional processes, approval gates, and high-cost coordination problems.

## Product position

OntologyAI Workspace is best understood as an enterprise **ops twin** and guided pilot-building environment. The platform converts raw evidence from conversations, uploads, exports, and connected tools into typed operational objects, diagnoses what is stuck or risky, and generates governed workflow drafts plus handoff artifacts.

### One-line pitch

OntologyAI Workspace turns messy enterprise operations into a shared business map, reveals what is broken, and drafts governed workflows teams can review, approve, and pilot.

### What it is

- A self-serve FDE companion for enterprise discovery and pilot design.
- A shared workspace for evidence intake, ontology review, operational truth, approvals, and exports.
- An ontology-first AI operating layer with deterministic validation and governance controls.
- A portfolio-grade demonstration of the Forward Deployed Engineer method as software.

### What it is not

- A founder alert bot.
- A finance-only assistant.
- A passive dashboard.
- A generic no-code builder.
- An unconstrained autonomous action engine.
- A small-business utility bundle built around a few lightweight API add-ons.

## Who it is for

Primary users:
- Forward Deployed Engineers, implementation engineers, transformation leads, and enterprise operators running discovery-to-pilot engagements.
- Client-side operations owners using a workspace directly to structure messy business inputs and review proposed workflows.

Secondary users:
- Approvers, reviewers, domain contributors, and stakeholders consuming truth maps, workflow packs, SOPs, and governed action proposals.

## Product pillars

The product should be presented through three visible pillars rather than six backend workflow names.

### Understand

This pillar covers conversational discovery, evidence intake, the ontology setup flow, unresolved questions, and the first shared business map. It is powered internally by ChiefOfStaff, Discovery, and Ontology Mapping workflows, but the user experience should feel like one guided understanding loop.

### Diagnose

This pillar covers operational truth: blockers, contradictions, missing ownership, risky states, and action-worthy findings. Internally this maps to TruthAnalysisWorkflow, but the product surface should present it as operational diagnosis rather than abstract analytics.

### Build

This pillar covers workflow specs, SOPs, pilot drafts, approval gating, and exportable deployment packages. Internally this spans WorkflowBuilderWorkflow and GovernanceWorkflow, while the user sees a safe path from recommendation to review to pilot package.

## User-facing workflow

The internal architecture keeps the locked V5.1 phases, but the visible workflow should be simpler:

1. Frame the problem.
2. Add evidence.
3. Confirm the business map.
4. Review what is broken.
5. Approve the pilot draft.
6. Export or launch the pilot.

This aligns with the existing engagement phases of Discovery, Ontology Mapping, Truth Analysis, Workflow Design, Governance Review, Deployment Planning, and Handoff while making the experience easier to understand for enterprise users.

## Core architecture

The V5.2 architecture is built on the following foundations:
- Exactly 6 workflows: ChiefOfStaffWorkflow, DiscoveryWorkflow, OntologyMappingWorkflow, KnowledgeValidationWorkflow, SolutionArchitectWorkflow, GovernanceWorkflow.
- Exactly 6 ontology object types: Party, Engagement, MoneyEvent, Issue, Message, PlannedAction.
- Enterprise Knowledge Model is the canonical intermediate representation — entities, relationships, processes, business rules, capabilities, problems, opportunities.
- Evidence layer: every entity carries full provenance (source, confidence, evidence ID, timestamp, extraction method).
- Canonical EngagementState as the shared state for all workflow collaboration.
- ExecutableWorkflowDraft as the typed deployable workflow artifact.
- Governance exclusivity for external execution and approval-gated side effects.

## Why enterprise focus

OntologyAI shines when operations are too cross-functional, messy, and risky for simple automation glue. Small teams can often survive with a few point integrations, but larger organizations need a governed system that can unify evidence, preserve provenance, model relationships, identify contradictions, and route action through approvals instead of brittle one-off scripts.

This enterprise framing also better matches the product's ontology-first architecture, shared state design, governance model, handoff artifacts, and workflow-draft generation. Those capabilities are structurally more valuable in multi-team environments than in very small businesses with simple tool stacks.

## UI language remaster

Recommended user-facing labels:

| Internal term | User-facing label |
|---|---|
| ChiefOfStaff | Workspace Guide |
| Ontology | Business Map |
| Truth Analysis | Operational Truth |
| Solution Architect | Pilot Builder |
| Governance | Approvals & Safety |
| ExecutableWorkflowDraft | Pilot Draft |

These labels keep the architecture intact while making the product more legible to enterprise users.

## Navigation

Recommended primary workspace navigation:
- Workspace
- Business Map
- Findings
- Workflow Drafts
- Approvals
- Exports

This is cleaner than exposing internal workflow names directly and still satisfies the required shared workspace views for chat, uploads, ontology, truth findings, workflows, drafts, approvals, and artifacts.

## Current V5.2 scope

V5.2 is an AI Discovery and Solution Design Platform. It includes:
- Shared workspace intake and streaming interaction.
- Enterprise Knowledge Model as the canonical intermediate representation.
- Evidence layer: provenance-tracked ingestion with full lineage.
- Guided ontology construction from evidence.
- Knowledge validation: cross-source truth diagnosis with provenance verification.
- Capability Catalogue: searchable registry of enterprise capabilities.
- Solution Recommendation Engine: matches requirements to capabilities.
- Enterprise Architecture Pack (12 artifacts): truth map, ontology snapshot, EKM snapshot, evidence index, capability catalogue, solution recommendation, workflow specs, SOP packs, action registers, business rules, process models, and executable draft artifacts.
- Approval-gated governance.

It explicitly does not include deployment, activation, scheduling, or unconstrained autonomous execution. Runtime compilation is an optional export target only.

## Build principle

Keep the backend contract strict and the frontend experience simple: typed state, deterministic validation, governed actions, and enterprise-grade review loops underneath; guided, comprehensible, outcome-first UX on top.

---

## Architecture

Users reach OntologyAI through the workspace landing page (web). The Go Core accepts the message, routes the `@mention` in O(1) to the `ChiefOfStaffWorkflow` control plane, which dispatches specialist Temporal workflows. A Python AI worker runs the LangGraph/DSPy agents against an LLM provider, streams answers back over SSE, and — for consequential writes — proposes a `PlannedAction` that `GovernanceWorkflow` approves. Every ontology entity carries full provenance (source, confidence, evidence ID, timestamp, extraction method), enforced by the **Evidence Layer**. The `SolutionArchitectWorkflow` consults the **Capability Catalogue** and **Solution Recommendation Engine** to map validated knowledge to solution architectures. The `GovernanceWorkflow` produces the **Enterprise Architecture Pack** (12 artifacts) for download — not deployment.

```mermaid
flowchart TD
    U["Enterprise User"] --> CORE["Go Core (Fiber HTTP + HTMX + SSE)"]
    CORE --> ROUTER["@mention Router — O(1) map lookup → ChiefOfStaff control plane"]
    ROUTER --> COS["ChiefOfStaffWorkflow  (@ontologyai / @chief / @sarthi)"]
    COS --> DISC["DiscoveryWorkflow  (@discover)"]
    COS --> MAP["OntologyMappingWorkflow  (@map)"]
    COS --> KV["KnowledgeValidationWorkflow  (@validate)"]
    COS --> SA["SolutionArchitectWorkflow  (@architect)"]
    COS --> GOV["GovernanceWorkflow  (@govern)"]
    DISC --> PY["Python AI Worker (LangGraph / DSPy)"]
    MAP --> PY
    KV --> PY
    SA --> PY
    GOV --> PY
    PY --> LLM["LLM Providers (Azure AI Foundry / Groq / Ollama / OpenAI)"]
    PY --> EKM["Enterprise Knowledge Model"]
    EKM --> PG[("PostgreSQL (engagement_states)")]
    EKM --> REDIS[("Redis")]
    EKM --> QDRANT[("Qdrant")]
    EKM --> GRAPH[("Neo4j + Graphiti)"]

    SA --> CAT["Capability Catalogue"]
    CAT --> REC["Solution Recommendation Engine"]
    REC -.-> SA

    GOV --> EAP["Enterprise Architecture Pack <br/> <i>12 artifacts</i>"]
    EAP -->|"download"| DOWNLOAD["Artifact Download"]

    subgraph EVIDENCE["Evidence Layer"]
        PROV["Provenance: source, confidence, evidence ID, timestamp, extraction method"]
    end
    PY --> EVIDENCE
    EKM --> EVIDENCE

    subgraph OPTIONAL["Optional Export (not required for core product)"]
        N8N["n8n compiler <br/> <i>canonical optional export</i>"]
        ADK["ADK-Go compiler"]
        PA["PydanticAI compiler"]
        SA2["smolagents compiler"]
    end
    GOV -.->|"optional export_payload"| N8N
    GOV -.->|"optional"| ADK
    GOV -.->|"optional"| PA
    GOV -.->|"optional"| SA2
```

**Key components**

| Layer | Responsibility |
|-------|----------------|
| **Interface** (`apps/core/` HTMX) | Web workspace, chat, uploads, approval UI, exports UI. |
| **Go Core** (`apps/core/`) | Fiber HTTP server, HTMX templates, SSE streaming, `@mention` routing, Temporal client. |
| **Control plane** | `ChiefOfStaffWorkflow` — intent classify, route, deterministically merge `EngagementState` patches, summarize. |
| **Specialist workflow layer** | 5 canonical specialists + ChiefOfStaff control plane (= 6 total). |
| **Python AI Worker** (`apps/ai/`) | LangGraph/DSPy agents per domain; builds the Ontology; proposes governed writes; compiles drafts. |
| **LLM providers** | OpenAI-compatible SDK → Azure AI Foundry, Groq, Ollama, OpenAI (auto-detected). |
| **Enterprise Knowledge Model** (canonical IR) | PostgreSQL (`engagement_states`), Redis, Qdrant, Neo4j + Graphiti. Typed entities with full provenance: every entity carries `source_refs`, `confidence_score`, `evidence_id`, `extracted_at`, `extraction_method`. |
| **Capability Catalogue** | Registry of enterprise capabilities mapped to solution patterns. Powered by `SolutionArchitectWorkflow`. |
| **Solution Recommendation Engine** | Maps validated knowledge to recommended solution architectures. |
| **Evidence Layer** | Provenance-preserving pipeline: every ontology entity tracks source, confidence, evidence ID, timestamp, and extraction method. Enforced by Pydantic validators across all ontology writes. |
| **Governance** | `GovernanceWorkflow` enforces approval gating, blast-radius checks, and audit logging. Produces the Enterprise Architecture Pack (12 artifacts). |
| **Runtime / export** (optional) | Deterministic compilers for n8n (canonical optional target), ADK-Go, PydanticAI, smolagents behind a `RuntimeCompiler` ABC + `get_compiler()` factory. **Windmill** — DEPRECATED (ADR-009 superseded). Compilation is export-only; no deployment or execution. |
| **Observability** | Langfuse tracing, audit logs, approval history. |

---

## Request / Response Flow

A typical `@mention` query — from the user's message to a streamed answer, with the specialist → governance approval → deterministic export branch:

```mermaid
sequenceDiagram
    actor User
    participant Core as Go Core (Fiber)
    participant Router as @mention Router
    participant COS as ChiefOfStaffWorkflow
    participant Spec as Specialist Workflow
    participant Agent as Python AI Worker
    participant LLM as LLM Provider
    participant Gov as GovernanceWorkflow
    participant Comp as Compilers (n8n / custom_agent)
    participant UI as HTMX UI (SSE)
    participant Human as Approver

    User->>Core: POST /api/command/chat/send "@discover extract facts from upload"
    Core->>Router: extract @mention
    Router-->>Core: ChiefOfStaffWorkflow (O(1) map)
    Core->>UI: SSE event:chat (user bubble)
    Core->>COS: ExecuteWorkflow("ChiefOfStaffWorkflow", input)
    COS->>Spec: route to DiscoveryWorkflow
    COS->>Agent: dispatch activity
    Agent->>LLM: extraction / synthesis
    LLM-->>Agent: result
    Agent-->>COS: SpecialistResponse + EngagementState patch
    COS-->>Core: merged summary
    Core->>UI: SSE event:chat (answer bubble)
    alt requires governance approval
        Spec->>Gov: propose PlannedAction / ExecutableWorkflowDraft
        Gov->>UI: SSE event:hitl (approval request)
        Human->>Core: POST /api/command/approvals/:id/approve
        Core->>Gov: SignalWorkflow("hitl-approval", true)
        Gov-->>Comp: approved → compile export_payload
        Comp-->>Core: artifact exported
    end
```

The dispatch runs in a goroutine with a 5-minute context timeout and a non-blocking `tryBroadcast()` (`select { case ch <- msg: default: log }`) so the UI shows a "🤔 Thinking…" bubble immediately and never blocks the HTTP handler.

---

## Ontology Layer

The V5.2 Ontology is the **canonical shared model** of a business engagement. It is fully typed (Pydantic v2, `extra="forbid"`, `strict=True`) and TDD-verified. It comprises 6 primary Object Types, the `ExecutableWorkflowDraft` and `EngagementState` shared-state shapes, and 11 semantic link types. Every entity carries full provenance (source, confidence, evidence ID, timestamp, extraction method) enforced by the Evidence Layer.

| Component | File | What it does |
|-----------|------|--------------|
| **Object Types** | `apps/ai/src/ontology/object_types.py` | 6 strict Pydantic v2 models: `Party`, `Engagement`, `MoneyEvent`, `Issue`, `Message`, `PlannedAction`. |
| **Link Types** | `apps/ai/src/ontology/link_types.py` | `LINK_TYPES` registry of 11 semantic links + `resolve_link()`. |
| **Action Types** | `apps/ai/src/ontology/action_types.py` | Full `PlannedAction` model + action registry. |
| **Workflow Drafts** | `apps/ai/src/ontology/workflow_drafts.py` | `ExecutableWorkflowDraft` — single source of truth; `export_payload` only set by compiler; `status="activated"` only by Governance. |
| **Engagement State** | `apps/ai/src/schemas/engagement_state.py` | `EngagementState` canonical shared state (mode, phase, ontology objects/links, truth findings, drafts, actions). |
| **Governed Writes** | `apps/ai/src/ontology/governance.py` | `@governed_write` decorator enforcing the `OBJECT_WRITE_POLICY` blast-radius gate; only `GovernanceWorkflow` finalizes external execution. |

### Object Types, Links & Shared State

```mermaid
classDiagram
    class Party {
        +str id
        +Literal kind
        +str name
        +Literal status
        +str owner
        +list~str~ contact_points
        +list~str~ source_refs
    }
    class Engagement {
        +str id
        +Literal kind
        +str title
        +Literal status
        +float value
        +str due_date
        +list~str~ source_refs
    }
    class MoneyEvent {
        +str id
        +Literal kind
        +float amount
        +str currency
        +Literal status
        +str due_date
        +str counterparty_id
    }
    class Issue {
        +str id
        +Literal kind
        +Literal severity
        +Literal status
        +str opened_at
        +str resolved_at
        +str summary
    }
    class Message {
        +str id
        +Literal channel
        +str thread_id
        +Literal direction
        +str summary
        +Literal sentiment
        +bool needs_action
    }
    class PlannedAction {
        +str id
        +str type
        +Literal blast_radius
        +Literal status
        +str requested_by
        +Literal target_object_type
        +str target_id
        +bool requires_approval
    }
    class ExecutableWorkflowDraft {
        +str id
        +Literal runtime
        +str name
        +Literal status
        +dict trigger
        +list~dict~ steps
        +dict export_payload
    }
    class EngagementState {
        +str engagement_id
        +str tenant_id
        +Literal workspace_mode
        +Literal phase
        +list~dict~ ontology_objects
        +list~dict~ ontology_links
        +list~dict~ truth_findings
        +list~dict~ executable_workflow_drafts
        +list~dict~ planned_actions
    }

    Party "1" --> "*" Engagement : party_engagement
    Engagement "1" --> "*" MoneyEvent : engagement_money_event
    Engagement "1" --> "*" Issue : engagement_issue
    Message "1" --> "*" Party : message_party
    Message "1" --> "*" Engagement : message_engagement
    Issue "1" --> "*" PlannedAction : issue_planned_action
    MoneyEvent "1" --> "*" PlannedAction : money_event_planned_action
    Party "1" --> "*" PlannedAction : party_planned_action
    Engagement "1" --> "*" PlannedAction : engagement_planned_action
    ExecutableWorkflowDraft "1" --> "*" PlannedAction : workflow_action
    ExecutableWorkflowDraft "1" --> "*" Party : workflow_object_dependency
    EngagementState "1" --> "*" Party : holds
    EngagementState "1" --> "*" ExecutableWorkflowDraft : holds
```

> **Canonical ontology types (6):** The V5.2 product contract specifies exactly 6 canonical ontology object types: Party, Engagement, MoneyEvent, Issue, Message, PlannedAction. These are the entity types that the OntologyAI core populates, links, and reasons over. Each type carries the Evidence Layer provenance envelope (source, confidence, evidence ID, timestamp, extraction method) to ensure traceability.

### `@governed_write`

The `@governed_write` decorator enforces human-in-the-loop approval for consequential ontology writes. Two independent gates trigger a required `PlannedAction`:

1. **Explicit flag** — the property is `requires_approval=True` in `OBJECT_WRITE_POLICY`.
2. **Blast-radius threshold** — the effective blast radius is at/above the configured threshold (default `"medium"`; `"low"` writes proceed).

When a `PlannedAction` is required, the decorator **blocks** the underlying write and returns the `PlannedAction` for the caller to submit for approval. Only `GovernanceWorkflow` may set `status=activated`, `executing`, `completed`, or `exported` on external side effects.

```python
@governed_write(object_type="Party", property_name="status", requested_by="Discovery")
def governed_party_update(party_id: str, **kwargs): ...
```

---

## Project Structure

```
apps/
  core/                     # Go Modular Monolith (control / gateway)
    cmd/
      server/               # HTTP server entrypoint
      worker/               # Temporal worker entrypoint
    internal/
      web/                  # HTTP handlers (Fiber + HTMX + SSE)
        handler.go          # All endpoints, @mention routing (O(1) map → 15+ aliases / 6 V5.2 workflows)
        sse.go              # SSE handler (SetBodyStreamWriter + SSEHub)
        command_center_test.go
        templates/
          command_center.html
          partials/         # HTMX partials (workspace screens + ontology setup wizard partials)
      agents/               # Go agent definitions
      config/               # LLM configuration
      db/                   # sqlc generated code
      database/             # Connection utilities
      temporal/             # Temporal client (SignalWorkflow, ExecuteWorkflow)
      workflow/             # Temporal workflows & stubs
    sqlc.yaml               # sqlc configuration
  ai/                       # Python AI Worker
    src/
      ontology/             # V5.2 — Object Types, Link Types, Action Types, Workflow Drafts, Governance, Evidence
        object_types.py     # 6 canonical types
        link_types.py       # 11 link types
        action_types.py     # PlannedAction + registry
        workflow_drafts.py  # ExecutableWorkflowDraft (source of truth)
        adapter.py          # mission_state_to_ontology (read-only bridge)
        governance.py       # @governed_write + OBJECT_WRITE_POLICY
        evidence.py         # Evidence provenance model — source, confidence, evidence_id, timestamp, extraction_method
        capability_catalogue.py # Registry of enterprise capabilities mapped to solution patterns
        solution_recommendation.py # Solution recommendation engine — maps validated knowledge to architectures
      schemas/              # Pydantic models (engagement_state, specialist_response, workflow_spec, sop, executable_workflow_draft)
        ontology_setup_state.py # OntologySetupState + SetupStep enum + step data models (28 state model tests)
      workflows/            # Temporal workflow definitions (6 V5.2 canonical)
        chief_of_staff_workflow.py   # @workflow.defn(name="ChiefOfStaffWorkflow")
        discovery_workflow.py        # @workflow.defn(name="DiscoveryWorkflow")
        ontology_mapping_workflow.py # @workflow.defn(name="OntologyMappingWorkflow")
        knowledge_validation_workflow.py # @workflow.defn(name="KnowledgeValidationWorkflow")
        solution_architect_workflow.py   # @workflow.defn(name="SolutionArchitectWorkflow")
        governance_workflow.py       # @workflow.defn(name="GovernanceWorkflow")
      runtime/              # Deterministic compilers (optional export targets) + artifact export
        base.py                 # RuntimeCompiler ABC
        n8n_compiler.py         # n8n JSON compiler (canonical optional export)
        n8n_client.py           # n8n REST API client
        adk_go_compiler.py      # ADK-Go: generates main.go + tools.go
        pydantic_ai_compiler.py # PydanticAI: generates agent.py w/ BaseModel
        python_agent_compiler.py# smolagents: generates CodeAgent worker.py
        custom_agent_compiler.py# Legacy agent config compiler
        artifact_export.py      # Artifact export service
      session/              # EngagementState store (canonical) + mission_state read bridge
      memory/               # Graphiti, Qdrant, spine
      integrations/         # Stripe, Plaid, Slack, ERPNext, HubSpot, QuickBooks
      services/             # Evidence layer, trust battery, provenance validation
        engagement_state_store.py # Async PostgreSQL CRUD (asyncpg) for EngagementState
      activities/           # Temporal activity definitions
      worker.py             # Registers all workflows (6 V5.2 canonical + legacy V4.1) + activities
    tests/                  # Pytest suite (1286 passing / 32 skipped + V5.2 suites)
    pyproject.toml          # Python dependencies
```

---

## Getting Started

### Prerequisites

- **Docker** (Temporal, Qdrant, PostgreSQL, Neo4j)
- **Go 1.24**
- **Python 3.13** with [`uv`](https://github.com/astral-sh/uv)

### Quickstart

```bash
# 1. Start infrastructure (Temporal, Qdrant, PostgreSQL, Neo4j)
make up

# 2. Run the Go server (HTTP + HTMX + SSE workspace)
cd apps/core && go run cmd/server/main.go

# 3. Run the Go Temporal worker (in a second terminal)
cd apps/core && go run cmd/worker/main.go

# 4. Install Python deps and run the Python Temporal worker (third terminal)
cd apps/ai && uv sync
cd apps/ai && uv run python -m src.worker

# 5. Open the workspace landing page
#    http://localhost:8080
#    The workspace presents a guided discovery flow: frame a problem, add evidence,
#    review the business map, validate knowledge, explore solution recommendations.
```

### Run the tests

```bash
# Go — all packages
cd apps/core && go test ./...

# Go — web handlers only
cd apps/core && go test ./internal/web/... -v

# Python — full suite (1286 passing / 32 skipped + V5.2 schema/workflow/governance/export suites)
cd apps/ai && uv run pytest tests/ -v

# Python — ontology TDD suites
cd apps/ai && uv run pytest tests/test_ontology_schema.py tests/test_link_and_action_registry.py tests/test_engagement_state.py tests/test_executable_workflow_draft.py -v
```

### Environment variables (LLM providers + legacy modules)

The system uses the official OpenAI-compatible SDK, auto-detecting the configured provider:

| Provider | Variables |
|----------|-----------|
| **Azure AI Foundry** | `AZURE_OPENAI_ENDPOINT`, `AZURE_OPENAI_API_KEY` |
| **Groq** | `GROQ_API_KEY` |
| **OpenAI** | `OPENAI_API_KEY` |
| **Ollama** (local) | `OLLAMA_BASE_URL`, `OLLAMA_API_KEY` |

| Control | Variable | Default |
|---------|----------|---------|
| Temporal task queue | `ONTOLOGYAI-MAIN-QUEUE` (fallback `TRACKGUARD-MAIN-QUEUE`) | `TRACKGUARD-MAIN-QUEUE` |
| Legacy FDE modules | `LEGACY_FDE_MODULES=on` | off (gated) |

Secrets live in a local `.env` file (never committed). See `internal/config/llm.go` for auto-detection logic.

---

## Architecture Decision Records

These ADRs capture the load-bearing architectural decisions. Each follows an RFC 2119-style **Status / Context / Decision / Consequences** structure.

### ADR-001: Rebrand TrackGuard / Sarthi → OntologyAI

- **Status:** Accepted
- **Context:** The product was known as *TrackGuard* / *Sarthi*. As the scope expanded from alert-tracking to a full business Ontology with governed specialist agents, the old name no longer reflected the product. A rebrand risked breaking existing deployments, chat aliases, migration filenames, and Docker/container names that external tooling depended on.
- **Decision:** Rebrand the product to **OntologyAI** across all user-facing surfaces (page titles, display names, documentation). To preserve compatibility we **MUST** keep:
  - the `@sarthi` chat alias (and `@agent`, `@qa`, `@ask`) routing to `ChiefOfStaffWorkflow`;
  - SQL migration filenames and Docker service/container names (e.g. `iterateswarm-api`);
  - the Temporal task queue constant `TRACKGUARD-MAIN-QUEUE` (now the fallback default for `ONTOLOGYAI-MAIN-QUEUE`).
  Internal Pydantic `Sarthi*` types were fully renamed to `OntologyAI*` with zero dangling references.
- **Consequences:**
  - *Positive:* A name that matches the product's actual scope; clean, consistent branding for newcomers.
  - *Negative:* Two names coexist in the codebase (product = OntologyAI; some infra identifiers retain the legacy name), which must be documented to avoid confusion (see [V5.2 Active Roster vs Legacy Compatibility](#v52-active-roster-vs-legacy-compatibility)).

### ADR-002: Six frozen canonical workflows with O(1) `@mention` map routing

- **Status:** Accepted
- **Context:** V4.2 froze a 5-specialist roster (`ChiefOfStaffWorkflow`, `FPAWorkflow`, `GrowthAnalyticsWorkflow`, `ReliabilityWorkflow`, `CommsWorkflow`) with O(1) map routing. V5.1 reframes the product as a self-serve FDE companion + multi-agent FDE operating system, replacing the domain-specialist roster with a discovery-to-deployment workflow roster.
- **Decision:** Freeze **six** canonical workflows — `ChiefOfStaffWorkflow` (control-plane orchestrator), `DiscoveryWorkflow`, `OntologyMappingWorkflow`, `TruthAnalysisWorkflow`, `WorkflowBuilderWorkflow`, `GovernanceWorkflow` — and keep the declarative `map[string]specialistRoute` providing O(1) lookup. The control-plane alias set (`@ontologyai`, `@agent`, `@ask`, `@chief`, `@sarthi`) routes to `ChiefOfStaffWorkflow`; specialist aliases (`@discover`, `@map`, `@truth`, `@build`, `@govern`) route to the five specialists. Adding a workflow is now **one map entry + one Python workflow class**; no handler changes.
- **Consequences:**
  - *Positive:* O(1) routing; new workflows are data-driven; the roster is stable and documented; the control plane cleanly separates orchestration from domain work.
  - *Negative:* Workflow type strings are not compile-time checked — a typo fails at runtime. Mitigated by a test that verifies every route's workflow name matches a registered Temporal workflow.

### ADR-003: Governance exclusivity — only `GovernanceWorkflow` finalizes external execution

- **Status:** Accepted
- **Context:** Specialists can propose writes with real-world impact (change money state, send a message, activate a workflow). Unbounded autonomous writes are unsafe for a founder/client-facing product. V4.2 introduced `@governed_write` routing consequential mutations through a `PlannedAction`; V5.1 extends this so that *no* workflow except `GovernanceWorkflow` may set `status=activated`, `executing`, `completed`, or `exported` on external side effects.
- **Decision:** Keep `@governed_write` plus an `OBJECT_WRITE_POLICY` registry. A write is blocked and routed through a `PlannedAction` (requiring human approval) when either (a) the property is `requires_approval=True`, or (b) its effective blast radius is at/above a configurable threshold (default `"medium"`; `"low"` writes proceed). Additionally, `GovernanceWorkflow` is the sole executor of final external side effects; `ExecutableWorkflowDraft.status="activated"` may only be set by `GovernanceWorkflow`. The decorator mirrors the Temporal HITL pattern: it returns the `PlannedAction` and intentionally does **not** execute the underlying write.
- **Consequences:**
  - *Positive:* Consequential writes are never silent; a single, overridable policy source governs blast radius; governance is the single gate before any side effect; the contract is unit-testable in isolation.
  - *Negative:* Every governed write adds a round-trip (propose → approve → execute); the policy source must be kept in sync with the actual specialist actions.

### ADR-004: Deterministic compiler / export purity rule

- **Status:** Accepted
- **Context:** V5.1 must generate deployable `ExecutableWorkflowDraft` artifacts for n8n and custom-agent runtimes. Letting the LLM freehand the export payload risks malformed, unvalidated, or unsafe automation. The thin-LLM / fat-deterministic-core principle forbids the LLM from generating export payloads directly.
- **Decision:** All compilers (n8n, ADK-Go, PydanticAI, smolagents) are **pure, deterministic functions** extending a `RuntimeCompiler` ABC with a `compile(draft: dict) -> dict` contract. The LLM may propose workflow *structure* (steps, decision points, approvals) but **must never write `export_payload`**. `export_payload` is only populated by the compiler code; this is enforced by a model validator in `workflow_drafts.py` and asserted in `test_runtime_compilers.py` / `test_n8n_compiler.py`.
- **Consequences:**
  - *Positive:* Byte-stable, validated, inspectable exports; the LLM is kept in its safe lane (ambiguity, synthesis, narrative); exports are reproducible and testable.
  - *Negative:* Compiler logic must be maintained for each runtime target; structure proposed by the LLM must be normalized by the compiler before export.

### ADR-005: `EngagementState` as canonical shared state (with `mission_states` read-only bridge)

- **Status:** Accepted
- **Context:** V4.2 used `MissionState` as the operational state store. V5.1 needs a richer, phase-aware shared state (`EngagementState`) covering discovery notes, ontology objects/links, truth findings, workflow specs, executable drafts, and planned actions — with `workspace_mode` and `phase` as first-class fields. Deleting `mission_states` outright would break the existing read path and downstream consumers.
- **Decision:** Make `EngagementState` the **canonical write target** (persisted in `engagement_states`). Keep `mission_states` as a **read-only bridge for one version**; `mission_state_to_ontology` remains callable until the adapter is fully migrated to `MoneyEvent`. All specialist workflows read `EngagementState` first and write back a typed, deterministically-merged patch; unknown keys are rejected and merge conflicts log + preserve provenance. `workspace_mode` is immutable after creation unless explicitly migrated.
- **Consequences:**
  - *Positive:* One shared, typed source of truth; no agent owns a private model of the business; clean migration path without breaking existing infra.
  - *Negative:* Two state shapes coexist for one version; the bridge adds a small maintenance burden until `mission_states` is retired.

### ADR-006: SSE + HTMX `SetBodyStreamWriter` for streaming chat

- **Status:** Accepted
- **Context:** The original client used raw JavaScript `EventSource` with client-side DOM construction for every chat bubble — duplicating template logic and adding ~40 lines of reconnect/parse JS. Synchronous `run.Get()` in the HTTP handler also blocked responses for up to 60s.
- **Decision:** Stream chat over Server-Sent Events using Fiber's `SetBodyStreamWriter` with a `*bufio.Writer`, and let HTMX's `hx-ext="sse"` manage the connection lifecycle declaratively (`sse-connect` / `sse-swap` / `hx-swap`). The server renders chat bubbles as HTML fragments (`renderChatBubble()`) and pushes them as named SSE events (`event: chat`); all user/LLM text is `html.EscapeString()`-escaped. An `SSEHub` provides event-type-filtered, per-subscriber fan-out (buffered 64).
- **Consequences:**
  - *Positive:* ~40 fewer lines of JS; auto-reconnect built in; single source of truth for HTML; XSS-safe; immediate "Thinking…" feedback via non-blocking `tryBroadcast()`.
   - *Negative:* HTML fragments over SSE inflate bandwidth vs JSON; harder to integrate non-HTMX clients; error handling moves into goroutine closures (log-based monitoring required).

### ADR-007: Reuse n8n as the invisible execution runtime; build the OntologyAI canvas on the canonical model

- **Status:** Accepted (locked V5.1, PR #33, branch `feature/ontologyai-v5.1`)
- **Context:** V5.1 already ships the canonical `ExecutableWorkflowDraft` model, deterministic compilers (`runtime/n8n_compiler.py`, `runtime/custom_agent_compiler.py`, `runtime/artifact_export.py`), 6 active workflows, and `EngagementState` with deterministic `merge_patch`. The open question was whether to build a workflow engine/canvas from scratch or reuse an existing one. Building from scratch would duplicate mature execution/integration/retry/scheduling/credential tooling and slow "finishing the product."
- **Decision:** **Do NOT build the workflow engine or canvas from scratch.** Reuse **n8n** as the execution/runtime layer, but build **OntologyAI's own client-facing AI workspace and live workflow canvas** on top of the canonical `ExecutableWorkflowDraft` model. The final split:

  | Layer | Decision | Why |
  |-------|----------|-----|
  | Client experience | Build your own | Differentiation: conversation, transcript extraction, evidence, AI suggestions, FDE collaboration, governance, pilot creation |
  | Workflow data model | Build your own typed canonical model | Lets the AI generate/validate/explain/version/govern workflows deterministically |
  | Execution runtime | Reuse n8n first | n8n provides execution, integrations, retries, scheduling, credentials, ops tooling |
  | Agent orchestration | Keep existing Temporal/Python | 6 workflow roles, typed shared state, governance, deterministic compilers already exist |
  | Agent framework | Use one, not two | Do not add ADK merely because fashionable; smolagents only sandboxed utility |

  **Licensing constraint:** the native n8n editor is **NOT** exposed to clients in the first release (n8n OEM/Embed license required). The OntologyAI canvas *looks and behaves like* a simplified n8n canvas; every edit is saved into `ExecutableWorkflowDraft`; approved drafts compile to n8n JSON and deploy to the client's own n8n instance or a managed n8n runtime only after the appropriate commercial agreement. Run state, errors, and activation status are reflected back into OntologyAI read-only.

  **Stack ownership:** OntologyAI owns the workspace, ingestion, evidence, ontology/truth generation, canvas, governance UI, versioning, and the compile/export button. n8n owns execution, connectors, scheduling/retries, and credential handling on the client instance. Python owns extraction, retrieval, validation, deterministic compilation, policy/approval gates, agent coordination, and audit trail.

  **Multi-runtime compilers (ADR-008):** Four deterministic compilers now exist behind a `RuntimeCompiler` ABC: n8n (automation), ADK-Go (Go-native agents), PydanticAI (typed Python agents), and smolagents/python_agent (sandboxed utility). Runtime selection is deterministic based on workflow traits. See [`ADR-008`](#adr-008-multi-runtime-compiler-architecture).

  **ADK vs smolagents:** Temporal + typed Python = backbone; ADK = optional orchestration enhancement only (not added merely because fashionable); smolagents = sandboxed utility worker (document exploration, safe data transforms, connector research, isolated code analysis) — agent-generated code must NOT access production network, credentials, database, or the n8n instance.

  **Canonical node vocabulary (12 nodes):** Trigger, Human input/form, AI extraction or classification, Condition/branch, HTTP/API action, Send message, Create/update record, Approval gate, Delay/schedule, Transform data, Error/fallback, End/success metric. These map to n8n during compilation; new integrations/bespoke nodes come later.
- **Consequences:**
  - *Positive:* No duplicated execution engine; fast path to a finished product; clear differentiation in the client experience; deterministic, governed, versioned workflow authoring; n8n's ops tooling reused for free.
   - *Negative:* A license boundary must be respected (no exposed n8n editor in first release); the OntologyAI canvas must stay in sync with `ExecutableWorkflowDraft`; deployment to a managed n8n runtime is gated on a commercial agreement.

### ADR-008: Multi-Runtime Compiler Architecture

- **Status:** Accepted
- **Context:** V5.1 originally shipped two deterministic compilers (`n8n`, `custom_agent`). As three agent-runtime patterns emerged (typed Python, Go-native, sandboxed utility), a single monolith compiler became untenable. The product director confirmed LangGraph + OntologyAI stays the single control plane.
- **Decision:** Create a `RuntimeCompiler` ABC with a `get_compiler()` factory. Four deterministic compilers each produce a runtime-specific artifact from the canonical `ExecutableWorkflowDraft`: n8n (JSON), ADK-Go (Go source), PydanticAI (Python agent), smolagents (sandboxed worker). Runtime selection is deterministic based on workflow traits.
- **Consequences:**
  - *Positive:* Each compiler is isolated, testable, and swappable without changing the product brain.
  - *Positive:* 15 TDD tests cover all 4 targets + ABC + factory — byte-stable, reproducible exports.
  - *Negative:* Each new runtime target requires a new compiler module; generated code must be reviewed by client teams.

### ADR-009: Windmill replaces n8n as primary execution runtime

- **Status:** DEPRECATED / Superseded (V5.2 reframing — Windmill was a transitional target; n8n remains canonical optional export)
- **Context:** n8n served as the execution runtime throughout V5.1 development. Windmill emerged as a better fit for execution (native Python/TypeScript scripts, built-in approvals, AGPL license) and was adopted as a transitional primary target during V5.1.
- **Decision:** Windmill is **DEPRECATED** as of V5.2. The product reframes from "deployment & execution" to "discovery, knowledge validation, and solution design." Runtime compilation is now an **optional export** target only. n8n remains the canonical optional export target for clients that require deployable workflow artifacts. No runtime is required to use OntologyAI V5.2.
- **Consequences:**
  - *Positive:* Simplified architecture — no Windmill dependency, no deployment gate, no runtime credential management.
  - *Negative:* Clients requiring deployable workflow artifacts use n8n compiler export (canonical optional target).

---

## V5.2 Active Roster vs Legacy Compatibility

The default active V5.2 Temporal worker registers exactly **6 canonical workflows**:

| # | Workflow | Role | Category |
|---|----------|------|----------|
| 1 | `ChiefOfStaffWorkflow` | Control-plane orchestrator | V5.2 canonical |
| 2 | `DiscoveryWorkflow` | Evidence intake & fact extraction | V5.2 canonical |
| 3 | `OntologyMappingWorkflow` | Object/link type population | V5.2 canonical |
| 4 | `KnowledgeValidationWorkflow` | Cross-source truth diagnosis & provenance validation | V5.2 canonical |
| 5 | `SolutionArchitectWorkflow` | Capability mapping & solution recommendation | V5.2 canonical |
| 6 | `GovernanceWorkflow` | Approval gate & Enterprise Architecture Pack generation | V5.2 canonical |

**Legacy V4.1 workflows** (Pulse, Investor, FPA, GrowthAnalytics, etc.) — gated behind `LEGACY_FDE_MODULES=on`. Default: off.

When `LEGACY_FDE_MODULES=on` is set:
- All 11 legacy V4.1 workflows are added alongside the active roster

---

## Contributing & Conventions

- **Feature branches:** `git checkout -b feature/description` — never commit directly to `main`.
- **Conventional Commits:** `feat:`, `fix:`, `refactor:`, `docs:`, `test:`, `chore:`.
- **Never commit to `main`.** Open a PR from your feature branch.
- **Secrets:** use a local `.env` file; never commit secrets.
- **Agent guidelines:** full coding standards, build/test commands, and the specialist route-map pattern live in [`AGENTS.md`](./AGENTS.md) at the repo root.
- **Database:** use `sqlc` for type-safe SQL; regenerate generated code after schema changes.

---

## Test Coverage

| Suite | Tests | Status |
|-------|-------|--------|
| Python Unit Tests | 1286 passing / 32 skipped (baseline + V5.2 schema/workflow/governance suites) | ✅ |
| V5.2 Schema & State | object_types, link_types, action_types, engagement_state, specialist_response, workflow_spec, sop, executable_workflow_draft | ✅ |
| V5.2 Workflows (6 workflows) | Discovery, Ontology Mapping, Knowledge Validation, Solution Architect, Governance + workflow_names | ✅ |
| V5.2 Multi-Runtime Compilers | n8n, ADK-Go, PydanticAI, smolagents + ABC + factory | ✅ |
| V5.2 Compilers / Export | n8n, custom_agent compile + export tests | ✅ |
| V5.2 Governance / HITL | Governance workflow (17 tests), HITL signals | ✅ |
| **V5.2 Ontology Setup Wizard** | Setup state models (28 tests), Go handler (17 tests), ChiefOfStaff wizard routing (52 tests) — **97 total** | ✅ |
| **V5.2 Infra & Registration** | Worker registration (5 tests), EngagementStateStore (8 tests) | ✅ |
| V5.2 ChiefOfStaff routing | Route map (15+ aliases), intent classification, specialist routing — integration tested | ✅ |
| Go HTMX Web Handlers + Wizard | Route map (15+ aliases), workspace panels, ontology setup wizard (17 tests) | ✅ |
| Go Build | Clean | ✅ Binary compiles |
| E2E Smoke Test | 9/9 | ✅ Real Docker + real LLM |
| DB Tests | — | 🟡 Skip (requires PostgreSQL container) |

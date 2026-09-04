# OntologyAI — AI-Powered B2B SaaS Customer Onboarding Operations

> Frozen portfolio vertical: governed AI workforce for B2B SaaS onboarding, from Closed-Won to First Value.
>
> Branch: `feature/ontologyai-onboarding-restructure` | 170 Python tests green | ruff clean

## Contents

- [Vertical](#vertical)
- [Authority Boundary](#authority-boundary)
- [Domain Model](#domain-model)
- [Runtime Scope](#runtime-scope)
- [Repo Map](#repo-map)
- [Getting Started](#getting-started)
- [Tests](#tests)
- [Status and Roadmap](#status-and-roadmap)
- [Conventions](#conventions)

## Vertical

OntologyAI is an AI workforce for **B2B SaaS customer onboarding operations**.

Covered workflow:

```
Closed-Won → Handoff → Kickoff → Implementation → Blocker Resolution → First Value
```

Missions M1–M6 operate inside this workflow (validate handoff, prepare kickoff, investigate blocker, recover milestone, detect drift, readiness review).

Explicitly out of scope: generic RevOps, retention, upsell, and whole-lifecycle COO coverage. Earlier README versions described a broad Virtual COO office across Marketing/Sales/Operations/Finance pillars; that direction is superseded.

## Authority Boundary

Core principle:

> "LLMs propose intent. Deterministic infrastructure decides whether intent is valid, authorized, safe, idempotent, executable, and successfully completed."

Fixed pipeline:

```
Evidence → Context Checkpoint → Employee / Mission / Skill → ActionIntent
  → CONTROL PLANE (schema, auth, RBAC/scopes, policy, evidence gate,
     idempotency, concurrency, approval)
  → AuthorizedAction → Capability Executor → Business Verification
  → Immutable Audit / Timeline → Mission + Memory + Workspace
```

Rules:

- Skills and LLMs may only emit `ActionIntent` (untrusted proposal).
- Only the Control Plane may produce `AuthorizedAction`.
- Only the Capability Executor may touch connectors.
- Every action records reason, evidence IDs, policy decision, approval, idempotency key, verification result, and audit event.
- Connector payloads never become instructions (see ADR-012).

## Domain Model

`Onboarding` is the first-class aggregate. `Mission` is a bounded AI work unit operating within one onboarding via `Mission.onboarding_id` (one customer has 0..n onboardings; one onboarding has 0..n missions).

- `Task` is planned work (milestones, checklist steps, implementation items).
- `Issue` is a deviation (blocker, risk, drift) requiring investigation or recovery.
- The two types are separate; a task never doubles as a blocker report.
- Connector data (Slack, Salesforce, Jira, Notion) is evidence with provenance (source, id, timestamp, freshness), never instruction. Injection strings are quoted as evidence and cannot change authority, policy, or routing.

References:

- `docs/adr/ADR-010-onboarding-domain-aggregate.md`
- `docs/adr/ADR-011-authority-boundary.md`
- `docs/adr/ADR-012-external-data-boundary.md`

## Runtime Scope

Runtime profile: `onboarding_v6` (see `apps/ai/config/runtime.yaml`).

Active integrations: `slack`, `salesforce`, `jira`, `notion`.

Legacy integrations (`stripe`, `plaid`, `erpnext`, `hubspot`, `quickbooks`) are archived and fail-closed under this profile: the worker never imports them and any proposal referencing them is denied by policy.

## Repo Map

- `apps/ai/src/control_plane/` — authority boundary; 9 thin modules: `ingress.py`, `contracts.py`, `authorization.py`, `policy.py`, `idempotency.py`, `approval.py`, `executor.py`, `verification.py`, `audit.py`.
- `apps/ai/src/mission/skills/onboarding_ops.py` — skill `investigate_onboarding_blocker`; LLM does root-cause reasoning only, then submits one `ActionIntent`.
- `apps/ai/src/mission/blocker_investigation_mission.py` — runner `run_blocker_investigation_mission`; Slack-to-evidence ingestion, context checkpoint, frozen-timeline append, memory checkpoint, EmployeeRuntime dispatch.
- Contract tests — `apps/ai/tests/test_action_intent_contract.py`, `apps/ai/tests/test_onboarding_aggregate_contract.py`, `apps/ai/tests/test_task_issue_contract.py`, `apps/ai/tests/test_evidence_guardrail_contract.py`, `apps/ai/tests/mission/test_skill_contracts.py`, `apps/ai/tests/deterministic/test_behavioral_contracts.py`; slice coverage in `apps/ai/tests/test_blocker_investigation_slice.py`.
- `apps/ai/config/runtime.yaml` — declares `runtime_profile: onboarding_v6`, enabled vs legacy integration lists.
- Canonical tracker: `Aparnap2/Ontology_AI`, issues #59–#65.

## Getting Started

### Prerequisites

- Docker (PostgreSQL, Temporal, Qdrant)
- Go 1.24
- Python 3.13 with [`uv`](https://github.com/astral-sh/uv)

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

# 5. Open the workspace
#    http://localhost:8080
```

### Environment variables

| Provider | Variables |
|----------|-----------|
| Azure AI Foundry | `AZURE_OPENAI_ENDPOINT`, `AZURE_OPENAI_API_KEY` |
| Groq | `GROQ_API_KEY` |
| OpenAI | `OPENAI_API_KEY` |
| Ollama (local) | `OLLAMA_BASE_URL`, `OLLAMA_API_KEY` |

Secrets live in a local `.env` file (never committed).

## Tests

```bash
# Go — all packages
cd apps/core && go test ./...

# Python — full suite
cd apps/ai && uv run pytest tests/ -v

# Lint
cd apps/ai && uv run ruff check src tests
```

Current gate on this branch: 170 Python tests green, ruff clean.

## Status and Roadmap

Completed on this branch: ADRs (010/011/012), canonical contracts, control-plane scaffold, legacy gating via `onboarding_v6`, governed blocker-investigation slice covering happy path, duplicate, unauthorized, missing evidence, policy violation, approval resume, connector failure, unverified-200, and injection-as-evidence.

Next: evidence checkpoint pipeline (#63), M1–M6 workforce config (#64), ACME E2E/ROI (#65), plus Go SSE wiring, Temporal parity, and migration 013.

Issues #59–#65 are tracked in `Aparnap2/Ontology_AI`; #59–#62 cover verification and commit of the work described above.

## Conventions

- Feature branches: `git checkout -b feature/description` — never commit directly to `main`.
- Conventional Commits: `feat:`, `fix:`, `refactor:`, `docs:`, `test:`, `chore:`.
- Full build/test/style rules live in `AGENTS.md`.

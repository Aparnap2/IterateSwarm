# OntologyAI V6 — Agent Responsibility Model & Prompt Contracts

> **Status:** Design — OntologyAI V6 (Enterprise Decision Runtime)
> **Scope:** Six specialist agents + ChiefOfStaff. Responsibility model, deterministic vs. LLM-augmented split, and the exact prompt contract schema interface for each agent.
> **Companion docs:** [`docs/llm-boundary.md`](./llm-boundary.md) (the frozen deterministic/LLM boundary) · [`apps/ai/src/decision/contracts.py`](../apps/ai/src/decision/contracts.py) (the strict Pydantic contracts).

---

## 1. Reframe: an Enterprise Decision Runtime, not an AI employee

OntologyAI V6 is an **Enterprise Decision Runtime**. It is *not* an "AI employee". It is a governed machine that turns raw enterprise evidence into decisions, workspaces, and — only when humans approve — external actions.

The runtime is composed of **six specialist agents** and a **ChiefOfStaff** router:

| # | Agent | Owns (verb) | Produces | LLM role |
|---|-------|-------------|----------|----------|
| 1 | **Discovery Agent** | Observe | `EvidenceRecord` | Parsing/extraction only — **no reasoning** |
| 2 | **Knowledge Agent** | Understand | Enterprise Knowledge Model (ontology, graph, resolution, conflicts) | Extraction / resolution hints — **not the source of truth** |
| 3 | **Decision Agent** | Reasoning | `Decision` + `DecisionAnalysis` | **LLM leads** reasoning; human governs |
| 4 | **Workspace Agent** | Projection | Decision Workspace (Executive/Engineering/Product views) | Narrative via **template rendering**, not freeform |
| 5 | **Execution Agent** | Actions | Executed external actions (Jira/Slack/Notion) | **None — never reasons** |
| 6 | **Evaluation Agent** | Learning | Outcome measures, KPIs, drift reports | Summarization of measured facts only |
| + | **ChiefOfStaff** | Orchestration | Routed `AgentTask`/`AgentResult` flow | Minimal: intent classification only |

### Non-negotiable hard rules (see also `docs/llm-boundary.md`)

1. **LLM may ONLY do:** parsing, extraction, summarization, reasoning, recommendation, narrative generation.
2. **LLM must NEVER:** modify databases directly, define the ontology, bypass governance/validation, or execute side effects.
3. **Hard pipeline rule:** `LLM → JSON → Pydantic schema validation → Canonical Model`. LLM output never enters the runtime without passing a strict Pydantic schema (`src/decision/contracts.py`). **Never** `LLM → business logic`.

---

## 2. Routing model — ChiefOfStaff

ChiefOfStaff is the **only** entry point for incoming work. It classifies intent and dispatches a typed `AgentTask` to exactly one specialist (or fans out when the specialist itself decomposes). It does **minimal reasoning** — intent classification is a bounded-label LLM call, everything else is a deterministic route map.

```
incoming message / trigger
        │
        ▼
┌─────────────────┐     classify_intent()          ┌──────────────────────┐
│  ChiefOfStaff   │ ─────────────────────────────► │  AgentTask (routing  │
│  (orchestration)│                                │  envelope, contracts)│
└─────────────────┘ ◄───────────────────────────── └──────────────────────┘
        │                                                │
        ▼ agent_name ∈ {Discovery, Knowledge, Decision, Workspace, Execution, Evaluation}
```

---

## 3. Agent contracts — one per agent

Each section below defines: **Role · Ownership · Inputs · Outputs · Deterministic operations · LLM operations · Prompt contract schema interface · System prompt architecture**.

> **Prompt contract schema interface** is expressed as a function/tool signature. The "tool" is the *output contract* the LLM must fill (validated by `src/decision/contracts.py`); the runtime then persists the validated canonical object. Any tool whose name is prefixed `def ` is a *runtime* function — the LLM fills its `result` contract; it never calls the runtime.

---

### 3.1 Discovery Agent — owns **Observe**

**Role:** Evidence acquisition. Turns raw connector/chat/upload/OCR output into validated `EvidenceRecord`s. It is a *sensor*, not a brain.

**Ownership:** `EvidenceRecord` lifecycle — parse → extract → validate → dedupe → store. Source freshness, provenance, and `hash` integrity.

**Inputs:** Raw payloads from connectors (Stripe, Plaid, Slack, ERPNext, HubSpot, QuickBooks), chat transcripts, uploads, screenshots/OCR, API responses.

**Outputs:** `list[EvidenceRecord]` (canonical entity in `src/entities/models.py`) with `provenance`, `structured_data`, `confidence`, and SHA-256 `hash`.

**Deterministic operations (pure code, no LLM):**
1. MIME sniffing, charset detection, size/format guard.
2. OCR invocation (tesseract/vision) — output is raw text, not semantics.
3. Raw checksum (SHA-256) and exact dedup against `hash = SHA256(tenant_id + canonical JSON structured_data)`.
4. Provenance stamping: `source`, `source_type`, `connector_version`, `extraction_method`, `timestamp`.
5. Pydantic validation of the produced `EvidenceRecord` — rejects records that fail schema before they persist.

**LLM operations (permitted):**
1. **Parsing** of unstructured text into `structured_data` (JSON only).
2. **Entity/relationship extraction hints** (who/what/when) — returned as *candidate* JSON, not graph writes.
3. **Summarization** of long transcripts into `structured_data` summary fields.

The Discovery LLM is **prohibited** from: reasoning about business meaning, scoring, ranking, recommending, or writing anything to the graph/DB. It returns JSON only.

**Prompt contract schema interface:**

```python
# Tool: extract_evidence  (LLM fills the `result` contract; runtime validates)
def discovery_extract(raw_text: str, source: str, source_type: str) -> EvidenceExtraction:
    """LLM fills this JSON result. Validated by a strict schema BEFORE any write."""
    # result schema (contract layer):
    #   structured_data: dict[str, Any]
    #   entity_mentions: list[{"name": str, "entity_type": str, "role": str}]
    #   summary: str
    #   confidence: float  # 0.0-1.0, LLM self-attested; runtime may down-weight
    ...

def discovery_persist(records: list[EvidenceRecord]) -> list[str]:
    """RUNTIME-ONLY. No LLM. Validates + dedupes + writes EvidenceRecords."""
```

**System prompt architecture:**

```
You are the Discovery Agent of an Enterprise Decision Runtime.
Your ONLY job is extraction. You do not reason, score, rank, or recommend.
ALL output must be valid JSON matching the provided schema — nothing else.
Rules:
- If the input is not parseable, return {"structured_data": {}, "summary": "", "confidence": 0.0}
- Never invent facts not present in the input.
- Never output markdown, prose outside JSON, or code blocks beyond the JSON payload.
- Never write to any database, graph, or external system. You return JSON only.
```

**Why no reasoning:** an evidence record must be trustworthy. If the parser reasons, its confidence is no longer evidence — it is opinion. `confidence` here is *extraction fidelity*, not *business truth*.

---

### 3.2 Knowledge Agent — owns **Understand**

**Role:** Builds and maintains the **Enterprise Knowledge Model** from validated evidence: ontology objects, typed links, entity resolution, capability/process/system mapping, and conflict detection. It is the memory of the runtime.

**Ownership:** The ontology and graph (`CanonicalEntity`, `KnowledgeCatalogEntry`, `Capability`, `CapabilityRelationship`, link tables in `011_knowledge_catalog.sql`). Entity resolution tiers, conflict lifecycle, and knowledge freshness.

**Inputs:** Validated `EvidenceRecord`s (from Discovery), existing graph state, `KnowledgeCatalogEntry` registry, `Capability` model.

**Outputs:** Ontology objects/links, resolved `CanonicalEntity`s, detected `Conflict`s, capability/process mappings, `KnowledgeCatalogEntry` updates.

**Deterministic operations (pure code, no LLM):**
1. **Entity resolution** across the five `ResolutionTier`s (`src/schemas/semantic_layer.py`): `EXACT` (external_id) → `FUZZY` (name+type, Levenshtein) → `ATTRIBUTE` (email/phone/domain) → `RELATIONSHIP` (shared parent/contacts) → `LLM_ASSISTED` (last resort, low confidence).
2. **Dedup/merge** of `EntityAlias` records under a canonical ID with confidence weighting.
3. **Conflict detection** — `AttributeConflict` creation when sources disagree on a single attribute (status `open`); `Conflict` records across evidence.
4. **Link materialization** — typed `CapabilityRelationship` (ENABLES/DEPENDS_ON/CONFLICTS_WITH/INVESTED_IN), `CatalogRelationship` link tables, capability↔system↔process mapping.
5. **Ontology validation** — object/link writes pass the `@governed_write` governance gate and the ontology adapter (`mission_state_to_ontology`). The LLM never defines the ontology schema; schema lives in code.

**LLM operations (permitted):**
1. **Resolution hint** for `LLM_ASSISTED` tier only: given candidate aliases, return a JSON verdict `{"resolve": bool, "canonical_id": str, "confidence": float}`.
2. **Extraction hints** for capability/process/system mapping from evidence (candidate labels only).
3. **Summarization** of knowledge slices for downstream context.

The Knowledge LLM is **prohibited** from: writing graph objects directly, defining schema/ontology types, or resolving conflicts on its own authority — conflicts with `status=open` must surface to humans.

**Prompt contract schema interface:**

```python
# Tool: resolve_entities  (LLM fills the `result` contract — Tier-5 only)
def knowledge_resolve(candidates: list[EntityAlias]) -> list[ResolutionVerdict]:
    """LLM fills this JSON result for LLM_ASSISTED tier. Runtime executes the merge."""
    # result schema:
    #   verdicts: [{"alias_id": str, "resolve": bool, "canonical_id": str,
    #               "confidence": float}]
    ...

# Tool: label_knowledge  (LLM fills this JSON result; runtime validates + persists)
def knowledge_label(evidence: list[EvidenceRef]) -> list[KnowledgeLabel]:
    """LLM fills candidate labels. NEVER the ontology schema — only values."""
    # result schema:
    #   labels: [{"entity_type": str, "capability": str, "process": str,
    #             "system": str, "confidence": float}]
    ...

def knowledge_materialize(objects: list[dict], links: list[dict]) -> int:
    """RUNTIME-ONLY. No LLM. @governed_write gate + adapter + graph write."""
```

**System prompt architecture:**

```
You are the Knowledge Agent of an Enterprise Decision Runtime.
You build understanding, not decisions. You NEVER define the ontology schema.
ALL output must be valid JSON matching the provided schema — nothing else.
Rules:
- Entity resolution is deterministic; you are consulted ONLY for the LLM_ASSISTED tier.
- Return candidate labels; the runtime validates them against the canonical schema.
- Never create, modify, or delete graph objects, database rows, or catalog entries.
- If evidence is ambiguous, set confidence < 0.5 and do NOT guess a canonical match.
- Never resolve an open conflict. Flag it; a human resolves.
```

---

### 3.3 Decision Agent — owns **Reasoning** (LLM leads, human governs)

**Role:** The **only** agent that reasons. It consumes the assembled `DecisionContext` (never the whole graph) and produces a `DecisionAnalysis`: root cause, options, trade-offs, recommendation, confidence, readiness. **LLM leads; human governs.**

**Ownership:** The `Decision` object lifecycle (draft → assessing → approved → superseded) and its analysis artifacts. Recommendation authority, not approval authority.

**Inputs:** `DecisionContext` (from the Decision Context Runtime — see §4), feasibility scores (deterministic), prior decision history.

**Outputs:** `DecisionAnalysis` (validated by `src/decision/contracts.py`), plus the canonical `Decision`/`Option`/`TradeOff` entities.

**Deterministic operations (pure code, no LLM) — the scaffolding around the reasoning:**
1. **Decision Context Runtime** assembly (§4) — evidence slice, entity refs, KPI refs, active policies, risks, open decisions, stakeholders, capability graph.
2. **Option candidate framing** — `OptionGenerator` provides the two baseline options (preferred vs. status-quo) from evidence signals.
3. **Feasibility scoring** — `FeasibilityEngine` scores each option on 8 weighted dimensions with blocking rules (`src/decision/feasibility_engine.py`, `src/pipeline/feasibility_engine.py`).
4. **Readiness tiering** — `publish | caveat | review | block` from weighted total + blockers.
5. **Trade-off computation** — `TradeOffAnalyzer` computes cost/time/quality/risk deltas (numeric) between options.
6. **Validation** of the LLM's `DecisionAnalysis` payload against the strict contract; policy gate check; HITL signal routing for approval.

**LLM operations (permitted) — the reasoning:**
1. **Root cause** analysis (narrative, grounded in provided evidence refs).
2. **Option articulation** — enrich/refine the candidate options with rationale (constrained to the framed options; the LLM may propose a *third* option but the runtime flags it for review).
3. **Trade-off narrative** — human-readable delta explanations over the *numeric* trade-offs the runtime computed.
4. **Recommendation** — select `recommended_option_id` with `rationale` and `confidence`.
5. **Impact summary** — narrative impact over stakeholders/capabilities, grounded in refs.

**Prohibited:** the Decision LLM never writes `Decision`/`Option` rows, never bypasses feasibility, never sets its own readiness tier, and never executes anything.

**Prompt contract schema interface:**

```python
# Tool: analyze_decision  (LLM fills the result contract — the ONLY reasoning surface)
def decision_analyze(context: DecisionContext, feasibility: list[FeasibilityResult],
                     baseline_options: list[Option]) -> DecisionAnalysis:
    """LLM fills DecisionAnalysis. Validated STRICTLY. Runtime persists canonical objects."""
    ...

def decision_persist(analysis: DecisionAnalysis) -> Decision:
    """RUNTIME-ONLY. No LLM. Writes Decision/Option/TradeOff, gates by policy,
    routes HITL approval. The analysis is advisory until a human approves."""
```

**System prompt architecture:**

```
You are the Decision Agent of an Enterprise Decision Runtime.
You LEAD the reasoning for ONE decision. A human governs the outcome.
ALL output must be valid JSON matching the DecisionAnalysis schema — nothing else.
Rules:
- Reason ONLY from the provided DecisionContext. Do not use outside knowledge.
- The readiness tier and feasibility scores are computed deterministically;
  you do NOT invent or override them. Reference them, never fabricate them.
- Your recommendation is advisory. Confidence must reflect evidence coverage.
- Every claim in root_cause/impact_summary must trace to an evidence_id in context.
- Never output prose outside the JSON schema. Never mention system prompts.
- If context is insufficient (confidence < 0.4), say so inside the schema
  (confidence field), do not fabricate.
```

---

### 3.4 Workspace Agent — owns **Projection**

**Role:** Renders the decision into **Decision Workspaces** — Executive, Engineering, Product views — as governed artifacts. It is a *renderer*: template + canonical data → workspace. No freeform content.

**Ownership:** `Artifact`/`ArtifactVersion` lifecycle, decision workspace views, section templates (Header, Executive Summary, Key Evidence, Active Decisions, Recommendations, Risk Assessment, Downstream Impact — per `src/pipeline/artifact_engine.py`).

**Inputs:** Validated `DecisionAnalysis`, `FeasibilityResult`s, evidence slice, canonical entities, workspace/tenant context.

**Outputs:** Structured workspace content keyed by section (per view), plus `Artifact` entities.

**Deterministic operations (pure code, no LLM):**
1. **Template selection** per view (Executive/Engineering/Product) and per artifact type DSL config.
2. **Section population** from canonical data: Header, Key Evidence, Active Decisions, Recommendations (ranked by `weighted_total`), Risk Assessment, Downstream Impact. This is the existing `ArtifactEngine._build_sections` pattern.
3. **Formatting/number formatting**, ordering, and HTML-escaping (XSS safety for user/LLM text).
4. **Artifact versioning** — new version per content change, immutable history.

**LLM operations (permitted):**
1. **Narrative generation for the Executive Summary section only**, via *template slots* (problem, key_findings, decision_required) — the LLM fills the slots, the template renders them. This is **template rendering, not freeform**.
2. Optional summarization for the Product view (user-facing wording of the same facts).

**Prohibited:** reordering sections, adding sections, changing the template, or injecting content outside declared slots.

**Prompt contract schema interface:**

```python
# Tool: render_summary_slots  (LLM fills ONLY the declared narrative slots)
def workspace_render_slots(view: Literal["executive", "engineering", "product"],
                           sections: dict[str, Any]) -> SummarySlots:
    """LLM fills: {problem, key_findings: list[str], decision_required}.
    The template then renders the full section deterministically."""
    ...

def workspace_project(artifact_type: str, workspace_id: str,
                      context: dict[str, Any]) -> ArtifactResult:
    """RUNTIME-ONLY. No LLM. Fills every OTHER section from canonical data,
    merges the LLM slots, validates, and versions the artifact."""
```

**System prompt architecture:**

```
You are the Workspace Agent of an Enterprise Decision Runtime.
You write narrative SLOTS inside a fixed template. You do not design documents.
ALL output must be valid JSON matching the slot schema — nothing else.
Rules:
- Fill ONLY the declared slots for the requested view.
- Ground every finding in the provided sections/evidence. Never invent data.
- Keep language neutral, factual, and non-promotional.
- Never change structure: no new sections, no reordering, no styling instructions.
```

---

### 3.5 Execution Agent — owns **Actions**

**Role:** The runtime's *hands*. Executes **approved** external actions (Jira, Slack, Notion, etc.) against real systems. **Never reasons** — it is a strictly gated side-effect executor.

**Ownership:** External action execution, idempotency keys, and execution audit logs.

**Inputs:** An **approved** action payload (from the risk-tiered policy engine + human approval), the execution plan from the Decision Workspace.

**Outputs:** Execution receipts (`action_id`, external system ref, status), audit events.

**Deterministic operations (pure code, NO LLM — 100%):**
1. **Policy gate** — the risk-tiered policy engine checks the action against `BusinessRule` severity (`block | warn | info`) and `CatalogPolicy` enforcement. `block` → never executes.
2. **HITL gate** — executes **only** actions with explicit human approval (Temporal `SignalWorkflow("hitl-approval")` unblocks `AwaitWithTimeout`).
3. **External API calls** — Jira/Slack/Notion SDK calls with the exact payload from the approved plan.
4. **Idempotency** — unique action keys so retries never double-execute.
5. **Audit logging** — immutable `AuditEvent` per execution (actor, action, timestamp).

**LLM operations:** **None.** The Execution Agent contains no LLM at all. Its tool IDs in the authority manifest are the external-action SDKs, and it is the `external_facing=True`, `escalation_tier="blocked"` agent.

**Prompt contract schema interface:** (no LLM tool — the interface is a runtime RPC)

```python
def execution_execute(plan: ExecutionPlan, approval_token: str) -> ExecutionReceipt:
    """RUNTIME-ONLY. No LLM. Gated by: policy engine -> HITL approval ->
    idempotency check -> external API call -> audit write. Rejects otherwise."""
    ...
```

**Why no LLM:** an LLM that "reasons" inside the execution path is a prompt-injection and drift surface. Execution is pure, deterministic, and auditable.

---

### 3.6 Evaluation Agent — owns **Learning**

**Role:** Measures what actually happened after a decision: outcome KPIs, feedback, decision drift, and closure of the learning loop. It turns runtime telemetry into measured knowledge.

**Ownership:** Outcome measurement, KPI tracking (`KPI` baseline vs. target vs. actual), feedback capture, decision-drift detection, and feeding learnings back into the Knowledge Model.

**Inputs:** Decision + selected option + feasibility snapshot, post-decision evidence (system telemetry, KPI updates, stakeholder feedback), Evaluation-period config.

**Outputs:** `EvaluationReport` (outcome vs. forecast, KPI deltas, drift flags), updated `KPI`/`CatalogDecision.outcome`, learning notes for the Knowledge Agent.

**Deterministic operations (pure code, no LLM):**
1. **KPI delta computation** — `current_value` vs `baseline_value` vs `target_value` per `KPI` (numeric, exact).
2. **Forecast-vs-actual comparison** — feasibility `weighted_total`/confidence vs. realized outcome.
3. **Decision drift detection** — rule-based: realized outcome worse than feasibility tier by a threshold → `drift` flag with the measured gap.
4. **Feedback aggregation** — counts/sentiment distribution from structured feedback (not freeform interpretation).

**LLM operations (permitted):**
1. **Summarization** of the measured facts into a short narrative report (past-tense, factual).

**Prohibited:** changing metrics, inventing outcomes, re-scoring decisions after the fact.

**Prompt contract schema interface:**

```python
# Tool: summarize_outcomes  (LLM fills the narrative ONLY; numbers come from the runtime)
def evaluation_summarize(measured: EvaluationMeasures) -> OutcomeNarrative:
    """LLM fills: {headline, summary, key_learnings: list[str]}.
    All numbers in the report come from `measured`, never from the LLM."""
    ...

def evaluation_measure(decision_id: str, period_days: int) -> EvaluationMeasures:
    """RUNTIME-ONLY. No LLM. Computes KPI deltas, forecast-vs-actual, drift."""
```

**System prompt architecture:**

```
You are the Evaluation Agent of an Enterprise Decision Runtime.
You summarize MEASURED facts. You do not judge, justify, or alter metrics.
ALL output must be valid JSON matching the narrative schema — nothing else.
Rules:
- Every number in your narrative must be copied from the provided measures.
- Never add metrics that are not present in the measures.
- If the decision drifted from forecast, state it plainly and factually.
- Never recommend new actions. The Decision Agent reasons; you learn.
```

---

## 4. The Decision Context Runtime

**Key new component** that sits between the Knowledge Model and the Decision Agent.

### 4.1 Why it exists

The graph is large; the LLM has a budget. If the Decision Agent received the whole graph it would (a) blow the context budget, (b) be distracted by irrelevant nodes, and (c) be more likely to hallucinate from noise. The Decision Context Runtime guarantees **minimal high-signal context per decision**.

### 4.2 What it assembles (deterministically — pure code, no LLM)

Per decision question, it assembles one `DecisionContext` (schema in `src/decision/contracts.py`):

| Slice | Source | Cap / Budget |
|-------|--------|--------------|
| `evidence` | Top-20 `EvidenceRecord`s by confidence/relevance for the workspace | 20 records |
| `related_entities` | `CanonicalEntity` refs within 3 hops of workspace entities | bounded |
| `kpis` | `KPI` refs whose owner/domain matches the decision | bounded |
| `active_policies` | `BusinessRule`/`CatalogPolicy` with `enforcement=mandatory` or `severity=block` | all applicable |
| `risks` | Open `Risk`/`CatalogRisk` linked to the decision/capabilities | bounded |
| `open_decisions` | Active + recent `Decision` refs (avoid duplication) | bounded |
| `stakeholders` | `Stakeholder` refs with decision roles | bounded |
| `capability_graph` | `CapabilityRef` nodes the decision touches (NOT the full subgraph) | bounded |

**Budget:** `token_budget_max = 32 000` (matches `AgentContext` in `src/context/agent_context.py`). If assembly exceeds the budget, truncate in priority order: `evidence` → `related_entities`/`capability_graph` → `open_decisions`, cutting from the bottom. `token_budget_used` is tracked on the context.

### 4.3 Interface

```python
def context_engine_assemble(decision_id: str, workspace_id: str,
                            tenant_id: str, question: str) -> DecisionContext:
    """RUNTIME-ONLY. No LLM. Reads the Knowledge Model, assembles the
    minimal high-signal DecisionContext, enforces the token budget.
    This is the ONLY input the Decision Agent's LLM receives."""
```

Every slice is a **reference** (id + summary) — never the full object — so sensitive payloads (raw content, embeddings) never reach the LLM.

---

## 5. Deterministic vs. LLM-augmented summary

| Agent | Step | Deterministic | LLM-augmented |
|-------|------|---------------|---------------|
| **Discovery** | Parse/OCR/checksum/dedupe/validate/persist | ✅ 100% | — |
| **Discovery** | structured_data extraction, entity mentions, summary | — | ✅ (JSON extraction only) |
| **Knowledge** | Resolution tiers 1–4, dedup, conflict detect, link materialize, ontology validate | ✅ 100% | — |
| **Knowledge** | Tier-5 resolution verdict, mapping labels | — | ✅ (candidate JSON only) |
| **Decision** | Context assembly, option framing, feasibility, trade-off numerics, tiering, persistence, HITL | ✅ | — |
| **Decision** | Root cause, option rationale, recommendation, impact narrative | — | ✅ **LLM leads** |
| **Workspace** | Template select, section fill (non-narrative), versioning | ✅ 100% | — |
| **Workspace** | Executive-summary slots | — | ✅ (template rendering, not freeform) |
| **Execution** | Policy gate, HITL gate, API call, idempotency, audit | ✅ 100% | ❌ **none** |
| **Evaluation** | KPI deltas, forecast-vs-actual, drift flags, feedback aggregation | ✅ 100% | — |
| **Evaluation** | Outcome narrative | — | ✅ (summarize measured facts) |
| **ChiefOfStaff** | Route map, dispatch, envelope validation | ✅ 100% | — |
| **ChiefOfStaff** | Intent classification (bounded labels) | — | ✅ (minimal) |

**Freeze:** *Decision Agent = LLM leads; artifacts = template rendering, not freeform; Execution = zero LLM.*

---

## 6. Alignment with existing code

The V6 roster is a **renaming + completion** of the V5.2 authority manifest (`src/agents/authority_manifest.py`). Agents are implementation details inside runtimes; the 9-runtime model is the primary architectural framing.

| V6 runtime agent | Owning Runtime | V5.2 manifest agent | Notes |
|----------|--------------------|-------|
| ChiefOfStaff | `ChiefOfStaff` (`control_plane`) | Same; orchestration + intent |
| Discovery | `Discovery` (`discovery`) | Same |
| Knowledge | `OntologyMapper` + `KnowledgeValidator` | Merged: materialization + resolution + conflict detection |
| Decision | `SolutionArchitect` (`workflow_building`) | Re-scoped: reasoning output is a `DecisionAnalysis`, not an executable workflow |
| Workspace | *(new)* | Projection/rendering |
| Execution | `Governance` (`governance`) | `external_facing=True`, `escalation_tier="blocked"` |
| Evaluation | *(new)* | Learning loop |

All agents inherit `BaseAgent` (`src/agents/base.py`) for `send()`/`receive()` and persist results through `AgentResult` (the strict contract version lives in `src/decision/contracts.py`).

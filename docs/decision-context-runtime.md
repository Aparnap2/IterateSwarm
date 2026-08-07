# OntologyAI V6.1 — Decision Context Runtime (Contract)

**Status:** FROZEN (implementable contract)
**Version:** 1.0
**Date:** 2026-08-05
**Author:** Solution Architecture
**Depends on:** `docs/v6-runtime-architecture.md` (frozen), `V6_DOMAIN_SPEC.md` §1–§3 (entity/edge taxonomy), §10 (context model), §11 (API contracts)
**Constitution:** This is the precise, implementable contract for the Decision Context Runtime. It does not modify production code.

---

## 1. Purpose

The Decision Context Runtime sits **between the Enterprise Knowledge Model (EKM) and the Decision agent**. Its job is to assemble the **minimal high-signal context** for a single decision — not the entire knowledge graph — and hand it to the Decision agent as a deterministic, validated, budget-bounded `DecisionContext`.

It is the foundation for:

- **Long-context handling** — the runtime never ships the whole graph to the LLM.
- **Token efficiency** — a fixed per-section budget with priority truncation.
- **Explainability** — every field carries provenance (evidence / score / policy / graph).
- **Deterministic reasoning** — policies, KPIs, priorities, and risk tier are computed deterministically and injected as ground truth the model may reason *about* but never *author*.

The runtime is **read-only** with respect to the EKM. It never mutates the graph, evidence, or policy stores. It is invoked by the Decision Runtime (R3) on the `ONTOLOGYAI-AGENT-QUEUE`.

---

## 2. Input Contract

The runtime accepts a single typed input:

```python
@dataclass
class DecisionContextRequest:
    decision_id: str | None        # ULID; None for an unresolved work item / intake
    workspace_id: str              # ULID (required)
    tenant_id: str                 # ULID (required)
    intake: DecisionIntake         # the question being decided
    requesting_stakeholder_id: str | None = None
    mode: Literal["new_decision", "re_open", "decision_monitoring_regeneration"] = "new_decision"
    budget_tokens: int = 32_000    # default; overridable per decision
```

```python
@dataclass
class DecisionIntake:
    title: str                     # max 200 chars
    description: str               # max 5000 chars
    decision_type: Literal["strategic", "tactical", "operational", "technical"]
    urgency: Literal["low", "medium", "high", "critical"] = "medium"
    tags: list[str] = field(default_factory=list)
```

Validation: `DecisionContextRequest` is validated with `extra="forbid", strict=True` (Pydantic convention across the codebase). A request with neither `decision_id` nor a resolvable intake is rejected.

---

## 3. Output Contract — `DecisionContext` Schema

The runtime returns a single `DecisionContext`. Every field is typed; `extra="forbid", strict=True`.

```yaml
DecisionContext:
  context_id: string (ULID)
  schema_version: "1.0"
  tenant_id: string (ULID)
  workspace_id: string (ULID)
  decision_id: string (ULID) | null
  assembled_at: datetime (UTC)
  mode: enum(new_decision, re_open, decision_monitoring_regeneration)

  # ── 1. The question being decided ─────────────────────────────────────
  decision_intake:
    title: string
    description: string
    decision_type: enum(strategic, tactical, operational, technical)
    urgency: enum(low, medium, high, critical)
    requested_by: StakeholderRef | null

  # ── 2. Relevant evidence (max N, sorted by combined relevance) ────────
  relevant_evidence:                       # max 20 records
    - evidence_id: string (ULID)
      source: string
      source_type: enum(connector, chat, upload, transcript, spreadsheet, email, screenshot, api)
      timestamp: datetime
      confidence: float [0,1]
      reliability: float [0,1]             # from Source.reliability
      structured_data: dict
      freshness_state: enum(fresh, stale, expired)
      relevance_score: float [0,1]         # combined semantic + graph + recency
      role: enum(supporting, contradicting, contextual, prerequisite)

  # ── 3. Related entities (graph, max depth 2) ──────────────────────────
  related_entities:                        # max 30
    - entity_id: string (ULID)
      entity_type: string                  # canonical entity type name
      name: string
      confidence: float [0,1]
      state: string                        # entity lifecycle state
      relationship_to_decision: string     # e.g. DEPENDS_ON, AFFECTS, LINKS_TO, MAPS_TO_CAPABILITY
      evidence_backing_count: int
      freshness_state: enum(fresh, stale, expired)

  # ── 4. KPIs affected (MEASURES edge / capability association) ─────────
  kpis:                                    # max 10
    - kpi_id: string (ULID)
      name: string
      baseline_value: float
      target_value: float
      current_value: float | null
      unit: string
      owner_id: string (ULID) | null
      status: enum(baseline_set, tracking, met, missed)
      impact_projection: string | null     # deterministic, from evidence delta

  # ── 5. Active policies (deterministic, NEVER LLM-authored) ────────────
  active_policies:                         # max 10
    - policy_id: string (ULID)
      policy_code: string                  # e.g. BR-042
      description: string
      severity: enum(block, warn, info)
      rule_expression: string              # human-readable, from BusinessRule
      applicability: enum(always, conditional)
      effective_at: datetime

  # ── 6. Risks touching the decision (AFFECTS edge + workspace register) ─
  risks:                                   # max 10
    - risk_id: string (ULID)
      description: string
      risk_type: enum(technical, financial, operational, compliance, market, strategic)
      severity: float [0,100]
      probability: float [0,1]
      status: enum(identified, analyzed, mitigated, accepted, realized)
      mitigation: string | null
      owner_id: string (ULID) | null

  # ── 7. Open decisions (related / precedent) ───────────────────────────
  open_decisions:                          # max 10
    - decision_id: string (ULID)
      title: string
      status: enum(draft, assessing, approved, superseded)
      owner_id: string (ULID) | null
      decision_type: string
      relationship: enum(related, precedent, superseded_by, dependent_on)

  # ── 8. Stakeholders (owners, mentions, decision roles) ────────────────
  stakeholders:                            # max 15
    - stakeholder_id: string (ULID)
      name: string
      role: string
      department: string | null
      influence_score: float [0,1]
      sentiment_score: float [0,1]
      relationship_to_decision: enum(decision_maker, reviewer, participant, informed, owner, mentioned)

  # ── 9. Capability graph (L0/L1/L2 + CapabilityRelationship) ───────────
  capability_graph:                        # max 20 capabilities
    - capability_id: string (ULID)
      name: string
      level: enum(L0, L1, L2)
      domain: string | null
      maturity_level: int [1,5]
      health_score: float [0,1]
      owner_id: string (ULID) | null
      relationships:                       # CapabilityRelationship
        - source_id: string (ULID)
          target_id: string (ULID)
          relationship_type: enum(ENABLES, DEPENDS_ON, CONFLICTS_WITH, INVESTED_IN)
          confidence: float [0,1]
          strength: float [0,1]
      impact_projection: string | null     # deterministic mapping of decision → capability

  # ── 10. Priorities (deterministic signal fusion) ──────────────────────
  priorities:
    urgency: enum(low, medium, high, critical)
    severity: enum(low, medium, high, critical)
    blast_radius: enum(low, medium, high)
    readiness_tier: enum(publish, caveats, review, block) | null
    risk_tier: enum(low, medium, high)     # feeds the Autonomy Model
    recommended_action: enum(proceed, review, block, escalate)

  # ── 11. Freshness / signals (Continuous Decision Monitoring) ──────────
  freshness:
    evidence_age_max_days: float
    stale_evidence_count: int
    conflicting_evidence_count: int
    missing_context: list[str]             # deterministic gap report
    drift_signals: list[str]
    decision_monitoring:
      previous_decision_valid: bool
      staleness_reason: string | null
      changed_entities: list[string (ULID)]
      changed_evidence: list[string (ULID)]
      regenerated: bool

  # ── 12. Budget accounting ─────────────────────────────────────────────
  budget:
    total_tokens: int
    reserved_tokens: int
    sections: dict[str, int]               # section → tokens actually used
```

### 3.1 Deterministic vs LLM-sourced fields

| Field group | Source | Authored by LLM? |
|---|---|---|
| `active_policies`, `kpis`, `priorities`, `freshness`, `budget` | Deterministic engines (rules, math, store queries) | **Never** |
| `relevant_evidence`, `related_entities`, `risks`, `open_decisions`, `stakeholders`, `capability_graph` | Store queries + deterministic fusion | **Never** (retrieved, not generated) |
| `decision_intake` | Caller-provided | No |
| `impact_projection` (kpis/capabilities) | Deterministic projection from evidence delta | No (may be *narrated* later by the Decision agent, but the engine value is deterministic) |

The Decision agent may reason over any field, but it **cannot** alter `active_policies`, `priorities.risk_tier`, or `freshness` — those are ground truth injected by the runtime.

---

## 4. Assembly Algorithm (frozen)

The runtime assembles context in **nine ordered steps**. Steps 1–3 are read-only store queries; step 4 fuses; steps 5–8 order, budget, and validate; step 9 hands off.

```
Input: DecisionContextRequest
  │
  ├─ 1. Scope resolution ──────────────── Postgres (Workspace, Decision)
  ├─ 2. Seed expansion ────────────────── Neo4j (CONTAINS, EVALUATES, entity_refs)
  ├─ 3. Parallel retrieval ────────────── Neo4j graph + Qdrant vector + Postgres relational
  ├─ 4. Fusion & scoring ──────────────── deterministic relevance + role classification
  ├─ 5. Deterministic enrichment ──────── policies, KPIs, priorities, risk tier, freshness
  ├─ 6. Ordering ──────────────────────── sort each section by relevance/severity
  ├─ 7. Budget enforcement ────────────── truncate lowest-signal sections
  ├─ 8. Validate ──────────────────────── Pydantic DecisionContext (extra="forbid", strict)
  └─ 9. Handoff ───────────────────────── serialize → Decision agent (deterministic feed)
```

### Step 1 — Scope resolution (Postgres)

- Load `Workspace` by `workspace_id`; fail if not `active`.
- If `decision_id` given, load `Decision`; else treat intake as a new decision.
- Resolve `requesting_stakeholder_id` → `Stakeholder` (for `decision_intake.requested_by` and stakeholder slice).

### Step 2 — Seed expansion (Neo4j)

Collect the seed entity set that anchors retrieval:

- Entities linked to the workspace via `CONTAINS`.
- Entities linked to the decision via `EVALUATES` (options) and `AFFECTS` (risks).
- Entities referenced by the decision's linked evidence (`EvidenceRecord.entity_refs`).
- Capabilities mapped via `MAPS_TO_CAPABILITY` from the seed evidence.

### Step 3 — Parallel retrieval

Three independent queries run concurrently (async, circuit-broken):

**(a) Neo4j graph traversal** — from seed entities, traverse typed edges to depth 2:

```cypher
MATCH (seed) WHERE seed.id IN $seed_ids
MATCH (seed)-[r]-(n)
WHERE type(r) IN ['LINKS_TO','MAPS_TO_CAPABILITY','DEPENDS_ON','CAPABILITY_DEPENDS',
                  'ENABLED_BY','MEASURES','SATISFIES','GOVERNS','AFFECTS','OWNED_BY',
                  'MENTIONS','CONFLICTS_WITH','SUPPORTS','REFUTES']
RETURN n.id AS entity_id, labels(n)[0] AS entity_type, n.name AS name,
       n.confidence AS confidence, n.state AS state, type(r) AS rel,
       r.confidence AS rel_confidence
LIMIT $max_nodes
```

**(b) Qdrant vector retrieval** — encode `intake.title + intake.description` with the evidence embedding model (768-dim), top-K by cosine similarity against the `v6_evidence_embeddings` collection, scoped to `tenant_id`:

```
top_k = 20
filter = { "must": [ { "key": "tenant_id", "match": { "value": tenant_id } } ] }
```

**(c) Postgres relational retrieval** — KPIs (`MEASURES` join), active `BusinessRule`/`Constraint`/`CatalogPolicy`, `Risk` register, open `Decision`s, `Stakeholder` + `EntityAlias`, `KnowledgeCatalogEntry` for seed entities.

### Step 4 — Fusion & scoring (deterministic)

Combine graph hits and vector hits into `relevant_evidence`:

```
combined_relevance(e) =
    w_sem * semantic_sim(e)          # Qdrant cosine, 0 if not a vector hit
  + w_graph * graph_affinity(e)       # 1 if e links to a seed entity, else 0
  + w_rec  * recency(e)               # 1 / (days_since_timestamp + 1), normalized
```

Default weights: `w_sem = 0.5`, `w_graph = 0.3`, `w_rec = 0.2` (configurable, not hardcoded). Dedupe by `evidence_id` (graph hit wins over vector hit). Classify `role`:

- `contradicting` if the evidence has an active `CONFLICTS_WITH` edge to a supporting record;
- `supporting` if it has a `SUPPORTS`/`LINKS_TO` edge to a seed entity;
- `prerequisite` if it is a `Requirement`-backing record for a seed entity;
- else `contextual`.

### Step 5 — Deterministic enrichment

- **KPIs**: pull `KPI` rows for seed entities via `MEASURES`; compute `impact_projection` from the delta between `current_value` and `target_value` (deterministic).
- **Policies**: pull active `BusinessRule`/`Constraint`/`CatalogPolicy` scoped to workspace + tenant. **Never LLM-authored.**
- **Priorities**: compute `severity`, `blast_radius` (Neo4j dependency fan-out), `readiness_tier` (from existing `FeasibilityScore` if present), and `risk_tier` (see `docs/autonomy-model.md` §2). `recommended_action` derives from the policy gate, not the LLM.
- **Freshness**: apply the `V6_DOMAIN_SPEC.md` §3.5 freshness policy per `source_type`; count stale/conflicting evidence; run the deterministic gap report (missing entity types per workspace vs present).
- **Decision monitoring**: if `mode == decision_monitoring_regeneration`, diff the previous decision's evidence/entity set against current state to populate `changed_entities`/`changed_evidence` and `staleness_reason`.

### Step 6 — Ordering

Sort each section by descending relevance/severity: evidence by `combined_relevance`, risks by `severity × probability`, stakeholders by `influence_score`, capabilities by `health_score`.

### Step 7 — Budget enforcement

Fixed per-section budget (defaults, configurable):

| Section | Budget (tokens) | Truncation priority |
|---|---|---|
| System prompt + instructions | 2,000 | never truncated |
| `decision_intake` | 1,000 | never truncated |
| `relevant_evidence` | 12,000 | 1 (truncate first) |
| `related_entities` | 4,000 | 2 |
| `capability_graph` | 4,000 | 3 |
| `active_policies` | 2,000 | 4 |
| `risks` | 2,000 | 5 |
| `open_decisions` | 2,000 | 6 |
| `stakeholders` | 1,000 | 7 |
| `kpis` | 1,000 | 8 |
| `priorities` + `freshness` | 1,000 | never truncated (deterministic ground truth) |
| **Total** | **32,000** | — |

Truncation is from the **bottom** of each section (lowest relevance/severity) in priority order. `active_policies`, `priorities`, and `freshness` are **never** truncated — they are deterministic ground truth and must always reach the model. Token accounting uses a real tokenizer (`tiktoken`), not the `char/4` heuristic in `agent_context.py`.

### Step 8 — Validate

Construct and validate `DecisionContext` against the Pydantic schema (`extra="forbid", strict=True`). Any unknown field or type coercion fails the assembly and is logged (observability).

### Step 9 — Deterministic handoff to the Decision agent

The runtime returns the validated `DecisionContext` as the **sole** decision input. The Decision agent receives:

- the `DecisionContext` (serialized, budget-bounded);
- a fixed system prompt that instructs it to reason **only** over the provided context, to treat `active_policies`, `priorities.risk_tier`, and `freshness` as ground truth, and to return a typed `DecisionAnalysis` (options, trade-offs, risks, recommendation, confidence, readiness, brief).

The agent has **no** direct store access in this path — it cannot query the graph or policy store itself. This guarantees the context is minimal, budgeted, and explainable.

---

## 5. Determinism Guarantees

1. Same `DecisionContextRequest` + same store state → byte-identical `DecisionContext` (modulo timestamps). Assembly is deterministic; no LLM call in the runtime.
2. `active_policies`, `priorities`, `freshness` are computed by code, never by a model.
3. The engine is read-only; it emits no governed writes.
4. Every field carries provenance: evidence → `EvidenceRecord`; policy → `BusinessRule`; KPI → `KPI`; risk → `Risk`; capability → `Capability`.

---

## 6. Relationship to the Existing `AgentContext` (V6 §10)

The existing `AgentContext` (8 layers, 32K budget, workspace-centric) in `apps/ai/src/context/agent_context.py` is **retained** for the pipeline's LLM-augmented stages (Parse, Entity/Relationship Build, Artifact Projection). The Decision Context Runtime is a **decision-centric** context layered on top, used only by the Decision Runtime. The two do not replace each other.

---

## 7. Observability & Failure Handling

- Emit `decision_context.runtime.assembled` event (Redpanda) with `context_id`, `decision_id`, per-section token counts, and retrieval latencies.
- Emit `decision_context.truncated` when budget enforcement drops items, with counts per section.
- Circuit breakers on Neo4j, Qdrant, and Postgres reads; on failure, degrade gracefully (drop the affected section, mark `missing_context`, never fail the whole decision).
- All runtime activity is traced with `trace_id` (V6 §13 event envelope).

---

## 8. Risks Flagged

| # | Risk | Mitigation |
|---|------|------------|
| R1 | Token budget too tight → decision loses signal | Configurable per-section budgets; observability of utilization; priority truncation keeps ground-truth sections intact |
| R2 | Vector retrieval returns off-topic evidence | `w_graph` affinity + tenant filter + role classification; evidence below `min_confidence` excluded |
| R3 | Graph traversal fan-out exceeds budget | Depth capped at 2; `max_nodes` limit; blast-radius computed separately, not inlined |
| R4 | Deterministic ground truth (policies/priorities) conflicts with model reasoning | Model is instructed these are authoritative; policy gate re-checks risk tier at execution time (defense in depth) |

---

*This contract is frozen. It feeds the Decision agent per `docs/v6-runtime-architecture.md` §5 and the autonomy model per `docs/autonomy-model.md`.*
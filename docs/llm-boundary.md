# OntologyAI V6 — The Deterministic / LLM Boundary

> **Status:** Design — OntologyAI V6 (Enterprise Decision Runtime)
> **Purpose:** Freeze exactly where the LLM is allowed, define the `LLM → JSON → Pydantic → Canonical` pipeline, specify the retry/schema-repair strategy, and audit the pre-existing LLM call sites that must be gated.
> **Companion docs:** [`docs/agents-and-prompt-contracts.md`](./agents-and-prompt-contracts.md) · [`apps/ai/src/decision/contracts.py`](../apps/ai/src/decision/contracts.py)

---

## 1. The frozen boundary

### 1.1 LLM may ONLY do

| Operation | Example | Owner agent |
|-----------|---------|-------------|
| **Parsing** | unstructured text → `structured_data` JSON | Discovery |
| **Extraction** | entity/relationship mentions, mapping labels | Discovery, Knowledge |
| **Summarization** | transcript → summary; measured facts → narrative | Discovery, Workspace, Evaluation |
| **Reasoning** | root cause, option rationale, recommendation | Decision (LLM leads) |
| **Recommendation** | `recommended_option_id` + rationale (advisory) | Decision |
| **Narrative generation** | template slots, outcome narrative | Workspace, Evaluation |
| **Intent classification** | bounded-label routing | ChiefOfStaff (minimal) |

### 1.2 LLM must NEVER do

| Prohibited | Why |
|-----------|-----|
| Modify databases / graph directly | LLM output is untrusted until validated; direct writes bypass governance |
| Define the ontology / schema | Schema is code (`src/schemas/*`); an LLM defining it is a drift + injection surface |
| Bypass governance / validation | The `@governed_write` gate and Pydantic contracts are non-negotiable |
| Execute side effects | Execution is 100% deterministic and HITL-gated (Execution Agent has zero LLM) |
| Set its own readiness tier / feasibility | These are computed deterministically; the LLM references, never fabricates |

### 1.3 The hard rule

```
LLM → JSON → Pydantic schema validation → Canonical Model
```

**Never:** `LLM → business logic`. An LLM's output is *data to be validated*, never *code to be run*.

---

## 2. The `LLM → JSON → Pydantic → Canonical` pipeline

Every LLM call site in the runtime must conform to this pipeline. The contract schemas live in `apps/ai/src/decision/contracts.py` (all `extra="forbid"`, `strict=True`).

```
┌──────────┐   prompt    ┌─────────┐   raw text   ┌──────────────┐
│  Runtime │ ──────────► │   LLM   │ ───────────► │  JSON parse  │
│  (caller)│             └─────────┘              └──────────────┘
└──────────┘                                          │
                                                      ▼
                                          ┌───────────────────────┐
                                          │  Pydantic validation  │  ← strict=True, extra="forbid"
                                          │  (contracts.py)       │
                                          └───────────────────────┘
                                                      │ pass
                                                      ▼
                                          ┌───────────────────────┐
                                          │  Canonical Model      │  ← entities/models.py
                                          │  + governance gate    │  ← @governed_write
                                          └───────────────────────┘
                                                      │
                                                      ▼
                                          ┌───────────────────────┐
                                          │  Persist / act        │  ← only after validation
                                          └───────────────────────┘
```

**Guarantees:**
1. **No raw LLM text** ever reaches a business-logic branch. It is always parsed to JSON, then validated.
2. **Strict typing** (`strict=True`) rejects implicit coercion — a hallucinated string where an int is expected fails loudly.
3. **No unknown keys** (`extra="forbid"`) — an LLM inventing fields is rejected.
4. **Governance is orthogonal** — even a schema-valid payload must still pass the `@governed_write` decorator and the risk-tiered policy engine before any write or side effect.

---

## 3. Retry / schema-repair strategy

When an LLM payload fails Pydantic validation, the runtime applies a **bounded, deterministic repair ladder**. It never silently coerces or drops fields.

### 3.1 Ladder (in order)

| Step | Action | Deterministic? |
|------|--------|----------------|
| 1 | **Re-prompt with the exact validation error** — feed the `ValidationError` (field, expected type, offending value) back to the LLM with the same schema. | LLM (bounded) |
| 2 | **Re-prompt with a trimmed schema** — if the model repeatedly fails on optional/narrative fields, drop those fields for this call and require only the mandatory core. | LLM (bounded) |
| 3 | **Deterministic field repair** — for *known-safe* coercions only (e.g. trimming whitespace, normalising an enum string to lowercase, rounding a float to the schema bound). Never for semantic fields. | ✅ pure code |
| 4 | **Fail closed** — after `MAX_RETRIES` (default **2** re-prompts) the call is marked `failed`/`rejected`, the raw payload is quarantined to the audit log, and the task is routed back to ChiefOfStaff or to a human. **Never** a best-effort partial write. | ✅ pure code |

### 3.2 Rules

- **`MAX_RETRIES = 2`** re-prompts, then fail-closed. No infinite loops, no unbounded token spend.
- **Repair is additive, never destructive.** A repaired payload is re-validated in full before it is accepted.
- **Every failure is audited** — the raw LLM output, the validation error, and the repair step are written to the audit log (`AuditEvent`) for traceability.
- **Confidence is not a repair target.** If the LLM returns `confidence` outside `[0,1]`, the runtime clamps to the bound and *down-weights* it — it never inflates it.

---

## 4. Audit of pre-existing LLM call sites that must be gated

The following call sites exist in the current codebase and must be brought under the `LLM → JSON → Pydantic → Canonical` pipeline. File paths are real and current.

### 4.1 `apps/ai/src/pipeline/artifact_engine.py` — Executive Summary (LLM-augmented)

- **File:** `apps/ai/src/pipeline/artifact_engine.py`
- **Location:** `ArtifactEngine._build_sections`, **Section 2 "Executive Summary"** (docstring lines 8–9 mark it LLM-augmented; the section is built at lines 156–180).
- **Current state:** The section is populated deterministically for M0.5 (no LLM call yet), but the design intent is LLM-augmented narrative.
- **Gate required:** When the LLM is enabled, the narrative must be produced via the **Workspace Agent's** `workspace_render_slots` contract (template slots: `problem`, `key_findings`, `decision_required`), validated by the strict slot schema, then merged into the section by the deterministic template. The LLM must **not** be allowed to emit the whole section or reorder it.
- **Boundary:** template rendering, not freeform.

### 4.2 `apps/ai/src/session/relevance_gate.py` — already deterministic (model citizen)

- **File:** `apps/ai/src/session/relevance_gate.py`
- **Location:** `evaluate_relevance` (lines 132–223), `get_triggered_agents` (lines 226–258).
- **Current state:** This is **pure Python keyword routing — zero LLM tokens** (docstring line 4: "This is pure Python — zero LLM tokens. Fast and deterministic."). It uses `DOMAIN_KEYWORDS` + Trust Battery gating.
- **Verdict:** **Already compliant.** It is a positive example of the boundary, not a violation. **Keep it LLM-free.** If a future change proposes LLM intent classification here, it must be routed through ChiefOfStaff's bounded `classify_intent` contract instead, and the deterministic keyword path must remain the fast-path default.

### 4.3 `apps/ai/src/schemas/semantic_layer.py` — Tier-5 LLM-assisted resolution

- **File:** `apps/ai/src/schemas/semantic_layer.py`
- **Location:** `ResolutionTier.LLM_ASSISTED = "llm_assisted"` (line 40), the fifth and lowest-priority resolution tier.
- **Current state:** The schema declares the tier; the resolution *strategy* (in the Knowledge Agent) consults the LLM only for low-confidence cases after tiers 1–4 (EXACT → FUZZY → ATTRIBUTE → RELATIONSHIP) fail.
- **Gate required:** The LLM-assisted verdict must flow through the **Knowledge Agent's** `knowledge_resolve` contract (`{"alias_id", "resolve", "canonical_id", "confidence"}`), validated strictly, and the **merge is executed deterministically by the runtime** — the LLM returns a verdict, never a graph write. If the LLM verdict is low-confidence or schema-invalid, the runtime fails closed to a human review rather than auto-merging.

### 4.4 Summary table

| Call site | File | LLM today? | Action |
|-----------|------|-----------|--------|
| Artifact Executive Summary | `apps/ai/src/pipeline/artifact_engine.py` (Section 2, lines 156–180) | No (M0.5 deterministic) / intended LLM | Gate via `workspace_render_slots` template-slot contract |
| Relevance gate | `apps/ai/src/session/relevance_gate.py` | **No** (pure Python) | Keep LLM-free; route any future intent classification via ChiefOfStaff |
| Tier-5 entity resolution | `apps/ai/src/schemas/semantic_layer.py` (`ResolutionTier.LLM_ASSISTED`, line 40) | Yes (low-confidence cases) | Gate via `knowledge_resolve` verdict contract; runtime executes merge |

---

## 5. Vector store (pgvector) — deterministic retrieval

The vector store is **pgvector** (primary; Qdrant removed for MVP). It is kept behind a `VectorStore` abstraction with a single pgvector implementation for MVP. Vector retrieval is **deterministic** and is part of the **Decision Context Runtime** retrieval (see `docs/agents-and-prompt-contracts.md` §4).

- **Retrieval is deterministic.** pgvector similarity search is a pure, deterministic operation executed by the Decision Context Runtime — it is not an LLM step. The LLM consumes the *result* of retrieval (as `EvidenceRef`s in the `DecisionContext`), never the raw vector store.
- **The LLM never does vector-store writes.** Embeddings are generated deterministically (a deterministic embedding-model call) and stored via the `VectorStore` abstraction. The LLM has no write path to the vector store.
- **Embeddings are deterministic.** The embedding model call is a deterministic function of the input text; the resulting vector is stored via the `VectorStore` abstraction. This keeps the vector path replay-safe (see `docs/replay-engine.md`).

---

## 6. Enforcement checklist

- [ ] Every LLM call site returns JSON only, parsed before any branch.
- [ ] Every LLM payload passes a strict Pydantic contract (`extra="forbid"`, `strict=True`) from `src/decision/contracts.py`.
- [ ] No LLM output is consumed as business logic; it is always validated → canonicalized → governed.
- [ ] Execution Agent contains zero LLM.
- [ ] Ontology schema is defined only in code (`src/schemas/*`), never by an LLM.
- [ ] Retry ladder is bounded (`MAX_RETRIES = 2`) and fail-closed.
- [ ] All validation failures are audited via `AuditEvent`.
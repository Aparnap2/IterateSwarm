# OntologyAI V6 — Replay Engine

> **Status:** Design — OntologyAI V6 (Enterprise Decision Runtime)
> **Scope:** Documents the Replay Engine — the proof that the pipeline replays deterministically via Temporal. References the existing replay test suite (`apps/ai/tests/v6/test_replay.py`) and the Temporal queues (`apps/ai/src/temporal/queues.py`).
> **Companion docs:** [`docs/evidence-contracts.md`](./evidence-contracts.md) · [`docs/ADR-009-platform-runtime-freeze.md`](./ADR-009-platform-runtime-freeze.md) · [`docs/v6-runtime-architecture.md`](./v6-runtime-architecture.md)

---

## 1. What the Replay Engine proves

For a Temporal-based system, **deterministic replay is a required architectural property**. If replay changes output, there is nondeterminism in the pipeline stages. The Replay Engine verifies that the pipeline is deterministic: **same input → same output**, every time, across retries and re-executions.

Replay proves the following properties:

| Property | What it proves | How it's verified |
|----------|----------------|-------------------|
| **Idempotency** | Re-running the same input produces the same output; no double-effects | Run pipeline twice → identical serialized result |
| **Retry** | A failed/replayed stage re-executes to the same result (Temporal retries) | Deterministic stages produce identical output on re-run |
| **DLQ** | Failed records are quarantined deterministically, not silently dropped | Fail-closed validation + audit; replay preserves the same outcome |
| **Out-of-order** | Reordering of work does not change the final result | Deterministic stage order is invariant across runs |
| **Dedupe** | The SHA256 `hash` dedup is stable — same evidence → same hash → no duplicates | Unique, stable hashes across runs |

---

## 2. How replay is verified

### 2.1 The replay test suite — `apps/ai/tests/v6/test_replay.py`

The existing test suite (`TestReplayDeterminism`) runs the `VerticalSlicePipeline` multiple times and asserts the serialized results are identical. It uses a `_serialize_result()` helper that extracts **only deterministic fields** for comparison:

- `evidence_count`, `entity_count`, `entity_types`, `entity_confidences`
- `decision_options`, `feasibility_tiers`, `feasibility_totals`
- `artifact_section_count`, `validation_passed`, `validation_rule_count`
- `workspace_id`, `status`

It deliberately **excludes** items that vary on every run (timestamps, generated ULIDs) and includes only structural properties that must be invariant across replays.

The suite covers:
- **2 runs identical** — `test_replay_produces_identical_output`
- **3 runs identical** (stability) — `test_replay_three_times_identical`
- **Entity counts/types consistent** — `test_entity_counts_are_consistent`
- **Stage order consistent** — `test_stage_order_is_consistent`
- **Stage success consistent** — `test_stage_success_consistent`
- **Entity confidence identical** — `test_entity_confidence_identical`
- **Decision title/option count consistent** — `test_decision_title_consistent`
- **Feasibility scores/tiers consistent** — `test_feasibility_scores_consistent`
- **Validation consistency** — `test_validation_consistency`

### 2.2 Temporal test framework

In production, replay is verified through the **Temporal test framework** (`temporalio.testing` / the Temporal SDK's `WorkflowEnvironment`). Temporal's replay model works by:

1. Recording the **event history** of a workflow execution.
2. **Replaying** that history through the workflow code.
3. Asserting the workflow produces the **same decisions and outputs** on replay as on the original run.

If the workflow code is nondeterministic (e.g. it reads wall-clock time, iterates a map, or calls a non-deterministic API inside the workflow), replay diverges and Temporal raises a nondeterminism error. This is the enforcement mechanism behind the Replay Engine.

### 2.3 Temporal queues (from `apps/ai/src/temporal/queues.py`)

Per ADR-007, three isolated queues prevent head-of-line blocking across pipeline, agent, and validation workloads:

| Queue | Constant | Workload |
|-------|----------|----------|
| Pipeline | `ONTOLOGYAI_PIPELINE_QUEUE` = `"ONTOLOGYAI-PIPELINE-QUEUE"` | 14-stage knowledge pipeline (Ingest → Publish); dedicated pipeline workers (2–4) |
| Agent | `ONTOLOGYAI_AGENT_QUEUE` = `"ONTOLOGYAI-AGENT-QUEUE"` | Agent skill execution (LLM-backed stages); AI workers (2–4) |
| Validation | `ONTOLOGYAI_VALIDATION_QUEUE` = `"ONTOLOGYAI-VALIDATION-QUEUE"` | Validation engine + governance checks (V001–V008); lightweight workers (1–2) |

Replay determinism is preserved because each queue maps to deterministic workers; the LLM-backed stages are confined to typed input → typed output (see `docs/llm-boundary.md`), so their outputs are deterministic *given* the same validated input.

---

## 4. The medallion path (with the new names)

The Replay Engine verifies determinism across the full medallion path. The medallion layers have been renamed:

```
Raw Evidence (Bronze)  →  Canonical Evidence (Silver)  →  Enterprise Knowledge Model / EKM (Gold)
```

| Layer | Old name | New name | Runtime | Replay concern |
|-------|----------|----------|---------|----------------|
| L1 | Bronze | **Raw Evidence** | Evidence Runtime (Observe) | `EvidenceRecord` produced deterministically; dedup via SHA256 `hash` |
| L2 | Silver | **Canonical Evidence** | Knowledge Runtime (Understand) | Entity resolution + ontology mapping deterministic (rule + similarity); LLM only as stage-5 fallback |
| L3 | Gold | **Enterprise Knowledge Model (EKM)** | Knowledge Runtime (Understand) | Canonical entities, ontology, capability graph, conflicts — deterministic materialization |

The replay test suite exercises this path end-to-end via `VerticalSlicePipeline`: evidence → entities → decision → feasibility → artifact → validation. Because each stage is deterministic (or LLM-augmented with typed I/O), the whole path replays identically.

---

## 5. Determinism guarantees that make replay possible

Replay is only possible because the pipeline is deterministic. The guarantees that enable it:

1. **Deterministic validation gate** — connectors validate against versioned data contracts before producing `EvidenceRecord`s (see `docs/evidence-contracts.md`). No LLM in the gate.
2. **SHA256 dedup** — `hash = SHA256(tenant_id + canonical JSON structured_data)` is stable and exact.
3. **LLM confined to typed I/O** — LLM stages (Parse S2, Entity/Relationship Build S6) return typed JSON, validated by strict Pydantic contracts before any write. Given the same input, the validated output is deterministic.
4. **Deterministic feasibility/readiness math** — feasibility scores, readiness tiers, and blocking rules are pure code.
5. **Deterministic stage ordering** — the pipeline runs stages in a fixed order; replay preserves it.

---

## 6. Checklist

- [ ] Replay produces identical output across 2+ runs (`test_replay.py`).
- [ ] Temporal event-history replay raises on nondeterminism.
- [ ] Dedup via SHA256 `hash` is stable across replays.
- [ ] Validation gate is deterministic (no LLM).
- [ ] Medallion path uses the new names: Raw Evidence → Canonical Evidence → EKM.
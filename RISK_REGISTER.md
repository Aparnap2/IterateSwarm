# OntologyAI V6 — Risk Register

**Status:** LIVE (Phase 1)
**Owner:** Principal Implementation Agent
**Method:** Repo audit (contextscout) + architecture review (architect-reviewer) + plan reorder (risk-first).

Executing risk-first: prove the architecture survives **real data** and stays **deterministic**
before adding capability breadth.

---

## Risk Table

| ID | Risk | Likelihood | Impact | Current Mitigation | Owner |
|----|------|-----------|--------|--------------------|-------|
| R-01 | **Mockoon divergence** — 3 launch mechanisms (`start-mockoon.sh` :3000, Makefile Docker :8097-9, conftest.py :3333); V6 connectors need :3001-:3004 via mockoon-cli | High | High | P2: retire all divergent paths; single cli-per-config on 3001-3004 with health-check loop | WS-P1 |
| R-02 | **No evidence store (Bronze)** — `vertical_slice.py` Stage 1 keeps evidence in an in-memory `evidence_list`; no append-only store exists | High | High | P2/P3: build append-only Postgres evidence store w/ `hash` dedup; wire as real Stage | WS-P1/P2 |
| R-03 | **Two divergent Silver paths** — `entity_resolver.py` hardcodes Sarah Chen / Mike Liu; `semantic_layer.py`+`connector_bridge.py` (5-tier) exists but unwired | High | High | P5.5/P6: retire hardcoded `_EXTRACTED_ENTITIES`; standardize on `semantic_layer` data-driven resolution | WS-P4 |
| R-04 | **In-memory fallbacks mask persistence bugs** — `graph_builder`, `EKM`, `SemanticLayer` silently no-op to dicts when infra down | Medium | High | P4 + "persistence asserted" tests that query back the store, never just "no error" | WS-P5 |
| R-05 | **LLM leak into business logic (predates V6)** — `artifact_engine.py`, `session/relevance_gate.py` already call LLM | Medium | High | P5 gate: LLM→JSON→Pydantic→Canonical; LLM never writes graph/decision/evidence directly | WS-P3 |
| R-06 | **Replay/idempotency claimed without durable substrate** — `vertical_slice.py` synchronous; `worker.py` still single legacy queue | Medium | Medium | P2/P3: wire queue routing + activity boundaries early; prove replay via Temporal test framework in P4 | WS-P1 |
| R-07 | **Neo4j constraint mismatch** — `init.cypher` has 13 constraints, spec claims 24-entity ontology | Medium | Medium | P4: reconcile constraint set + add constraint-count test | WS-P5 |
| R-08 | **Schema export surface** — `schemas/__init__.py` omits `Capability`/`CapabilityRelationship`/`KnowledgeCatalogEntry` | Low | Low | P2: add to imports + `__all__` (5-min fix) | WS-P1 |
| R-09 | **Pipeline 10 vs 14 stages** — missing evidence-store persistence, conflict detection, graph enrichment, artifact versioning | Medium | Medium | P4/P5.5: add missing stages; conflict detection is a defined-but-unused stage today | WS-P5 |
| R-10 | **Dual EvidenceRecord** — V5.2 `evidence/models.py` (`evidence_id`) vs V6 `entities/models.py` (`id`) | Low | Medium | Consolidate on V6 model; deprecate `evidence` module | WS-P2 |

---

## Top 5 Highest-Value Risks

1. **R-01 Mockoon divergence** — highest operational risk; blocks all deterministic connector testing.
2. **R-02 No evidence store (Bronze)** — blocks replay/idempotency/tenant-isolation proof.
3. **R-03 Divergent Silver paths** — highest correctness risk; risks wiring entities onto hardcoded resolver.
4. **R-04 In-memory fallbacks** — risks false confidence in persistence tests.
5. **R-05 LLM leak** — risks LLM deciding business logic instead of narrating read-models.

---

## De-risk Sequence (Maps to Execution Phases)

- **P2 (WS-P1):** R-01, R-08, R-06 (queue routing), R-02 (evidence store build)
- **P3 (WS-P2):** R-02 (evidence store wiring + connector determinism), R-10
- **P4 (Real Infra):** R-04, R-07 + graph/vector/transaction/tenant/replay proof, R-06 (replay via Temporal)
- **P5 (Real LLM):** R-05
- **P5.5 (Knowledge Pipeline Validation):** R-03, R-09 (conflict/dedupe/out-of-order/stale/replay/idempotency)
- **P6 (WS-P4):** R-03 (wire unified entities), correctness of new-entity paths
- **P7 (WS-P5):** production-medallion proof against real infra
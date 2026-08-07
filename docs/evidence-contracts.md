# OntologyAI V6 — Evidence Contracts & Schema Registry

> **Status:** Design — OntologyAI V6 (Enterprise Decision Runtime)
> **Scope:** The Data Contract Layer between Connectors and Evidence. Defines the `Connector → Data Contract → EvidenceRecord` flow, the lightweight Schema Registry, and the deterministic validation gate that runs **before** any LLM stage.
> **Companion docs:** [`docs/llm-boundary.md`](./llm-boundary.md) (the frozen deterministic/LLM boundary) · [`docs/ADR-009-platform-runtime-freeze.md`](./ADR-009-platform-runtime-freeze.md) (platform freeze) · [`apps/ai/src/entities/models.py`](../apps/ai/src/entities/models.py) (canonical entities) · [`apps/ai/src/connectors/v6_contract.py`](../apps/ai/src/connectors/v6_contract.py) (connector protocol/manifest).

---

## 1. Purpose

The **Evidence Contract** is the versioned, deterministic contract that every connector must satisfy **before** it is allowed to produce an `EvidenceRecord`. It is the Data Contract Layer that sits between the raw external source and the Evidence Runtime.

It exists to guarantee:

1. **Deterministic validation before any LLM stage.** A connector's output is validated against a versioned schema by pure code. The LLM is never involved in this validation — per the LLM Allowed/Forbidden contract, **validation is FORBIDDEN for the LLM** (see `docs/llm-boundary.md` §1.2 and `docs/ADR-009-platform-runtime-freeze.md` "Allowed/Forbidden contract").
2. **Schema evolution without breakage.** Each connector declares a `schema_version`; each record carries it. When a source changes shape, the schema version bumps and downstream stages can branch on it deterministically.
3. **A single source of truth for field names.** The `EvidenceRecord` contract in `apps/ai/src/entities/models.py` is authoritative; connectors and the Schema Registry both reference it.

---

## 2. The `Connector → Data Contract → EvidenceRecord` flow

```
External source (Slack, Jira, Salesforce, Notion, …)
        │  raw payload
        ▼
┌──────────────────────────────────────────────────────────────┐
│  CONNECTOR  (pure adapter — no side effects, no state write) │
│  connect() → ConnectorManifest  (declares schema_version)    │
│  fetch()   → raw items                                       │
└──────────────────────────────────────────────────────────────┘
        │  raw item
        ▼
┌──────────────────────────────────────────────────────────────┐
│  DATA CONTRACT VALIDATION  (deterministic, pure code)        │
│  - resolve schema_version from the connector manifest        │
│  - validate the raw item against the versioned contract      │
│  - reject / quarantine on failure (fail-closed)              │
└──────────────────────────────────────────────────────────────┘
        │  validated, normalized payload
        ▼
┌──────────────────────────────────────────────────────────────┐
│  EvidenceRecord  (canonical entity, src/entities/models.py)  │
│  - carries schema_version                                    │
│  - provenance stamped (connector_version, extraction_method, │
│    raw_checksum, retry_count)                                │
│  - SHA256 hash for exact dedup                               │
└──────────────────────────────────────────────────────────────┘
        │
        ▼
   Evidence Runtime (Observe) → Parse (S2, LLM-augmented) → …
```

**Key rule:** a connector **must** validate against a versioned data contract **before** producing an `EvidenceRecord`. No record reaches the pipeline without passing the contract gate. This is a hard, deterministic gate — it is not an LLM step.

---

## 3. The Schema Registry (lightweight)

The Schema Registry is a lightweight, code-first registry of evidence schema versions. It is **not** a separate service — it is a versioned set of Pydantic schemas plus a lookup that maps `schema_version → schema`.

### 3.1 Version naming

Schema versions are namespaced by connector and monotonically incremented:

| `schema_version` | Connector | Notes |
|------------------|-----------|-------|
| `slack.v1` | Slack | messages / channels / users |
| `slack.v2` | Slack | future shape change (e.g. new field, changed `structured_data`) |
| `salesforce.v1` | Salesforce | accounts / opportunities / contacts |
| `jira.v1` | Jira | issues / projects / comments |
| `notion.v1` | Notion | pages / databases |

The generic default is `v1`. A connector that has not yet been assigned a namespaced version uses `v1`; the registry is expected to grow namespaced versions as connectors are onboarded.

### 3.2 Where the version lives

- **Connector manifest** (`ConnectorManifest` in `apps/ai/src/connectors/v6_contract.py`) declares the connector's supported schema version(s). This is the natural place for the connector to advertise `schema_version`.
- **Every `EvidenceRecord`** carries `schema_version` (see §4). This makes each record self-describing and lets downstream stages branch deterministically on the version.

### 3.3 Registry contract

```python
# Lightweight registry shape (conceptual — code-first, not a service)
SCHEMA_REGISTRY: dict[str, EvidenceSchema] = {
    "slack.v1": SlackEvidenceSchema,
    "salesforce.v1": SalesforceEvidenceSchema,
    "jira.v1": JiraEvidenceSchema,
    "notion.v1": NotionEvidenceSchema,
}

def resolve_schema(schema_version: str) -> EvidenceSchema:
    """Deterministic lookup. Raises on unknown version (fail-closed)."""
    ...
```

---

## 4. The `EvidenceRecord` contract

The canonical `EvidenceRecord` is defined in `apps/ai/src/entities/models.py`. It is the atomic unit of knowledge. All models use `extra="forbid"` and `strict=True`.

### 4.1 Field reference (exact names from `src/entities/models.py`)

| Field | Type | Required | Notes |
|-------|------|----------|-------|
| `id` | `str` | ✅ | ULID |
| `tenant_id` | `str` | ✅ | Tenant isolation boundary |
| `source` | `str` | ✅ | Connector name (e.g. `"slack"`) |
| `source_type` | `Literal[...]` | ✅ | `connector` / `chat` / `upload` / `transcript` / `spreadsheet` / `email` / `screenshot` / `api` |
| `schema_version` | `str` | default `"v1"` | Evidence schema version (e.g. `"slack.v1"`) |
| `timestamp` | `datetime` | ✅ | When the evidence was created in the source |
| `confidence` | `float` | ✅ | `[0.0, 1.0]` |
| `provenance` | `Provenance` | ✅ | Connector provenance (see below) |
| `structured_data` | `dict` | default `{}` | Parsed payload |
| `raw_content` | `str \| None` | optional | Unparsed body/document |
| `embeddings` | `list[float] \| None` | optional | Vector embedding (pgvector) |
| `entity_refs` | `list[str]` | default `[]` | Internal entity IDs |
| `source_refs` | `list[str]` | default `[]` | External resource URLs |
| `chunk_ref` | `str \| None` | optional | Chunk reference |
| `hash` | `str` | ✅ | SHA256 of canonical JSON(`tenant_id` + `structured_data`) — exact dedup |

### 4.2 `Provenance` (nested)

| Field | Type | Notes |
|-------|------|-------|
| `connector_version` | `str` | Connector software version |
| `extraction_method` | `str` | `"api"`, `"webhook"`, … |
| `raw_checksum` | `str` | SHA256 of `raw_content` (before parsing) |
| `retry_count` | `int` | default `0` |

### 4.3 Connector manifest (`ConnectorManifest` in `src/connectors/v6_contract.py`)

The manifest returned by `connect()` describes identity, capabilities, and constraints. It is the natural place for a connector to declare its `schema_version` alongside `version`, `capabilities`, `supported_objects`, `sync_strategy`, etc.

---

## 5. Deterministic validation before any LLM stage

Validation is a **pure-code, deterministic** step. It is the first gate a raw payload passes through and it runs **before** any LLM stage (Parse S2, Entity/Relationship Build S6).

### 5.1 Why validation is FORBIDDEN for the LLM

Per the frozen LLM Allowed/Forbidden contract (`docs/ADR-009-platform-runtime-freeze.md`):

> **ALLOWED:** extraction, classification, summarization, reasoning, recommendation, narrative.
> **FORBIDDEN:** business rules, ontology, policy, state, execution, **validation**, permissions.

Validation is deterministic by design. If an LLM validated evidence, the evidence would no longer be trustworthy — its "validity" would be an opinion, not a fact. The Evidence Runtime's Discovery agent is a *sensor*, not a brain (see `docs/agents-and-prompt-contracts.md` §3.1).

### 5.2 The validation gate

```
raw item
   │
   ▼
[1] Resolve schema_version from the registry        (deterministic)
   │
   ▼
[2] Validate raw item against the versioned schema  (deterministic, Pydantic)
   │  fail → reject + quarantine to audit log (fail-closed)
   ▼
[3] Normalize into EvidenceRecord fields            (deterministic)
   │
   ▼
[4] Stamp provenance + compute SHA256 hash          (deterministic)
   │
   ▼
[5] Emit EvidenceRecord → Evidence Runtime          (LLM stages may now run)
```

**Guarantees:**
1. **Fail-closed.** A record that fails the contract is rejected and quarantined — never a best-effort partial write.
2. **No LLM in the gate.** The gate is pure code; the LLM only ever sees already-validated records.
3. **Versioned.** The gate resolves the exact schema version, so schema evolution is explicit and auditable.

---

## 6. Alignment with the frozen platform

- **Vector:** `embeddings` on `EvidenceRecord` are stored via the `VectorStore` abstraction backed by **pgvector** (primary). Qdrant is removed for MVP. Retrieval is deterministic and part of the Decision Context Runtime; the LLM never writes to the vector store. See `docs/llm-boundary.md` §5.
- **Medallion rename:** Raw Evidence (Bronze) → Canonical Evidence (Silver) → **Enterprise Knowledge Model (EKM)** (Gold). The `EvidenceRecord` is the **Raw Evidence** unit; the Knowledge Runtime promotes it into Canonical Evidence and the EKM.
- **Deferred to V6.5 (NOT MVP):** Decision Store, Feature Store, Knowledge Cache. These are out of scope for the Evidence Contract layer.

---

## 7. Checklist

- [ ] Every connector validates against a versioned data contract before producing an `EvidenceRecord`.
- [ ] Every connector declares `schema_version` (in its manifest).
- [ ] Every `EvidenceRecord` carries `schema_version`.
- [ ] Validation is deterministic, pure code — never an LLM step.
- [ ] Unknown schema versions fail closed (never silently accepted).
- [ ] Validation failures are audited.
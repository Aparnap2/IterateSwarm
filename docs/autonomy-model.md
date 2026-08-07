# OntologyAI V6.1 — Risk-Tiered Autonomy Model

**Status:** FROZEN (implementable contract)
**Version:** 1.0
**Date:** 2026-08-05
**Author:** Solution Architecture
**Depends on:** `docs/v6-runtime-architecture.md` (frozen), `docs/decision-context-runtime.md` (frozen), `V6_DOMAIN_SPEC.md` §11 (signals), §12 (ADR-007 queues)
**Constitution:** This is the implementable contract for the Action Runtime (R5). It does not modify production code.

---

## 1. Principle

**Act is policy-driven by RISK, not by a HITL/autonomous binary.**

Autonomy is a **continuum of three risk tiers**, each with a deterministic policy. The runtime decides *how much human governance* an action requires based on its risk tier — never on whether an LLM "feels" confident.

The Execution agent **never reasons**. It executes approved actions only, through the **Deterministic Action Scheduler**. There is no LLM call in the execution path.

---

## 2. Risk Classification (deterministic)

The Autonomy Classifier (in the Decision Runtime, R3) assigns a `risk_tier` to every proposed action. Classification is **code + config**, never LLM output. It is derived from three deterministic inputs:

1. **Action category** (from the action registry — see §5).
2. **Policy evaluation** (active `BusinessRule`/`Constraint`/`CatalogPolicy`).
3. **Approval matrix** (versioned config: role → authority → tier).

### 2.1 Risk tiers

| Tier | Definition | Autonomy | Examples |
|------|-----------|----------|----------|
| **Low** | Informational / read-only / no financial authority / no production change / no permission grant / no customer-data exposure | **Auto-execute** | Generate Jira ticket, Slack summary, PRD draft, architecture doc, SOP, meeting notes; read-only analysis; internal artifact publish |
| **Medium** | Creates or modifies business records, external-facing communications, or applies approved config — but reversible and non-destructive | **Draft → manager approval → execute** | Create a PR, apply an approved config change, schedule a meeting, send an external-facing communication, create a business record with non-trivial scope |
| **High** | Destructive, irreversible, financially authoritative, production-modifying, permission-granting, or compliance-sensitive | **NEVER autonomous** | Delete a customer, change pricing, approve spend, modify production, grant permissions, compliance-sensitive actions |

### 2.2 High-risk denylist (explicit, frozen)

The following action categories are **always** High risk regardless of any other signal:

- delete customer / delete production data
- change pricing / approve spend / financial authority
- modify production / deploy to prod / change infrastructure
- grant permissions / change access control
- compliance-sensitive actions (regulated data, legal, audit)
- any action touching a `CatalogPolicy` with `enforcement = "mandatory"` and `severity = "block"`

### 2.3 Classification rules

```
risk_tier(action) =
    HIGH    if action.category in HIGH_RISK_DENYLIST
            or any active policy with severity=block applies
            or action.financial_authority > 0
            or action.touches_production or action.grants_permissions
    MEDIUM  if action.category in MEDIUM_RISK_CATEGORIES
            or action.external_facing
            or action.creates_or_modifies_business_record
    LOW     otherwise
```

The tier is **recomputed inside the policy gate** at execution time — it is never trusted from the Decision agent's output (defense in depth).

---

## 3. The Policy Gate (frozen)

Every action passes through a four-stage deterministic gate before it can be scheduled:

```
Validation → Policy → Governance → Execution
```

| Stage | Owner | Deterministic? | What it does | Fail → |
|-------|-------|----------------|--------------|--------|
| **1. Validation** | Workspace Runtime (R4) | Yes | Action payload is schema-valid; required evidence links present (V001/V002 subset); action references a real decision/workspace | Reject with `ValidationResult` |
| **2. Policy** | Action Runtime (R5) | Yes | Evaluate active `BusinessRule`/`Constraint`/`CatalogPolicy` against the action; apply blocking rules | Block (never proceeds) |
| **3. Governance** | Action Runtime (R5) | Yes | Look up the **approval matrix** → resolve risk tier → route: Low = auto; Medium = manager approval; High = blocked | Medium: hold for approval; High: reject |
| **4. Execution** | Action Runtime (R5) | Yes | Enqueue approved action on the Deterministic Action Scheduler; Execution agent executes | Retry/DLQ per Temporal policy |

### 3.1 Governance routing (approval matrix)

The approval matrix is versioned config (never LLM-authored):

| Risk tier | Route | Human step |
|-----------|-------|------------|
| Low | Auto | None |
| Medium | Manager approval | Draft → manager approves/rejects via `SignalWorkflow("hitl-approval")` (reused from V5.2) |
| High | Blocked | Rejected; escalation to governance owner; `AuditEvent` logged |

Medium-risk approval reuses the existing HITL signal pattern (`SignalWorkflow("hitl-approval")` unblocks `AwaitWithTimeout`), preserving the Go handler and Temporal wiring already in production.

---

## 4. The Deterministic Action Scheduler (frozen)

The scheduler is a **deterministic state machine** over an `Action` table (Postgres). It holds **approved actions only** and drives them to completion. It has no LLM dependency.

### 4.1 Action schema

```yaml
Action:
  id: string (ULID)
  decision_id: string (ULID)
  workspace_id: string (ULID)
  tenant_id: string (ULID)
  action_type: string                # from the action registry (see §5)
  category: string                   # e.g. "jira_ticket", "slack_message", "prd_draft"
  risk_tier: enum(low, medium, high)
  status: enum(
    pending_validation, valid, policy_passed,
    awaiting_approval, approved, queued,
    executing, executed, failed, rejected, superseded
  )
  payload: dict                      # fully typed, validated (extra="forbid", strict)
  approved_by: string (ULID) | null  # manager for medium risk
  approved_at: datetime | null
  created_at: datetime
  executed_at: datetime | null
  result: dict | null                # execution result (template-rendered, no free-form LLM)
  audit_event_id: string (ULID) | null
```

### 4.2 State machine

```
pending_validation → valid → policy_passed → awaiting_approval → approved → queued → executing → executed
        │                │            │              │                 │            │
        └── rejected ────┘            └── rejected ───┘                 └── failed ──┘
                                                                              │
                                                                              └── (retry / DLQ)
```

Transitions are deterministic and driven by Temporal activities. No transition is decided by an LLM.

### 4.3 Scheduler invariants

1. **Approved-actions only**: the scheduler never enqueues an action that has not passed the policy gate.
2. **No reasoning**: the Execution agent receives a fully typed `payload` and a template; it renders output and calls the target connector/tool. It does not classify intent, generate free-form text, or interpret results.
3. **Idempotency**: each action executes at most once (idempotency key = `action_id`); retries are safe.
4. **Audit**: every state transition writes an `AuditEvent` (immutable, append-only).
5. **Supersession**: if Continuous Decision Monitoring invalidates the parent decision, queued-but-unexecuted actions are marked `superseded` and never execute.

---

## 5. Action Registry (frozen)

The action registry is a deterministic catalog of executable action types. Each entry declares its category, risk tier, payload schema, and target tool/connector.

| action_type | category | risk_tier | Target | Notes |
|-------------|----------|-----------|--------|-------|
| `jira_ticket` | jira_ticket | low | Jira connector | Auto-create |
| `slack_message` | slack_message | low | Slack connector | Auto-send (internal) |
| `prd_draft` | prd_draft | low | Workspace Runtime | Auto-generate artifact |
| `architecture_doc` | architecture_doc | low | Workspace Runtime | Auto-generate artifact |
| `sop` | sop | low | Workspace Runtime | Auto-generate artifact |
| `meeting_notes` | meeting_notes | low | Workspace Runtime | Auto-generate artifact |
| `create_pr` | create_pr | medium | Git connector | Draft → manager approval |
| `apply_config_change` | config_change | medium | Config store | Draft → manager approval |
| `schedule_meeting` | schedule_meeting | medium | Calendar connector | Draft → manager approval |
| `external_communication` | external_comm | medium | Slack/Email | Draft → manager approval |
| `delete_customer` | delete_customer | **high** | CRM connector | **Never autonomous** |
| `change_pricing` | pricing | **high** | Pricing store | **Never autonomous** |
| `approve_spend` | spend | **high** | Finance | **Never autonomous** |
| `modify_production` | production | **high** | Infra | **Never autonomous** |
| `grant_permissions` | permissions | **high** | IAM | **Never autonomous** |

Adding a new action = one registry entry + one payload schema + one target tool binding. No new agent.

---

## 6. Execution Agent Contract (frozen)

The Execution agent is the **only** agent that touches external systems on the Act path. Its contract:

- **Input**: an `approved` `Action` (typed `payload` + template id).
- **Behavior**: render the payload via the template, call the target connector/tool, capture the result.
- **Output**: a typed `result` dict; no free-form narrative.
- **Constraints**:
  - No LLM call in the execution path.
  - No intent classification.
  - No policy decisions (already decided by the gate).
  - No autonomous escalation (escalation is a gate function, not an agent function).
  - Every execution writes an `AuditEvent`.

---

## 7. Never AI-Owned (frozen, restated for the Act layer)

The following are **deterministic only** and are enforced by the Action Runtime:

business rules, ontology definition, policy, approval matrix, security, financial authority, production permissions, compliance logic.

The Execution agent and the policy gate never delegate these to an LLM. The Decision agent may *reason about* them (via the Decision Context Runtime) but cannot *author* or *override* them.

---

## 8. Continuous Decision Monitoring tie-in

When Continuous Decision Monitoring (Learning Runtime, R6) marks a decision stale:

1. The parent decision is set to `superseded` (append-only).
2. Any queued-but-unexecuted actions for that decision are marked `superseded` and never execute.
3. The Decision Context Runtime re-assembles context; the Decision agent re-reasons; the Workspace Runtime re-projects artifacts.
4. Stakeholders are notified: **"Your previous decision is no longer valid."**

This guarantees that a stale decision can never drive a new autonomous action.

---

## 9. Risks Flagged

| # | Risk | Mitigation |
|---|------|------------|
| R1 | Medium-risk action misclassified Low → auto-executes with financial/production impact | High-risk denylist is explicit; tier recomputed in the gate; `AuditEvent` on every action |
| R2 | Manager approval fatigue on Medium tier | Approval matrix is configurable; batch approvals; clear draft → approve → execute workflow |
| R3 | Execution agent "reasons" via tool output interpretation | No LLM in execution path; typed payloads; template-rendered output; audit trail |
| R4 | Stale decision drives a new action before monitoring catches it | Scheduler checks parent decision validity before enqueue; supersession is synchronous with monitoring |
| R5 | Policy gate becomes a bottleneck | Validation/Policy/Governance are lightweight deterministic activities on the validation queue (ADR-007); scale independently |

---

*This contract is frozen. It implements the Act layer of `docs/v6-runtime-architecture.md` and consumes the `priorities.risk_tier` produced by `docs/decision-context-runtime.md`.*
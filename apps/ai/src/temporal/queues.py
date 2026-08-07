"""Temporal task queue names for OntologyAI V6.

Per ADR-007, three isolated queues prevent head-of-line blocking across
the pipeline, agent, and validation workloads.
"""

# ── Pipeline Queue ──────────────────────────────────────────────────────
# 14-stage knowledge pipeline (Ingest → Publish).
# Dedicated pipeline workers (2-4); scales with evidence volume.
ONTOLOGYAI_PIPELINE_QUEUE = "ONTOLOGYAI-PIPELINE-QUEUE"

# ── Agent Queue ─────────────────────────────────────────────────────────
# Agent skill execution (LLM-backed stages: Parse, Entity Build, Decision
# Analysis, Artifact Projection).
# AI workers (2-4); scales with LLM latency.
ONTOLOGYAI_AGENT_QUEUE = "ONTOLOGYAI-AGENT-QUEUE"

# ── Validation Queue ────────────────────────────────────────────────────
# Validation engine + governance checks (V001–V008).
# Lightweight workers (1-2); scales with artifact frequency.
ONTOLOGYAI_VALIDATION_QUEUE = "ONTOLOGYAI-VALIDATION-QUEUE"

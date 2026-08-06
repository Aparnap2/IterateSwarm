"""V6 OntologyAI — Validation Engine.

Per §7 of the V6 spec, the Validation Engine applies 8 rules (V001–V008)
to artifacts before they can be published.  Rules run in numeric order;
the first block-level failure short-circuits the run.

All rule implementations are deterministic for M0.5 — no LLM calls.
"""

from src.validation.validation_engine import (
    ValidationEngine,
    ValidationOutput,
    ValidationResultItem,
    ValidationRule,
)

__all__ = [
    "ValidationEngine",
    "ValidationOutput",
    "ValidationResultItem",
    "ValidationRule",
]

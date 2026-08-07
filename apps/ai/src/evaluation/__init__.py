"""Evaluation Runtime package for OntologyAI V6.

Exports the Evaluation Runtime protocol and default implementation.

The Evaluation Runtime replaced the former "Outcome Runtime" (renamed during
the V6.0 M0.5 pivot).  The key insight from the pivot:

> "You don't have Actions yet. Without Actions there are no Outcomes."

So instead of tracking *what happened after execution*, the Evaluation
Runtime focuses on:

* Metrics — compute design-time metrics from decisions and reviews
* Confidence — update confidence scores based on evidence quality
* Replay — re-evaluate past decisions against current evidence
* Golden Dataset — track decision accuracy over time

FROZEN — V6.0 M0.5
"""

from src.evaluation.runtime import (
    BaseEvaluationRuntime,
    DefaultEvaluationRuntime,
    EvaluationRuntime,
    EvaluationRuntimeError,
    MetricError,
    RecordingError,
    get_evaluation_runtime,
)

__all__ = [
    "EvaluationRuntime",
    "BaseEvaluationRuntime",
    "DefaultEvaluationRuntime",
    "EvaluationRuntimeError",
    "MetricError",
    "RecordingError",
    "get_evaluation_runtime",
]

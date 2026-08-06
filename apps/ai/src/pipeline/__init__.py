"""V6 OntologyAI — Pipeline engines for the vertical-slice proof.

Contains the orchestrator plus the five core engines run during a
full pipeline cycle:

* **Decision Engine** — creates decisions, generates options.
* **Feasibility Engine** — multi-dimensional option scoring.
* **Artifact Engine** — project artifacts from canonical model data.
* **Validation Engine** — run V001–V008 rules.
* **Vertical Slice Pipeline** — end-to-end orchestrator calling every
  layer in order.
"""

from src.pipeline.vertical_slice import VerticalSlicePipeline
from src.pipeline.decision_engine import DecisionEngine, DecisionEngineResult
from src.pipeline.feasibility_engine import FeasibilityEngine, FeasibilityResult
from src.pipeline.artifact_engine import ArtifactEngine, ArtifactResult
from src.pipeline.validation_engine import ValidationEngine, ValidationResult

__all__ = [
    "VerticalSlicePipeline",
    "DecisionEngine",
    "DecisionEngineResult",
    "FeasibilityEngine",
    "FeasibilityResult",
    "ArtifactEngine",
    "ArtifactResult",
    "ValidationEngine",
    "ValidationResult",
]

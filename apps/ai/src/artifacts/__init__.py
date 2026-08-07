"""V6 OntologyAI — Artifact Projection Engine.

Per §6 of the V6 spec, artifacts are read-model projections computed from
the canonical model (Neo4j entities + Postgres transactional data) at
generation time.  Every field in an artifact must trace to either an
Evidence record or a computed Decision score.

This package contains:

*   ``dsl_loader`` — loads and validates artifact DSL YAML configs
*   ``template_engine`` — Jinja2-based template renderer
*   ``projection_engine`` — orchestrates artifact projection from DSL + model
*   ``registry/`` — YAML configs for all 18 artifacts (12 external + 6 internal)
"""

from src.artifacts.dsl_loader import DSLLoader, ArtifactDSL, ArtifactSection
from src.artifacts.projection_engine import ProjectionEngine
from src.artifacts.template_engine import TemplateEngine

__all__ = [
    "DSLLoader",
    "ArtifactDSL",
    "ArtifactSection",
    "TemplateEngine",
    "ProjectionEngine",
]

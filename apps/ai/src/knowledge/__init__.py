"""V6 OntologyAI — Knowledge layer (Entity Resolution, Graph Build, EKM, Semantic Layer).

The knowledge layer sits between connectors (ingest) and the pipeline
(orchestration).  It is responsible for:

* **Entity Resolution** — extracting canonical entities from evidence
  ``structured_data`` and matching against the Neo4j graph.
* **Graph Builder** — writing resolved entity nodes, evidence nodes, and
  typed relationships to Neo4j.
* **Enterprise Knowledge Model** — storing interpreted business state
  (confidence, derived metrics, classifications) in PostgreSQL.
* **Semantic Layer** — canonical entity resolution across source systems
  with 5-tier resolution strategy, conflict resolution, and lineage tracking.
* **Connector Bridge** — bridges connector EvidenceRecords into the semantic layer.
"""

from src.knowledge.conflict_resolver import ConflictResolver
from src.knowledge.connector_bridge import ConnectorBridge, IngestResult
from src.knowledge.entity_resolver import EntityResolver, EntityResolutionResult
from src.knowledge.graph_builder import GraphBuilder
from src.knowledge.semantic_layer import (
    InMemoryEntityStore,
    ResolutionResult,
    ResolutionTier,
    SemanticLayer,
)
from src.knowledge.enterprise_knowledge_model import EnterpriseKnowledgeModel

__all__ = [
    "EntityResolver",
    "EntityResolutionResult",
    "GraphBuilder",
    "EnterpriseKnowledgeModel",
    "SemanticLayer",
    "ResolutionResult",
    "ResolutionTier",
    "InMemoryEntityStore",
    "ConflictResolver",
    "ConnectorBridge",
    "IngestResult",
]

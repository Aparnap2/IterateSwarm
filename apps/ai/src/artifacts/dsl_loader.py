"""V6 OntologyAI — DSL Config Loader.

Per §6 (ADR-003) of the V6 spec, all 18 artifacts (12 external + 6 internal)
are defined via declarative YAML config files loaded at runtime.  The DSL
Loader validates each config against ``ArtifactDSL`` (Pydantic) schema
before returning it.

DSL configs live in ``apps/ai/src/artifacts/registry/*.yaml``.
"""

from __future__ import annotations

import glob
import logging
import os
from typing import Any

import yaml
from pydantic import BaseModel, ConfigDict, Field

logger = logging.getLogger(__name__)


# ── Exceptions ──────────────────────────────────────────────────────────


class DSLLoadError(Exception):
    """Raised when a DSL config cannot be loaded or validated."""


# ── Pydantic models for the DSL schema ──────────────────────────────────


VALID_SECTION_TYPES = frozenset({
    "title",
    "summary",
    "evidence_list",
    "decision_table",
    "recommendation_list",
    "risk_matrix",
    "impact_analysis",
    "kpi_table",
    "stakeholder_table",
    "timeline",
    "gantt",
    "diagram_placeholder",
    "narrative",
    "table",
    "list",
})


class ArtifactSection(BaseModel):
    """A single section within an artifact DSL config.

    Maps a named section to its type, source dot-path in the canonical
    model, and optional LLM augmentation flag.
    """

    model_config = ConfigDict(extra="forbid", strict=True)

    name: str = Field(..., min_length=1)
    type: str = Field(..., pattern=r"^[a-z_]+$")
    source: str = Field(..., min_length=1)
    llm_augment: bool = False
    config: dict[str, Any] = Field(default_factory=dict)


class ArtifactDSL(BaseModel):
    """The top-level artifact DSL config — validated at load time.

    Maps the full YAML structure described in §6.1 of the V6 spec.
    """

    model_config = ConfigDict(extra="forbid", strict=True)

    id: str = Field(..., min_length=1)
    name: str = Field(..., min_length=1)
    type: str = Field(..., pattern=r"^(external|internal)$")
    audience: list[str] = Field(default_factory=list)
    model_dependencies: list[str] = Field(default_factory=list)
    sections: list[ArtifactSection] = Field(..., min_length=1)
    validation: dict[str, Any] = Field(default_factory=dict)
    traceability: dict[str, Any] = Field(default_factory=dict)


# ── Registry path helpers ───────────────────────────────────────────────


def _default_registry_path() -> str:
    """Return the default path to the artifact registry directory."""
    here = os.path.dirname(os.path.abspath(__file__))
    return os.path.join(here, "registry")


# ── DSLLoader ───────────────────────────────────────────────────────────


class DSLLoader:
    """Loads and validates Artifact DSL YAML configs.

    DSL configs live in ``apps/ai/src/artifacts/registry/*.yaml``.
    Each config is validated against the ``ArtifactDSL`` schema.
    """

    def __init__(self, registry_path: str | None = None) -> None:
        """Initialise the loader.

        Parameters
        ----------
        registry_path:
            Path to the directory containing ``*.yaml`` DSL configs.
            Defaults to ``apps/ai/src/artifacts/registry/``.
        """
        self._registry_path = registry_path or _default_registry_path()
        self._cache: dict[str, ArtifactDSL] = {}

        if not os.path.isdir(self._registry_path):
            logger.warning(
                "Artifact registry directory not found: %s. "
                "No DSL configs will be available.",
                self._registry_path,
            )

    # ── Public API ───────────────────────────────────────────────────

    def load(self, artifact_id: str) -> ArtifactDSL:
        """Load a single artifact DSL config by ID.

        Parameters
        ----------
        artifact_id:
            The ``id`` field from the YAML config (e.g.
            ``"executive-decision-brief"``).

        Returns
        -------
        ArtifactDSL
            The validated DSL config.

        Raises
        ------
        DSLLoadError
            If the artifact ID is not found or the config is invalid.
        """
        # Check cache first
        if artifact_id in self._cache:
            return self._cache[artifact_id]

        # Find the matching YAML file
        pattern = os.path.join(self._registry_path, "*.yaml")
        for filepath in sorted(glob.glob(pattern)):
            try:
                with open(filepath, "r") as f:
                    raw: dict[str, Any] = yaml.safe_load(f)
            except Exception as exc:
                logger.warning("Failed to read %s: %s", filepath, exc)
                continue

            artifact_cfg = self.validate_config(raw)
            if artifact_cfg.id == artifact_id:
                self._cache[artifact_id] = artifact_cfg
                logger.info("Loaded and cached artifact DSL: %s", artifact_id)
                return artifact_cfg

        raise DSLLoadError(
            f"Artifact DSL '{artifact_id}' not found in {self._registry_path}. "
            f"Ensure a YAML file with id=\"{artifact_id}\" exists in the registry."
        )

    def list_artifacts(self) -> list[ArtifactDSL]:
        """List all available artifact DSL configs.

        Returns
        -------
        list[ArtifactDSL]
            All validated DSL configs found in the registry directory.
        """
        results: list[ArtifactDSL] = []
        pattern = os.path.join(self._registry_path, "*.yaml")

        for filepath in sorted(glob.glob(pattern)):
            try:
                with open(filepath, "r") as f:
                    raw: dict[str, Any] = yaml.safe_load(f)
                cfg = self.validate_config(raw)
                results.append(cfg)
                self._cache[cfg.id] = cfg
            except Exception as exc:
                logger.warning("Skipping %s due to error: %s", filepath, exc)
                continue

        return results

    def validate_config(self, config: dict[str, Any]) -> ArtifactDSL:
        """Validate a raw YAML dict against ``ArtifactDSL`` schema.

        Parameters
        ----------
        config:
            The parsed YAML content.  Must contain an ``artifact`` key
            and a ``sections`` key (per §6.1).

        Returns
        -------
        ArtifactDSL
            The validated config.

        Raises
        ------
        DSLLoadError
            If validation fails.
        """
        try:
            # The YAML has a top-level "artifact" key wrapping the metadata
            artifact_block: dict[str, Any] = config.get("artifact", config)
            sections_raw: list[dict[str, Any]] = config.get("sections", [])

            # Build the validated sections
            sections = [ArtifactSection(**s) for s in sections_raw]

            # Build the full DSL model
            dsl = ArtifactDSL(
                id=artifact_block.get("id", ""),
                name=artifact_block.get("name", ""),
                type=artifact_block.get("type", "internal"),
                audience=artifact_block.get("audience", []),
                model_dependencies=artifact_block.get("model_dependencies", []),
                sections=sections,
                validation=config.get("validation", {}),
                traceability=config.get("traceability", {}),
            )
        except Exception as exc:
            raise DSLLoadError(
                f"Failed to validate DSL config: {exc}"
            ) from exc

        # Post-validation: verify section types are known
        for section in dsl.sections:
            if section.type not in VALID_SECTION_TYPES:
                logger.warning(
                    "Section '%s' has unknown type '%s'. Known types: %s",
                    section.name,
                    section.type,
                    ", ".join(sorted(VALID_SECTION_TYPES)),
                )

        return dsl

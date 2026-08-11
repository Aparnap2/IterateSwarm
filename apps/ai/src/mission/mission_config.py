"""Mission config — a mission is a business objective assigned to one employee.

Missions load from ``config/missions.yaml`` as validated :class:`MissionSpec`
objects. A mission's ``mission_type`` must be within the owning employee's
``mission_types`` allowlist and its default skill plan must be a subset of the
employee's skill allowlist (enforced by the runtime at selection time).
"""
from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Literal

import yaml
from pydantic import Field

from src.entities.models import OntologyBaseModel

logger = logging.getLogger(__name__)


class MissionNotAllowedError(KeyError):
    """Raised when a mission is not admissible for its employee role."""


class MissionSpec(OntologyBaseModel):
    """A validated mission definition from config/missions.yaml."""

    id: str
    title: str
    description: str = ""
    employee_role: str
    mission_type: str
    priority: Literal["low", "medium", "high", "urgent"] = "medium"
    kpi_ids: list[str] = Field(default_factory=list)
    skill_plan: list[str] = Field(default_factory=list)


def _find_config(path: str | None = None) -> Path:
    """Locate config/missions.yaml (explicit path or search path)."""
    if path:
        candidate = Path(path)
        if candidate.exists():
            return candidate
        raise FileNotFoundError(f"missions config not found: {path}")
    candidates = [
        Path.cwd() / "config" / "missions.yaml",
        Path(__file__).resolve().parents[2] / "config" / "missions.yaml",
        Path(__file__).resolve().parents[1] / "config" / "missions.yaml",
    ]
    for candidate in candidates:
        if candidate.exists():
            return candidate
    raise FileNotFoundError("config/missions.yaml not found on any search path")


def _load_text(path: Path) -> str:
    """Read the file and expand ${VAR} environment placeholders."""
    return os.path.expandvars(path.read_text(encoding="utf-8"))


class MissionRegistry:
    """Registry of canonical missions loaded from config/missions.yaml."""

    _missions: dict[str, MissionSpec] = {}
    _loaded: bool = False

    @classmethod
    def load(cls, path: str | None = None) -> dict[str, MissionSpec]:
        """Load (once) and return {mission_id: MissionSpec}."""
        if cls._loaded and path is None:
            return dict(cls._missions)

        config_path = _find_config(path)
        data = yaml.safe_load(_load_text(config_path)) or {}
        missions: dict[str, MissionSpec] = {}
        for raw in data.get("missions", []):
            spec = MissionSpec(**raw)
            missions[spec.id] = spec

        if not missions:
            raise ValueError(f"missions.yaml at {config_path} contained no missions")

        cls._missions = missions
        cls._loaded = True
        logger.info("Loaded %d missions from %s", len(missions), config_path)
        return dict(cls._missions)

    @classmethod
    def get(cls, mission_id: str) -> MissionSpec:
        """Return the spec for *mission_id*, raising :class:`MissionNotFoundError`."""
        if not cls._loaded:
            cls.load()
        try:
            return cls._missions[mission_id]
        except KeyError:
            raise MissionNotAllowedError(
                f"unknown mission {mission_id!r}; loaded: {sorted(cls._missions)}"
            ) from None

    @classmethod
    def canonical_missions(cls) -> list[MissionSpec]:
        """Return the loaded canonical missions as a list."""
        if not cls._loaded:
            cls.load()
        return list(cls._missions.values())
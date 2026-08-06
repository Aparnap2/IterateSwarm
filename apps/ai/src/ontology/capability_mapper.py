"""OntologyAI V6 — Capability Mapper (ADR-013 §6).

Maps evidence records to capabilities using a 3-tier strategy:
  Tier 1: Keyword matching (deterministic)
  Tier 2: LLM classification (augmented)
  Tier 3: Manual tagging (HITL)

Runs at pipeline Stage 6 after entity resolution.
"""
from __future__ import annotations

import logging
from typing import Any, Optional

from pydantic import BaseModel, ConfigDict

from src.ontology.capability_types import Capability, CapabilityEvidence

log = logging.getLogger(__name__)


# ── Configuration Model ───────────────────────────────────────────


class CapabilityKeywordConfig(BaseModel):
    """Configuration for a single capability's keyword mapping rules."""

    model_config = ConfigDict(extra="forbid", strict=True)

    capability_name: str
    keywords: list[str]
    source_types: list[str] = ["connector", "chat"]
    confidence_boost: float = 0.1
    min_keyword_matches: int = 1


class CapabilityMappingConfig(BaseModel):
    """Configuration for the capability mapping engine."""

    model_config = ConfigDict(extra="forbid", strict=True)

    capabilities: list[CapabilityKeywordConfig] = []
    llm_confidence_threshold: float = 0.7
    max_mappings_per_evidence: int = 3
    enable_llm_fallback: bool = True


# ── Default Keyword Configurations ────────────────────────────────

DEFAULT_KEYWORD_CONFIGS: list[CapabilityKeywordConfig] = [
    # Sales domain
    CapabilityKeywordConfig(
        capability_name="Lead Qualification",
        keywords=["lead", "qualification", "scoring", "routing", "mql", "sql", "lead score"],
        source_types=["connector", "chat"],
    ),
    CapabilityKeywordConfig(
        capability_name="Proposal Generation",
        keywords=["proposal", "quote", "rfp", "bid", "pricing", "proposal template"],
        source_types=["connector", "chat"],
    ),
    CapabilityKeywordConfig(
        capability_name="Negotiation",
        keywords=["negotiation", "discount", "contract", "terms", "haggle", "concession"],
        source_types=["connector", "chat"],
    ),
    CapabilityKeywordConfig(
        capability_name="Close Deal",
        keywords=["close", "deal", "signature", "legal review", "onboarding", "handoff"],
        source_types=["connector", "chat", "api"],
    ),
    # Engineering domain
    CapabilityKeywordConfig(
        capability_name="CI/CD Pipeline",
        keywords=["ci/cd", "pipeline", "build", "deploy", "deployment", "github actions", "gitlab ci", "jenkins"],
        source_types=["connector", "chat"],
    ),
    CapabilityKeywordConfig(
        capability_name="Code Review",
        keywords=["code review", "pull request", "pr review", "review process", "approve", "merge"],
        source_types=["connector", "chat"],
    ),
    CapabilityKeywordConfig(
        capability_name="Monitoring",
        keywords=["monitoring", "alerting", "dashboard", "observability", "prometheus", "grafana", "incident"],
        source_types=["connector", "chat"],
    ),
    CapabilityKeywordConfig(
        capability_name="Technical Debt Management",
        keywords=["tech debt", "technical debt", "refactor", "cleanup", "legacy", "migration"],
        source_types=["connector", "chat"],
    ),
    # Finance domain
    CapabilityKeywordConfig(
        capability_name="Revenue Recognition",
        keywords=["revenue", "mrr", "arr", "billing", "invoice", "payment", "receivable"],
        source_types=["connector", "spreadsheet"],
    ),
    CapabilityKeywordConfig(
        capability_name="Expense Management",
        keywords=["expense", "cost", "spend", "budget", "procurement", "vendor"],
        source_types=["connector", "spreadsheet"],
    ),
    CapabilityKeywordConfig(
        capability_name="Financial Reporting",
        keywords=["report", "financial report", "p&l", "balance sheet", "cash flow", "forecast"],
        source_types=["connector", "spreadsheet"],
    ),
    # People domain
    CapabilityKeywordConfig(
        capability_name="Hiring",
        keywords=["hiring", "recruit", "candidate", "interview", "offer", "job posting"],
        source_types=["connector", "chat"],
    ),
    CapabilityKeywordConfig(
        capability_name="Onboarding",
        keywords=["onboarding", "new hire", "orientation", "training", "ramp", "30-60-90"],
        source_types=["connector", "chat"],
    ),
    CapabilityKeywordConfig(
        capability_name="Performance Management",
        keywords=["performance", "review", "okr", "goal", "feedback", "1:1", "one-on-one"],
        source_types=["connector", "chat"],
    ),
    # Product domain
    CapabilityKeywordConfig(
        capability_name="Product Discovery",
        keywords=["discovery", "user research", "interview", "survey", "pain point", "need"],
        source_types=["connector", "chat"],
    ),
    CapabilityKeywordConfig(
        capability_name="Feature Delivery",
        keywords=["feature", "sprint", "story", "backlog", "release", "launch", "ship"],
        source_types=["connector", "chat"],
    ),
]


# ── Mapping Engine ────────────────────────────────────────────────


class CapabilityMapper:
    """Maps evidence records to capabilities using 3-tier strategy.

    Tier 1: Keyword matching (deterministic, fast)
    Tier 2: LLM classification (augmented, for ambiguous cases)
    Tier 3: Manual tagging (HITL, highest confidence)
    """

    def __init__(self, config: CapabilityMappingConfig | None = None):
        self.config = config or CapabilityMappingConfig(
            capabilities=DEFAULT_KEYWORD_CONFIGS,
        )
        self._keyword_index = self._build_keyword_index()

    def _build_keyword_index(self) -> dict[str, list[CapabilityKeywordConfig]]:
        """Build reverse index: keyword → list of capability configs."""
        index: dict[str, list[CapabilityKeywordConfig]] = {}
        for cap_config in self.config.capabilities:
            for keyword in cap_config.keywords:
                key = keyword.lower()
                if key not in index:
                    index[key] = []
                index[key].append(cap_config)
        return index

    def map_evidence_to_capabilities(
        self,
        evidence_record: dict[str, Any],
        existing_capabilities: list[Capability],
    ) -> list[CapabilityEvidence]:
        """Map an evidence record to capabilities using 3-tier strategy.

        Args:
            evidence_record: The evidence record to map.
            existing_capabilities: List of existing capabilities to map against.

        Returns:
            List of CapabilityEvidence links (possibly empty).
        """
        mappings: list[CapabilityEvidence] = []

        # Tier 1: Keyword matching
        keyword_mappings = self._tier1_keyword_match(evidence_record, existing_capabilities)
        mappings.extend(keyword_mappings)

        # If we got clear results (≥2 matches with high confidence), stop here
        high_confidence = [m for m in mappings if m.relevance_score >= 0.8]
        if len(high_confidence) >= 2:
            return mappings[: self.config.max_mappings_per_evidence]

        # If no keyword matches and LLM is enabled, use Tier 2
        if not mappings and self.config.enable_llm_fallback:
            llm_mappings = self._tier2_llm_classify(evidence_record, existing_capabilities)
            mappings.extend(llm_mappings)

        # Cap at max_mappings_per_evidence
        return sorted(mappings, key=lambda m: m.relevance_score, reverse=True)[
            : self.config.max_mappings_per_evidence
        ]

    def _tier1_keyword_match(
        self,
        evidence_record: dict[str, Any],
        existing_capabilities: list[Capability],
    ) -> list[CapabilityEvidence]:
        """Tier 1: Keyword matching (deterministic).

        Matches evidence structured_data and raw_content against capability keywords.
        """
        mappings: list[CapabilityEvidence] = []

        # Extract text from evidence
        structured = evidence_record.get("structured_data", {})
        raw_content = evidence_record.get("raw_content", "") or ""
        source_type = evidence_record.get("source_type", "")

        # Combine all text for matching
        all_text = self._extract_all_text(structured, raw_content)
        all_text_lower = all_text.lower()

        # Match against keywords
        matched_capabilities: dict[str, float] = {}

        for keyword, cap_configs in self._keyword_index.items():
            if keyword in all_text_lower:
                for cap_config in cap_configs:
                    # Check source_type filter
                    if source_type and cap_config.source_types and source_type not in cap_config.source_types:
                        continue

                    # Count keyword occurrences
                    count = all_text_lower.count(keyword)
                    # Normalize by text length (longer text = more expected matches)
                    text_len = max(len(all_text_lower.split()), 1)
                    match_ratio = min(count / max(text_len * 0.02, 1), 1.0)

                    # Compute relevance score
                    relevance = match_ratio * (1.0 + cap_config.confidence_boost)

                    # Find matching capability in existing capabilities
                    for cap in existing_capabilities:
                        if cap.name.lower() == cap_config.capability_name.lower():
                            if cap.id not in matched_capabilities or relevance > matched_capabilities[cap.id]:
                                matched_capabilities[cap.id] = relevance
                            break

        # Build CapabilityEvidence links
        evidence_id = evidence_record.get("id", "")
        for cap_id, relevance in matched_capabilities.items():
            mappings.append(
                CapabilityEvidence(
                    evidence_id=evidence_id,
                    capability_id=cap_id,
                    relevance_score=min(relevance, 1.0),
                    mapping_method="keyword",
                    mapped_by="system",
                )
            )

        return mappings

    def _tier2_llm_classify(
        self,
        evidence_record: dict[str, Any],
        existing_capabilities: list[Capability],
    ) -> list[CapabilityEvidence]:
        """Tier 2: LLM classification (augmented).

        This is a placeholder for LLM-based classification. In production,
        this would call the Shared Platform Agent with a classification prompt.

        For now, returns empty — the LLM integration point is defined here
        but the actual call is implemented in the pipeline agent layer.
        """
        # LLM classification is implemented in the pipeline agent layer
        # (Stage 6 agent activity). This method defines the interface.
        log.debug(
            "Tier 2 LLM classification requested for evidence %s — "
            "delegating to pipeline agent",
            evidence_record.get("id", "?"),
        )
        return []

    def _extract_all_text(self, structured: dict, raw_content: str) -> str:
        """Extract all searchable text from an evidence record."""
        parts = [raw_content]

        for value in structured.values():
            if isinstance(value, str):
                parts.append(value)
            elif isinstance(value, list):
                for item in value:
                    if isinstance(item, str):
                        parts.append(item)
                    elif isinstance(item, dict):
                        for v in item.values():
                            if isinstance(v, str):
                                parts.append(v)

        return " ".join(parts)

    def add_capability_keywords(
        self,
        capability_name: str,
        keywords: list[str],
        source_types: list[str] | None = None,
    ) -> None:
        """Dynamically add keywords for a capability (for custom capabilities)."""
        config = CapabilityKeywordConfig(
            capability_name=capability_name,
            keywords=keywords,
            source_types=source_types or ["connector", "chat"],
        )
        self.config.capabilities.append(config)

        # Update reverse index
        for keyword in keywords:
            key = keyword.lower()
            if key not in self._keyword_index:
                self._keyword_index[key] = []
            self._keyword_index[key].append(config)

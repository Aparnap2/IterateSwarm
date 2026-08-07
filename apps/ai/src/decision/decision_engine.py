"""V6 OntologyAI — Decision Context Runtime.

Per §5 of the V6 spec, the Decision Context Runtime is responsible for:

1.  Creating decisions with linked evidence
2.  Generating exactly two options per decision (rule-based for M0.5)
3.  Analysing trade-offs between options across cost, time, quality, risk

For M0.5 the runtime is entirely deterministic — no LLM calls.  Data may be
stored in-memory (dicts) when Neo4j / PostgreSQL are unavailable.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

from src.entities.models import Decision, EvidenceRecord, Option, TradeOff

logger = logging.getLogger(__name__)


# ── Exceptions ──────────────────────────────────────────────────────────


class DecisionEngineError(Exception):
    """Base exception for decision-runtime failures."""


class ValidationError(DecisionEngineError):
    """Raised when a decision or option fails validation."""


# ── In-memory stores (fallback when Neo4j / Postgres unavailable) ───────


_IN_MEMORY_DECISIONS: dict[str, Decision] = {}
_IN_MEMORY_OPTIONS: dict[str, list[Option]] = {}
_IN_MEMORY_TRADEOFFS: dict[str, list[TradeOff]] = {}


def _utcnow() -> datetime:
    """Return the current UTC datetime (offset-aware)."""
    return datetime.now(timezone.utc)


# ── OptionGenerator — rule-based option creation for M0.5 ───────────────


class OptionGenerator:
    """Deterministic, rule-based option generator for M0.5.

    For each decision, exactly two options are generated:

    *   **Option A** — the *preferred* approach, derived from evidence
        recommendations (higher average sentiment / confidence).
    *   **Option B** — the *alternative* or status-quo approach.

    When evidence is sparse or neutral, Option A defaults to a "Proceed
    with recommended approach" and Option B to "Maintain current state".
    """

    def __init__(self) -> None:
        self._counter = 0

    def _next_id(self) -> str:
        self._counter += 1
        return f"opt-m0.5-{self._counter:04d}"

    def generate(
        self,
        decision_id: str,
        evidence_context: list[EvidenceRecord],
        *,
        tenant_id: str = "m0.5-tenant",
    ) -> tuple[Option, Option]:
        """Generate exactly two options for *decision_id*.

        Parameters
        ----------
        decision_id:
            The ULID of the owning Decision.
        evidence_context:
            Evidence records linked to this decision.
        tenant_id:
            Tenant scoping (defaults to a fixed M0.5 value).

        Returns
        -------
        tuple[Option, Option]
            ``(option_a, option_b)`` — the preferred and alternative options.
        """
        # Compute a simple signal from the evidence
        avg_confidence = self._average_confidence(evidence_context)
        positive_ratio = self._positive_sentiment_ratio(evidence_context)
        recommendation_score = avg_confidence * positive_ratio

        # ── Option A: preferred ──────────────────────────────────────
        if recommendation_score >= 0.5 and evidence_context:
            a_title = "Proceed with recommended approach"
            a_desc = self._build_preferred_description(evidence_context)
        else:
            a_title = "Proceed with evidence-informed approach"
            a_desc = (
                "Evidence is neutral or mixed. Proceed with a phased "
                "approach, monitoring key indicators before full commitment."
            )

        option_a = Option(
            id=self._next_id(),
            tenant_id=tenant_id,
            decision_id=decision_id,
            title=a_title,
            description=a_desc,
            status="proposed",
            feasibility_score=None,
        )

        # ── Option B: alternative / status quo ───────────────────────
        option_b = Option(
            id=self._next_id(),
            tenant_id=tenant_id,
            decision_id=decision_id,
            title="Maintain current state / status quo",
            description=(
                "Continue with existing processes and systems without "
                "adopting the proposed change. Accept current limitations "
                "and revisit when new evidence emerges."
            ),
            status="proposed",
            feasibility_score=None,
        )

        logger.info(
            "Generated options for decision %s: A=%s B=%s (score=%.2f)",
            decision_id,
            option_a.id,
            option_b.id,
            recommendation_score,
        )

        return option_a, option_b

    # ── Helpers ──────────────────────────────────────────────────────

    @staticmethod
    def _average_confidence(records: list[EvidenceRecord]) -> float:
        if not records:
            return 0.0
        return sum(r.confidence for r in records) / len(records)

    @staticmethod
    def _positive_sentiment_ratio(records: list[EvidenceRecord]) -> float:
        """Crude heuristic: count records with confidence >= 0.7 as positive."""
        if not records:
            return 0.0
        positive = sum(1 for r in records if r.confidence >= 0.7)
        return positive / len(records)

    @staticmethod
    def _build_preferred_description(records: list[EvidenceRecord]) -> str:
        """Build a human-readable description from evidence sources."""
        sources = sorted({r.source for r in records if r.source})
        if not sources:
            return (
                "Proceed with the approach supported by available evidence. "
                "Multiple indicators favour action."
            )
        source_list = ", ".join(sources[:5])
        return (
            f"Proceed with the approach recommended by evidence from: "
            f"{source_list}. Confidence in the recommendation is supported "
            f"by {len(records)} evidence record{'s' if len(records) != 1 else ''}."
        )


# ── TradeOffAnalyzer — deterministic trade-off analysis ─────────────────


_TRADE_OFF_DIMENSIONS = ["cost", "time", "quality", "risk"]


class TradeOffAnalyzer:
    """Compares two options across canonical trade-off dimensions.

    For M0.5 dimension scores are derived from evidence confidence averages.
    Each dimension produces a ``TradeOff`` entry.
    """

    def __init__(self) -> None:
        self._counter = 0

    def _next_id(self) -> str:
        self._counter += 1
        return f"to-m0.5-{self._counter:04d}"

    def analyze(
        self,
        option_a: Option,
        option_b: Option,
        evidence_context: list[EvidenceRecord] | None = None,
    ) -> list[TradeOff]:
        """Compare two options across all canonical dimensions.

        Parameters
        ----------
        option_a:
            The preferred option (Option A).
        option_b:
            The alternative option (Option B).
        evidence_context:
            Optional evidence records — used to inform dimension scores.

        Returns
        -------
        list[TradeOff]
            One ``TradeOff`` entry per dimension.
        """
        base = self._evidence_quality_score(evidence_context or [])
        trade_offs: list[TradeOff] = []

        for dim in _TRADE_OFF_DIMENSIONS:
            a_score, b_score = self._compute_dimension(dim, base)
            trade_offs.append(
                TradeOff(
                    id=self._next_id(),
                    option_a_id=option_a.id,
                    option_b_id=option_b.id,
                    dimension=dim,
                    a_score=round(a_score, 1),
                    b_score=round(b_score, 1),
                    delta=round(a_score - b_score, 1),
                    narrative=self._narrative_for(dim, a_score, b_score),
                )
            )

        return trade_offs

    # ── Dimension scoring ────────────────────────────────────────────

    @staticmethod
    def _evidence_quality_score(records: list[EvidenceRecord]) -> float:
        """Normalised [0, 100] quality score from evidence."""
        if not records:
            return 50.0  # neutral baseline
        raw = sum(r.confidence * 100 for r in records) / len(records)
        return max(0.0, min(100.0, raw))

    @staticmethod
    def _compute_dimension(dimension: str, base: float) -> tuple[float, float]:
        """Return ``(a_score, b_score)`` for *dimension*.

        Logic:
        - cost:      A is typically higher (investment), B lower (status quo).
        - time:      A is higher (new initiative takes time), B lower.
        - quality:   A is higher (improvement expected), B baseline.
        - risk:      A is more uncertain, B is known-quantity.
        """
        if dimension == "cost":
            # Option A incurs cost; Option B keeps current spend
            return (min(base * 0.7, 80.0), min(base * 0.3, 40.0))
        if dimension == "time":
            # Option A requires implementation time; B is already running
            return (min(base * 0.5, 60.0), min(base * 0.8, 90.0))
        if dimension == "quality":
            # Option A aims to improve; B maintains current level
            return (min(base * 0.9, 85.0), min(base * 0.5, 55.0))
        if dimension == "risk":
            # Option A introduces uncertainty (inverted: lower = riskier);
            # B is a known quantity
            return (min(base * 0.4, 50.0), min(base * 0.85, 80.0))
        return (base, base)  # fallback

    @staticmethod
    def _narrative_for(dimension: str, a: float, b: float) -> str:
        """Short human-readable description of the trade-off."""
        if dimension == "cost":
            return (
                f"Option A scores {a:.0f}/100 (investment required) vs "
                f"Option B at {b:.0f}/100 (existing spend)."
            )
        if dimension == "time":
            return (
                f"Option A scores {a:.0f}/100 (implementation timeline) vs "
                f"Option B at {b:.0f}/100 (already operational)."
            )
        if dimension == "quality":
            return (
                f"Option A scores {a:.0f}/100 (expected improvement) vs "
                f"Option B at {b:.0f}/100 (current state)."
            )
        if dimension == "risk":
            return (
                f"Option A scores {a:.0f}/100 (new initiative uncertainty) vs "
                f"Option B at {b:.0f}/100 (known-quantity risk profile)."
            )
        return ""


# ── DecisionEngine — public API (Decision Context Runtime) ──────


class DecisionEngine:
    """Creates decisions, generates options, and analyses trade-offs.

    For M0.5: deterministic rule-based option generation from evidence.
    Data is stored in memory (dict fallback) when Neo4j / Postgres are not
    available.

    Note: Class name retains "Engine" for backward compatibility; the
    architectural concept is now the Decision Context Runtime.
    """

    def __init__(
        self,
        neo4j_client: Any = None,
        db_pool: Any = None,
    ) -> None:
        """Initialise the engine.

        Parameters
        ----------
        neo4j_client:
            Optional Neo4j client for graph persistence.  If ``None`` the
            engine uses in-memory dicts.
        db_pool:
            Optional asyncpg-compatible pool for relational persistence.
        """
        self._neo4j = neo4j_client
        self._db_pool = db_pool
        self._option_gen = OptionGenerator()
        self._tradeoff_analyzer = TradeOffAnalyzer()
        self._decision_counter = 0

    def _is_persistent(self) -> bool:
        """Return ``True`` if we have a persistent backend available."""
        return self._neo4j is not None and self._db_pool is not None

    def _next_decision_id(self) -> str:
        self._decision_counter += 1
        return f"dec-m0.5-{self._decision_counter:04d}"

    # ── Create Decision ──────────────────────────────────────────────

    async def create_decision(
        self,
        workspace_id: str,
        title: str,
        description: str,
        owner_id: str | None = None,
        evidence_ids: list[str] | None = None,
    ) -> Decision:
        """Create a new decision with linked evidence.

        Decision status starts as ``"draft"``.
        At least one evidence record must be linked (validated).

        Parameters
        ----------
        workspace_id:
            The workspace ULID the decision belongs to.
        title:
            Decision title (max 200 chars).
        description:
            Decision description (max 5000 chars).
        owner_id:
            Optional stakeholder ULID who owns the decision.
        evidence_ids:
            ULIDs of evidence records backing this decision.  Must contain
            at least one element.

        Returns
        -------
        Decision
            The newly created decision with status ``"draft"``.

        Raises
        ------
        ValidationError
            If *evidence_ids* is empty or *title* is empty.
        """
        title = title.strip()
        if not title:
            raise ValidationError("Decision title must not be empty.")
        if len(title) > 200:
            raise ValidationError(
                f"Decision title exceeds 200 characters ({len(title)})."
            )
        if not evidence_ids:
            raise ValidationError(
                "A decision must link to at least one evidence record (V001). "
                "Provide at least one evidence_id."
            )

        decision = Decision(
            id=self._next_decision_id(),
            tenant_id="m0.5-tenant",
            workspace_id=workspace_id,
            title=title,
            description=description.strip(),
            owner_id=owner_id or "stakeholder-m0.5-unknown",
            status="draft",
            created_at=_utcnow(),
            approved_at=None,
        )

        if self._is_persistent():
            # TODO — persist to Neo4j + Postgres in later milestone
            logger.info(
                "Persistent backend detected — would persist decision %s",
                decision.id,
            )
        else:
            _IN_MEMORY_DECISIONS[decision.id] = decision
            logger.info("Stored decision %s in memory (no backend).", decision.id)

        return decision

    # ── Generate Options ─────────────────────────────────────────────

    async def generate_options(
        self,
        decision_id: str,
        evidence_context: list[EvidenceRecord],
    ) -> tuple[Option, Option]:
        """Generate exactly two options for *decision_id*.

        Parameters
        ----------
        decision_id:
            The decision ULID the options should belong to.
        evidence_context:
            Evidence records to derive option recommendations from.

        Returns
        -------
        tuple[Option, Option]
            ``(option_a, option_b)``.

        Raises
        ------
        DecisionEngineError
            If *decision_id* does not exist.
        """
        decision = await self.get_decision(decision_id)
        if decision is None:
            raise DecisionEngineError(f"Decision {decision_id} not found.")

        opt_a, opt_b = self._option_gen.generate(decision_id, evidence_context)

        # Store in memory
        opts = _IN_MEMORY_OPTIONS.setdefault(decision_id, [])
        opts.extend([opt_a, opt_b])

        return opt_a, opt_b

    # ── Analyse Trade-Offs ───────────────────────────────────────────

    async def analyze_tradeoffs(
        self,
        option_a: Option,
        option_b: Option,
        evidence_context: list[EvidenceRecord] | None = None,
    ) -> list[TradeOff]:
        """Compare two options across relevant dimensions.

        Generates ``TradeOff`` entries for each dimension where options
        differ.  Returns at least: cost, time, quality, risk trade-offs.

        Parameters
        ----------
        option_a:
            The preferred option.
        option_b:
            The alternative option.
        evidence_context:
            Optional evidence records to inform scoring.

        Returns
        -------
        list[TradeOff]
            One entry per dimension.
        """
        trade_offs = self._tradeoff_analyzer.analyze(
            option_a, option_b, evidence_context
        )

        # Store in memory
        key = f"{option_a.decision_id}"
        existing = _IN_MEMORY_TRADEOFFS.setdefault(key, [])
        existing.extend(trade_offs)

        return trade_offs

    # ── Retrieve Decision ────────────────────────────────────────────

    async def get_decision(self, decision_id: str) -> Decision | None:
        """Retrieve a decision by ID.

        Parameters
        ----------
        decision_id:
            The ULID of the decision to retrieve.

        Returns
        -------
        Decision | None
            The decision if found, else ``None``.
        """
        if self._is_persistent():
            # TODO — query Neo4j / Postgres
            pass
        return _IN_MEMORY_DECISIONS.get(decision_id)

    # ── Retrieve Options ─────────────────────────────────────────────

    async def get_options(self, decision_id: str) -> list[Option]:
        """Retrieve all options for a decision.

        Parameters
        ----------
        decision_id:
            The decision ULID.

        Returns
        -------
        list[Option]
            Options belonging to the decision, or empty list.
        """
        return _IN_MEMORY_OPTIONS.get(decision_id, [])

    # ── Retrieve Trade-Offs ──────────────────────────────────────────

    async def get_tradeoffs(self, decision_id: str) -> list[TradeOff]:
        """Retrieve all trade-offs for a decision's options.

        Parameters
        ----------
        decision_id:
            The decision ULID.

        Returns
        -------
        list[TradeOff]
            Trade-off entries, or empty list.
        """
        return _IN_MEMORY_TRADEOFFS.get(decision_id, [])

    # ── Approve Decision ─────────────────────────────────────────────

    async def approve_decision(self, decision_id: str) -> Decision:
        """Transition a decision from ``"draft"``/``"assessing"`` to ``"approved"``.

        Parameters
        ----------
        decision_id:
            The decision ULID.

        Returns
        -------
        Decision
            The updated decision.

        Raises
        ------
        DecisionEngineError
            If the decision does not exist or is already superseded.
        """
        decision = await self.get_decision(decision_id)
        if decision is None:
            raise DecisionEngineError(f"Cannot approve — decision {decision_id} not found.")
        if decision.status == "superseded":
            raise DecisionEngineError(
                f"Cannot approve — decision {decision_id} is superseded."
            )

        decision.status = "approved"
        decision.approved_at = _utcnow()

        if self._is_persistent():
            logger.info("Would persist approval of %s to backend.", decision_id)
        else:
            _IN_MEMORY_DECISIONS[decision_id] = decision

        return decision

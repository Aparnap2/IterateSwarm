"""Replay tests for V6 vertical slice.

Verifies that the pipeline is deterministic: same input → same output.
For a Temporal-based system, deterministic replay is a required
architectural property. If replay changes output, there is nondeterminism.
"""

from __future__ import annotations

import pytest

from src.pipeline.vertical_slice import VerticalSlicePipeline


def _serialize_result(result: dict) -> dict:
    """Extract only deterministic fields for comparison.

    Excludes items that vary on every run (timestamps, generated ULIDs).
    Includes structural properties that must be invariant across replays.
    """
    return {
        "evidence_count": len(result.get("evidence_ids", [])),
        "entity_count": len(result.get("entities", [])),
        "entity_types": sorted(
            e.get("entity_type", "") for e in result.get("entities", [])
        ),
        "entity_confidences": sorted(
            round(e.get("confidence", 0), 2) for e in result.get("entities", [])
        ),
        "decision_options": result.get("decision", {}).get("option_count", 0),
        "feasibility_tiers": sorted(
            s.get("readiness_tier", "") for s in result.get("feasibility", [])
        ),
        "feasibility_totals": sorted(
            round(s.get("weighted_total", 0), 1)
            for s in result.get("feasibility", [])
        ),
        "artifact_section_count": result.get("artifact", {}).get("section_count", 0),
        "validation_passed": result.get("validation", {}).get("passed", False),
        "validation_rule_count": result.get("validation", {}).get("rules_checked", 0),
        "workspace_id": result.get("workspace_id", ""),
        "status": result.get("status", ""),
    }


@pytest.mark.asyncio
class TestReplayDeterminism:
    """Critical: Pipeline must produce identical output on replay.

    For a Temporal-based system, deterministic replay is a required
    architectural property. If replay changes output, there is nondeterminism
    in the pipeline stages.
    """

    async def test_replay_produces_identical_output(self):
        """Run pipeline twice — both runs must produce identical results."""
        # Use separate pipeline instances to avoid stage_results accumulation
        pipeline1 = VerticalSlicePipeline()
        pipeline2 = VerticalSlicePipeline()

        # Run 1
        result1 = await pipeline1.run()
        serialized1 = _serialize_result(result1)

        # Run 2
        result2 = await pipeline2.run()
        serialized2 = _serialize_result(result2)

        assert serialized1 == serialized2, (
            f"Replay produced different results!\n"
            f"Run 1: {serialized1}\n"
            f"Run 2: {serialized2}\n"
            "This indicates nondeterminism in the pipeline."
        )

    async def test_replay_three_times_identical(self):
        """Three runs must all produce identical results (stability test)."""
        # Use separate pipeline instances to avoid stage_results accumulation
        pipelines = [VerticalSlicePipeline() for _ in range(3)]
        results = [await p.run() for p in pipelines]
        serialized = [_serialize_result(r) for r in results]

        assert serialized[0] == serialized[1] == serialized[2], (
            "Pipeline is nondeterministic across 3 runs"
        )

    async def test_entity_counts_are_consistent(self):
        """Entity counts and types should be the same across runs."""
        pipeline1 = VerticalSlicePipeline()
        pipeline2 = VerticalSlicePipeline()

        result1 = await pipeline1.run()
        result2 = await pipeline2.run()

        names1 = sorted(
            e.get("properties", {}).get("name", "")
            for e in result1.get("entities", [])
        )
        names2 = sorted(
            e.get("properties", {}).get("name", "")
            for e in result2.get("entities", [])
        )
        assert names1 == names2, "Entity names differ across runs"

        types1 = sorted(e.get("entity_type", "") for e in result1.get("entities", []))
        types2 = sorted(e.get("entity_type", "") for e in result2.get("entities", []))
        assert types1 == types2, "Entity types differ across runs"

    async def test_stage_order_is_consistent(self):
        """All 10 stages execute in the same order every time."""
        pipeline1 = VerticalSlicePipeline()
        pipeline2 = VerticalSlicePipeline()

        result1 = await pipeline1.run()
        result2 = await pipeline2.run()

        stages1 = [s["name"] for s in result1["stage_results"]]
        stages2 = [s["name"] for s in result2["stage_results"]]
        assert stages1 == stages2, "Stage execution order differs across runs"

    async def test_stage_success_consistent(self):
        """Stage pass/fail status must be identical across runs."""
        pipeline1 = VerticalSlicePipeline()
        pipeline2 = VerticalSlicePipeline()

        result1 = await pipeline1.run()
        result2 = await pipeline2.run()

        status1 = [(s["name"], s["success"]) for s in result1["stage_results"]]
        status2 = [(s["name"], s["success"]) for s in result2["stage_results"]]
        assert status1 == status2, "Stage success status differs across runs"

    async def test_entity_confidence_identical(self):
        """Confidence values for entities must be identical across runs."""
        pipeline1 = VerticalSlicePipeline()
        pipeline2 = VerticalSlicePipeline()

        result1 = await pipeline1.run()
        result2 = await pipeline2.run()

        confs1 = sorted(
            (e.get("entity_type", ""), round(e.get("confidence", 0), 4))
            for e in result1["entities"]
        )
        confs2 = sorted(
            (e.get("entity_type", ""), round(e.get("confidence", 0), 4))
            for e in result2["entities"]
        )
        assert confs1 == confs2, "Entity confidence values differ across runs"

    async def test_decision_title_consistent(self):
        """Decision title must be identical across runs."""
        pipeline1 = VerticalSlicePipeline()
        pipeline2 = VerticalSlicePipeline()

        result1 = await pipeline1.run()
        result2 = await pipeline2.run()

        assert (
            result1["decision"]["title"] == result2["decision"]["title"]
        ), "Decision title differs across runs"
        assert (
            result1["decision"]["option_count"]
            == result2["decision"]["option_count"]
        ), "Decision option count differs across runs"

    async def test_feasibility_scores_consistent(self):
        """Feasibility scores and tiers must be identical across runs."""
        pipeline1 = VerticalSlicePipeline()
        pipeline2 = VerticalSlicePipeline()

        result1 = await pipeline1.run()
        result2 = await pipeline2.run()

        tiers1 = sorted(
            (s.get("option_title", ""), s.get("readiness_tier", ""))
            for s in result1["feasibility"]
        )
        tiers2 = sorted(
            (s.get("option_title", ""), s.get("readiness_tier", ""))
            for s in result2["feasibility"]
        )
        assert tiers1 == tiers2, "Feasibility tiers differ across runs"

        totals1 = sorted(
            (s.get("option_title", ""), round(s.get("weighted_total", 0), 1))
            for s in result1["feasibility"]
        )
        totals2 = sorted(
            (s.get("option_title", ""), round(s.get("weighted_total", 0), 1))
            for s in result2["feasibility"]
        )
        assert totals1 == totals2, "Feasibility weighted totals differ across runs"

    async def test_validation_consistency(self):
        """Validation result must be identical across runs."""
        pipeline1 = VerticalSlicePipeline()
        pipeline2 = VerticalSlicePipeline()

        result1 = await pipeline1.run()
        result2 = await pipeline2.run()

        v1 = result1["validation"]
        v2 = result2["validation"]
        assert v1["passed"] == v2["passed"]
        assert v1["rules_checked"] == v2["rules_checked"]
        assert v1["warnings"] == v2["warnings"]
        assert v1["blocking_issues"] == v2["blocking_issues"]

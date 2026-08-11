"""
OntologyAI Temporal Worker — V5.2 Canonical Names.

Default active roster is EXACTLY 6 V5.2 workflows:
    ChiefOfStaffWorkflow, DiscoveryWorkflow, OntologyMappingWorkflow,
    KnowledgeValidationWorkflow, SolutionArchitectWorkflow, GovernanceWorkflow

V6 StrategyWorkflow is gated behind ``ENABLE_V6_WORKFLOWS=on``.
Legacy V4.1 workflows are gated behind ``LEGACY_FDE_MODULES=on``.

Task queue: ONTOLOGYAI-MAIN-QUEUE (env-overridable, legacy fallback)
"""
from __future__ import annotations

import asyncio
import logging
import os
from collections.abc import Callable

from temporalio.client import Client
from temporalio.worker import Worker

from src.orchestration.queue import ONTOLOGYAI_MAIN_QUEUE, resolve_task_queue
from src.integrations import legacy_integrations_enabled

# ── V5.2 canonical workflow imports (always importable) ─────────────────
from src.workflows.chief_of_staff_workflow import ChiefOfStaffWorkflow
from src.workflows.discovery_workflow import DiscoveryWorkflow
from src.workflows.ontology_mapping_workflow import OntologyMappingWorkflow
from src.workflows.knowledge_validation_workflow import KnowledgeValidationWorkflow
from src.workflows.solution_architect_workflow import SolutionArchitectWorkflow
from src.workflows.governance_workflow import GovernanceWorkflow

# ── Always-included activity imports ────────────────────────────────────
from src.activities.send_slack_message import send_slack_message
from src.activities.run_guardian_watchlist import run_guardian_watchlist
from src.activities.compile_n8n_workflow import compile_n8n_workflow
from src.activities.memory_maintenance import decay_memory_weights, expire_old_memories, optimize_memory_performance

log = logging.getLogger("ontology_ai.worker")

# ── Legacy V5.2 integration gate ─────────────────────────────────────
# The V6 worker path must NOT import the 5 legacy V5.2 integrations
# (stripe, plaid, erpnext, hubspot, quickbooks) by default. They are gated
# behind LEGACY_INTEGRATIONS=1 and emit a deprecation warning when enabled.
if legacy_integrations_enabled():
    log.warning(
        "DEPRECATION: legacy V5.2 integrations (stripe, plaid, erpnext, hubspot, quickbooks) "
        "enabled via LEGACY_INTEGRATIONS=1. The V6 worker path runs without them by default."
    )
else:
    log.info(
        "V6 worker path running WITHOUT legacy V5.2 integrations "
        "(stripe, plaid, erpnext, hubspot, quickbooks). "
        "Set LEGACY_INTEGRATIONS=1 to re-enable."
    )

TEMPORAL_HOST = os.getenv("TEMPORAL_HOST", "localhost:7233")
TASK_QUEUE = resolve_task_queue()
MAX_CONCURRENT = int(os.getenv("WORKER_MAX_CONCURRENT_ACTIVITIES", "10"))


def _build_workflow_list() -> list[type]:
    """Build the registered workflow list based on env flags.

    Default: exactly 6 V5.2 canonical workflows.
    V6 (+StrategyWorkflow) added when ``ENABLE_V6_WORKFLOWS=on``.
    Legacy V4.1 workflows added when ``LEGACY_FDE_MODULES=on``.
    """
    workflows: list[type] = [
        ChiefOfStaffWorkflow,
        DiscoveryWorkflow,
        OntologyMappingWorkflow,
        KnowledgeValidationWorkflow,
        SolutionArchitectWorkflow,
        GovernanceWorkflow,
    ]

    if os.getenv("ENABLE_V6_WORKFLOWS") == "on":
        from src.workflows.strategy_workflow import StrategyWorkflow
        workflows.append(StrategyWorkflow)

    if os.getenv("LEGACY_FDE_MODULES") == "on":
        from src.workflows.pulse_workflow import PulseWorkflow
        from src.workflows.investor_workflow import InvestorWorkflow
        from src.workflows.self_analysis_workflow import SelfAnalysisWorkflow
        from src.workflows.eval_loop_workflow import EvalLoopWorkflow
        from src.workflows.compression_workflow import CompressionWorkflow
        from src.workflows.weight_decay_workflow import WeightDecayWorkflow
        from src.workflows.memory_maintenance_workflow import MemoryMaintenanceWorkflow
        from src.workflows.fpa_workflow import FPAWorkflow
        from src.workflows.growth_analytics_workflow import GrowthAnalyticsWorkflow
        from src.workflows.reliability_workflow import ReliabilityWorkflow
        from src.workflows.comms_workflow import CommsWorkflow
        workflows.extend([
            PulseWorkflow,
            InvestorWorkflow,
            SelfAnalysisWorkflow,
            EvalLoopWorkflow,
            CompressionWorkflow,
            WeightDecayWorkflow,
            MemoryMaintenanceWorkflow,
            FPAWorkflow,
            GrowthAnalyticsWorkflow,
            ReliabilityWorkflow,
            CommsWorkflow,
        ])

    return workflows


def _build_activity_list() -> list[Callable]:
    """Build the registered activity list based on env flags.

    Always includes: send_slack_message, run_guardian_watchlist,
    compile_n8n_workflow, decay_memory_weights, expire_old_memories,
    optimize_memory_performance.

    Legacy V4.1 activities added when ``LEGACY_FDE_MODULES=on``.
    """
    activities: list[Callable] = [
        send_slack_message,
        run_guardian_watchlist,
        compile_n8n_workflow,
        decay_memory_weights,
        expire_old_memories,
        optimize_memory_performance,
    ]

    if os.getenv("LEGACY_FDE_MODULES") == "on":
        from src.activities.run_pulse_agent import run_pulse_agent
        from src.activities.run_anomaly_agent import run_anomaly_agent
        from src.activities.run_investor_agent import run_investor_agent
        from src.activities.run_qa_agent import run_qa_agent
        activities.extend([
            run_pulse_agent,
            run_anomaly_agent,
            run_investor_agent,
            run_qa_agent,
        ])

    return activities


async def create_worker() -> Worker:
    """Creates and returns configured Temporal worker (not started)."""
    client = await Client.connect(TEMPORAL_HOST)
    return Worker(
        client,
        task_queue=TASK_QUEUE,
        workflows=_build_workflow_list(),
        activities=_build_activity_list(),
        max_concurrent_activities=MAX_CONCURRENT,
    )


async def main() -> None:
    """Entry point for the Temporal worker."""
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(name)s %(levelname)s %(message)s",
    )
    log.info("Connecting to Temporal at %s", TEMPORAL_HOST)
    log.info("Task queue: %s", TASK_QUEUE)

    worker = await create_worker()

    wf_count = len(worker._workflows) if hasattr(worker, "_workflows") else "?"
    log.info("Worker started — listening on %s", TASK_QUEUE)
    log.info("Workflows registered: %s — V5.2 canonical (6) | V6=%s | Legacy=%s",
             wf_count,
             os.getenv("ENABLE_V6_WORKFLOWS", "off"),
             os.getenv("LEGACY_FDE_MODULES", "off"))
    act_count = len(worker._activities) if hasattr(worker, "_activities") else "?"
    log.info("Activities: %s registered (6 base + legacy=%s) | V5.2 specialists: chief_of_staff, discovery, ontology_mapping, knowledge_validation, solution_architect, governance",
             act_count,
             os.getenv("LEGACY_FDE_MODULES", "off"))

    async with worker:
        await asyncio.Future()  # run forever


if __name__ == "__main__":
    asyncio.run(main())

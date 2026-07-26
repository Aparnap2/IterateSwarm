"""
DEPRECATED: This file has been renamed to solution_architect_workflow.py.

The class ``WorkflowBuilderWorkflow`` has been renamed to
``SolutionArchitectWorkflow``. Import from
``src.workflows.solution_architect_workflow`` instead.
"""
import warnings
from src.workflows.solution_architect_workflow import SolutionArchitectWorkflow as WorkflowBuilderWorkflow

warnings.warn(
    "WorkflowBuilderWorkflow has been renamed to SolutionArchitectWorkflow. "
    "Import from src.workflows.solution_architect_workflow instead.",
    DeprecationWarning,
    stacklevel=2,
)

"""AgentSeism -- localizing where LLM-agent executions are behaviorally fragile.

AgentSeism does not judge whether an outcome is correct. It projects each run
into comparable execution features, measures how those features vary across
repeated runs, and ranks the ones whose variation is most associated with
downstream outcome variation.
"""

from agentseism.scan import analyze, divergence_tables, scan
from agentseism.report import ScanReport
from agentseism.runner import run_experiment
from agentseism.trace import TraceCollector
from agentseism.features import (
    MISSING,
    ExecutionFeature,
    FeatureSchema,
    FeatureSpec,
    ObservationRole,
)
from agentseism.projection import EventProjector, Projector, project_run
from agentseism.intervention import Intervenable, InterventionResult
from agentseism.types import Event, Experiment, Run, Task

__version__ = "0.2.0"

__all__ = [
    "scan",
    "analyze",
    "divergence_tables",
    "ScanReport",
    "run_experiment",
    "TraceCollector",
    "ExecutionFeature",
    "FeatureSchema",
    "FeatureSpec",
    "ObservationRole",
    "MISSING",
    "Projector",
    "EventProjector",
    "project_run",
    "Intervenable",
    "InterventionResult",
    "Task",
    "Run",
    "Event",
    "Experiment",
    "__version__",
]

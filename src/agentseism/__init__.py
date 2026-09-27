"""AgentSeism: CI decisions for stochastic AI agents.

AgentSeism runs a baseline and a candidate several times each and decides
whether the candidate made the agent worse: PASS, REGRESSION, INSUFFICIENT
EVIDENCE or INCOMPARABLE. The product entry point is the `seism` CLI
(`agentseism.cli`). The decision rule is in `agentseism.contract` and
`agentseism.capability`.

The run-level analysis API re-exported below (`scan`, feature projection) is
the earlier research tooling the product grew out of. It is kept for
compatibility and is not part of the CI decision.
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

__version__ = "0.1.1"

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

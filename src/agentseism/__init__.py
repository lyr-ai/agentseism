"""AgentSeism -- discovering where LLM-agent executions are behaviorally fragile.

AgentSeism does not judge whether an outcome is correct. It measures where
behavioral variation emerges inside an execution, how far it propagates, and
which execution points are most associated with downstream outcome variation.
"""

from agentseism.scan import analyze, divergence_tables, scan
from agentseism.report import ScanReport
from agentseism.runner import run_experiment
from agentseism.trace import TraceCollector
from agentseism.types import Event, Experiment, Run, Task

__version__ = "0.1.0"

__all__ = [
    "scan",
    "analyze",
    "divergence_tables",
    "ScanReport",
    "run_experiment",
    "TraceCollector",
    "Task",
    "Run",
    "Event",
    "Experiment",
    "__version__",
]

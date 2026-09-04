"""Top-level entry point.

    from agentseism import scan

    report = scan(agent=my_agent, cases=my_cases, trials=10, projector=my_adapter)
    print(report)
"""

from __future__ import annotations

from typing import Any, Callable, Sequence

from agentseism.attribution import rank_weak_points
from agentseism.attribution.weakpoints import DIVERGENCE_THRESHOLD
from agentseism.features import FeatureSchema
from agentseism.metrics.comparators import Comparator
from agentseism.projection import Projector
from agentseism.report import ScanReport
from agentseism.runner import run_experiment
from agentseism.types import Experiment
from agentseism.variation import feature_divergences, task_variation


def divergence_tables(
    experiment: Experiment,
    *,
    comparator: Comparator | str | None = None,
    schema: FeatureSchema | None = None,
) -> dict:
    """Per-task ``(feature columns, pair divergences)`` tables.

    Input to both :func:`rank_weak_points` and every baseline, so that
    AgentSeism and the baselines it is compared against always see exactly the
    same evidence.
    """
    schema = schema or experiment.schema
    tables = {}
    for task in experiment.tasks:
        runs = experiment.runs_for(task.id)
        if len(runs) < 2:
            continue
        columns, pairs = feature_divergences(
            runs, schema, outcome_comparator=comparator
        )
        if columns:
            tables[task.id] = (columns, pairs)
    return tables


def analyze(
    experiment: Experiment,
    *,
    comparator: Comparator | str | None = None,
    schema: FeatureSchema | None = None,
    threshold: float = DIVERGENCE_THRESHOLD,
    mode_threshold: float = 0.85,
) -> ScanReport:
    """Analyze an experiment that has already been run (or loaded from disk)."""
    schema = schema or experiment.schema
    tasks = [
        task_variation(experiment, task.id, comparator, mode_threshold=mode_threshold)
        for task in experiment.tasks
    ]
    per_task = divergence_tables(experiment, comparator=comparator, schema=schema)
    ranking = (
        rank_weak_points(per_task, schema, threshold=threshold) if per_task else None
    )

    return ScanReport(
        agent_id=experiment.agent_id,
        experiment=experiment,
        tasks=tasks,
        ranking=ranking,
        schema=schema,
    )


def scan(
    agent: Callable,
    cases: Sequence[Any],
    trials: int = 10,
    *,
    outcome: Callable[[Any], Any] | None = None,
    comparator: Comparator | str | None = None,
    projector: Projector | None = None,
    agent_id: str = "agent",
    threshold: float = DIVERGENCE_THRESHOLD,
    save_to: str | None = None,
    **runner_kwargs: Any,
) -> ScanReport:
    """Run an agent repeatedly and localize where its behavior varies.

    ``agent`` is any callable ``f(input) -> output``; if it accepts a ``trace``
    keyword, its raw trace is projected into execution features and those
    features are ranked.
    """
    experiment = run_experiment(
        agent,
        cases,
        trials,
        outcome=outcome,
        projector=projector,
        agent_id=agent_id,
        **runner_kwargs,
    )
    if save_to:
        experiment.save(save_to)
    return analyze(experiment, comparator=comparator, threshold=threshold)

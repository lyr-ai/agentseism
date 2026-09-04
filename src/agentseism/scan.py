"""Top-level entry point.

    from agentseism import scan

    report = scan(agent=my_agent, cases=my_cases, trials=10)
    print(report)
"""

from __future__ import annotations

from typing import Any, Callable, Sequence

from agentseism.attribution import rank_weak_points
from agentseism.attribution.weakpoints import DIVERGENCE_THRESHOLD
from agentseism.metrics.comparators import Comparator
from agentseism.report import ScanReport
from agentseism.runner import run_experiment
from agentseism.types import Experiment
from agentseism.variation import pair_divergences, task_variation


def divergence_tables(
    experiment: Experiment,
    *,
    comparator: Comparator | str | None = None,
    event_comparator: Comparator | str | None = None,
) -> dict:
    """Per-task ``(slots, pair divergences)`` tables.

    This is the input to both :func:`rank_weak_points` and every baseline, so
    that AgentSeism and the baselines it is compared against always see exactly
    the same evidence.
    """
    tables = {}
    for task in experiment.tasks:
        runs = experiment.runs_for(task.id)
        if len(runs) < 2:
            continue
        slots, pairs = pair_divergences(
            runs,
            outcome_comparator=comparator,
            event_comparator=event_comparator,
        )
        if slots:
            tables[task.id] = (slots, pairs)
    return tables


def analyze(
    experiment: Experiment,
    *,
    comparator: Comparator | str | None = None,
    event_comparator: Comparator | str | None = None,
    threshold: float = DIVERGENCE_THRESHOLD,
    mode_threshold: float = 0.85,
) -> ScanReport:
    """Analyze an experiment that has already been run (or loaded from disk)."""
    tasks = [
        task_variation(experiment, task.id, comparator, mode_threshold=mode_threshold)
        for task in experiment.tasks
    ]

    per_task = divergence_tables(
        experiment, comparator=comparator, event_comparator=event_comparator
    )
    weak_points = rank_weak_points(per_task, threshold=threshold) if per_task else []

    return ScanReport(
        agent_id=experiment.agent_id,
        experiment=experiment,
        tasks=tasks,
        weak_points=weak_points,
    )


def scan(
    agent: Callable,
    cases: Sequence[Any],
    trials: int = 10,
    *,
    outcome: Callable[[Any], Any] | None = None,
    comparator: Comparator | str | None = None,
    event_comparator: Comparator | str | None = None,
    agent_id: str = "agent",
    threshold: float = DIVERGENCE_THRESHOLD,
    save_to: str | None = None,
    **runner_kwargs: Any,
) -> ScanReport:
    """Run an agent repeatedly and report where its behavior varies.

    ``agent`` is any callable ``f(input) -> output``; if it accepts a ``trace``
    keyword it also gets event-level weak-point attribution.
    """
    experiment = run_experiment(
        agent,
        cases,
        trials,
        outcome=outcome,
        agent_id=agent_id,
        **runner_kwargs,
    )
    if save_to:
        experiment.save(save_to)
    return analyze(
        experiment,
        comparator=comparator,
        event_comparator=event_comparator,
        threshold=threshold,
    )

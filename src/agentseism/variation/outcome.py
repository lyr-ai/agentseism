"""Outcome-level variation (DESIGN.md §10).

    C_t = 2 / (N(N-1)) * sum_{i<j} sim(Y_i, Y_j)
    V_t = 1 - C_t
"""

from __future__ import annotations

from dataclasses import dataclass, field
from itertools import combinations
from typing import Any, Sequence

from agentseism.metrics import resolve_comparator
from agentseism.metrics.comparators import Comparator
from agentseism.types import Experiment


@dataclass
class OutcomeMode:
    """A cluster of behaviorally equivalent outcomes."""

    representative: Any
    count: int
    share: float
    run_ids: list[str] = field(default_factory=list)


@dataclass
class TaskVariation:
    task_id: str
    n_runs: int
    consistency: float
    variation: float
    modes: list[OutcomeMode] = field(default_factory=list)
    n_errors: int = 0


def consistency(values: Sequence[Any], comparator: Comparator | str | None = None) -> float:
    """Mean pairwise similarity over a set of outcomes."""
    compare = resolve_comparator(comparator)
    if len(values) < 2:
        return 1.0
    sims = [compare(a, b) for a, b in combinations(values, 2)]
    return sum(sims) / len(sims)


def outcome_modes(
    values: Sequence[Any],
    comparator: Comparator | str | None = None,
    *,
    threshold: float = 0.85,
    run_ids: Sequence[str] | None = None,
) -> list[OutcomeMode]:
    """Greedy single-pass clustering of outcomes by similarity.

    Not a claim about the true structure of the outcome space -- just enough to
    report "60% mode A / 30% mode B / 10% mode C" (DESIGN.md §10).
    """
    compare = resolve_comparator(comparator)
    ids = list(run_ids) if run_ids is not None else [str(i) for i in range(len(values))]
    clusters: list[list[int]] = []
    for index, value in enumerate(values):
        for cluster in clusters:
            if compare(values[cluster[0]], value) >= threshold:
                cluster.append(index)
                break
        else:
            clusters.append([index])

    total = len(values) or 1
    modes = [
        OutcomeMode(
            representative=values[cluster[0]],
            count=len(cluster),
            share=len(cluster) / total,
            run_ids=[ids[i] for i in cluster],
        )
        for cluster in clusters
    ]
    modes.sort(key=lambda m: -m.count)
    return modes


def task_variation(
    experiment: Experiment,
    task_id: str,
    comparator: Comparator | str | None = None,
    *,
    mode_threshold: float = 0.85,
) -> TaskVariation:
    runs = experiment.runs_for(task_id)
    outcomes = [r.outcome for r in runs]
    c = consistency(outcomes, comparator)
    n_errors = sum(
        1 for r in experiment.runs if r.task_id == task_id and not r.ok
    )
    return TaskVariation(
        task_id=task_id,
        n_runs=len(runs),
        consistency=c,
        variation=1.0 - c,
        modes=outcome_modes(
            outcomes,
            comparator,
            threshold=mode_threshold,
            run_ids=[r.id for r in runs],
        ),
        n_errors=n_errors,
    )

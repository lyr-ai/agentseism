"""Attribution baselines (DESIGN.md §18, DESIGN-FEATURE-PROJECTION.md §22).

Each baseline consumes the same per-task divergence tables as
:func:`rank_weak_points` and returns feature names, best first.

``first_divergence`` requires a declared feature order. On an unordered schema
it is unavailable rather than approximated -- inventing an order to make a
baseline runnable would make the comparison meaningless.

The correlation baseline is the one that matters. If it matches AgentSeism on
real agents, the weak-point score is not yet a contribution (§22); that is a
planned falsification test, not an implementation detail.
"""

from __future__ import annotations

import random
from statistics import mean
from typing import Sequence

from agentseism.alignment import FeatureColumn
from agentseism.attribution.weakpoints import _pearson
from agentseism.features import FeatureSchema, ObservationRole
from agentseism.variation.features import PairDivergence

PerTask = dict[str, tuple[Sequence[FeatureColumn], Sequence[PairDivergence]]]


class BaselineUnavailable(RuntimeError):
    """Raised when a baseline cannot run on this schema."""


def _attributable(per_task: PerTask, schema: FeatureSchema | None) -> list[str]:
    names: list[str] = []
    for columns, _ in per_task.values():
        for column in columns:
            spec = schema.spec(column.name) if schema else None
            role = spec.role if spec else column.role
            if role is ObservationRole.OUTCOME:
                continue
            if column.name not in names:
                names.append(column.name)
    return names


def _scored(scores: dict[str, float]) -> list[str]:
    return [name for name, _ in sorted(scores.items(), key=lambda kv: (-kv[1], kv[0]))]


def _columns(per_task: PerTask, schema, key):
    values: dict[str, list[float]] = {n: [] for n in _attributable(per_task, schema)}
    outcomes: dict[str, list[float]] = {n: [] for n in values}
    for _, pairs in per_task.values():
        for pair in pairs:
            for name in values:
                if name in pair.features:
                    values[name].append(pair.features[name])
                    outcomes[name].append(pair.outcome)
    return values, outcomes


# Baselines produce scores, not just an order. Scores let a comparison handle
# ties explicitly: resolving them by name would quietly decide who wins whenever
# several features are equally plausible (see `credit_at_k`).


def random_scores(per_task: PerTask, schema=None, *, seed: int = 0, **_: object) -> dict[str, float]:
    rng = random.Random(seed)
    return {name: rng.random() for name in sorted(_attributable(per_task, schema))}


def largest_diff_scores(per_task: PerTask, schema=None, **_: object) -> dict[str, float]:
    values, _ = _columns(per_task, schema, None)
    return {n: mean(v) if v else 0.0 for n, v in values.items()}


def correlation_scores(per_task: PerTask, schema=None, **_: object) -> dict[str, float]:
    values, outcomes = _columns(per_task, schema, None)
    return {n: max(0.0, _pearson(v, outcomes[n])) for n, v in values.items()}


def first_divergence_scores(
    per_task: PerTask, schema: FeatureSchema | None = None, *, threshold: float = 0.15, **_: object
) -> dict[str, float]:
    if schema is None or not schema.ordered:
        raise BaselineUnavailable(
            "first_divergence needs a declared feature order; this schema has none"
        )
    ordered = [n for n in schema.ordered_names() if n in set(_attributable(per_task, schema))]
    counts = {name: 0.0 for name in ordered}
    for _, pairs in per_task.values():
        for pair in pairs:
            for name in ordered:
                if pair.features.get(name, 0.0) >= threshold:
                    counts[name] += 1
                    break
    return counts


def random_point(per_task: PerTask, schema=None, **kwargs) -> list[str]:
    return _scored(random_scores(per_task, schema, **kwargs))


def largest_diff(per_task: PerTask, schema=None, **kwargs) -> list[str]:
    return _scored(largest_diff_scores(per_task, schema, **kwargs))


def correlation_only(per_task: PerTask, schema=None, **kwargs) -> list[str]:
    return _scored(correlation_scores(per_task, schema, **kwargs))


def first_divergence(per_task: PerTask, schema=None, **kwargs) -> list[str]:
    return _scored(first_divergence_scores(per_task, schema, **kwargs))


BASELINES = {
    "random": random_point,
    "first_divergence": first_divergence,
    "largest_diff": largest_diff,
    "correlation": correlation_only,
}

BASELINE_SCORERS = {
    "random": random_scores,
    "first_divergence": first_divergence_scores,
    "largest_diff": largest_diff_scores,
    "correlation": correlation_scores,
}


def available_baselines(schema: FeatureSchema | None, *, scorers: bool = False) -> dict:
    """Baselines that can run on this schema, honestly reported."""
    source = BASELINE_SCORERS if scorers else BASELINES
    if schema is not None and schema.ordered:
        return dict(source)
    return {k: v for k, v in source.items() if k != "first_divergence"}


def credit_at_k(scores: dict[str, float], target: str, k: int) -> float:
    """Expected Attribution@k credit under a uniformly random tie-break.

    A method that puts the injected feature in a three-way tie for first place
    gets 1/3 at k=1, not a free win from alphabetical ordering. Applied to
    AgentSeism and to every baseline alike.
    """
    if target not in scores:
        return 0.0
    target_score = scores[target]
    better = sum(1 for s in scores.values() if s > target_score)
    tied = sum(1 for s in scores.values() if s == target_score)
    if better >= k:
        return 0.0
    return min(tied, k - better) / tied

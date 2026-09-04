"""Feature-level variation (DESIGN-FEATURE-PROJECTION.md §13, §14).

For every pair of runs of one task, record how much each declared feature
differs and how much the outcome differs. Everything the ranker and the
baselines consume is derived from this table, so they always see the same
evidence.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from itertools import combinations
from typing import Any, Sequence

from agentseism.alignment import FeatureColumn, align_features
from agentseism.features import MISSING, FeatureSchema
from agentseism.metrics import default_comparator_for, resolve_comparator
from agentseism.metrics.comparators import Comparator
from agentseism.types import Run

MISSING_DIVERGENCE = 1.0
"""One run reached an execution point and the other did not: maximal difference."""


@dataclass
class PairDivergence:
    """Divergence between two runs of the same task."""

    run_a: str
    run_b: str
    outcome: float
    features: dict[str, float] = field(default_factory=dict)


def comparator_for(
    column: FeatureColumn, schema: FeatureSchema | None
) -> Comparator:
    """Declared comparator if the adapter gave one, else inferred from the value."""
    spec = schema.spec(column.name) if schema else None
    if spec is not None and spec.comparator is not None:
        return resolve_comparator(spec.comparator)
    for value in column.values.values():
        if value is not MISSING:
            return default_comparator_for(value)
    return resolve_comparator("exact")


def divergence(a: Any, b: Any, compare: Comparator) -> float:
    if a is MISSING and b is MISSING:
        return 0.0
    if a is MISSING or b is MISSING:
        return MISSING_DIVERGENCE
    return 1.0 - compare(a, b)


def feature_divergences(
    runs: Sequence[Run],
    schema: FeatureSchema | None = None,
    *,
    outcome_comparator: Comparator | str | None = None,
    columns: Sequence[FeatureColumn] | None = None,
) -> tuple[list[FeatureColumn], list[PairDivergence]]:
    """Build the per-pair divergence table for one task's runs."""
    runs = [r for r in runs if r.ok]
    columns = list(columns) if columns is not None else align_features(runs, schema)
    compare_outcome = resolve_comparator(outcome_comparator)
    comparators = {c.name: comparator_for(c, schema) for c in columns}

    pairs: list[PairDivergence] = []
    for a, b in combinations(runs, 2):
        pairs.append(
            PairDivergence(
                run_a=a.id,
                run_b=b.id,
                outcome=1.0 - compare_outcome(a.outcome, b.outcome),
                features={
                    column.name: divergence(
                        column.value(a.id), column.value(b.id), comparators[column.name]
                    )
                    for column in columns
                },
            )
        )
    return columns, pairs

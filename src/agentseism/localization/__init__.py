"""Weak-point localization and baselines.

V0 localizes: it ranks features whose variation is associated with outcome
variation. It does not attribute causally -- that needs intervention
(DESIGN-INTERVENTION.md).
"""

from agentseism.localization.weakpoints import (
    AGGREGATE_MODE,
    POSITIONED_MODE,
    Ranking,
    WeakPoint,
    rank_weak_points,
)
from agentseism.localization.baselines import (
    BASELINES,
    BASELINE_SCORERS,
    BaselineUnavailable,
    available_baselines,
    credit_at_k,
    correlation_only,
    first_divergence,
    largest_diff,
    random_point,
)

__all__ = [
    "WeakPoint",
    "Ranking",
    "rank_weak_points",
    "POSITIONED_MODE",
    "AGGREGATE_MODE",
    "BASELINES",
    "BASELINE_SCORERS",
    "BaselineUnavailable",
    "available_baselines",
    "credit_at_k",
    "first_divergence",
    "largest_diff",
    "correlation_only",
    "random_point",
]

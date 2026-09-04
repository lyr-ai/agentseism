"""Attribution baselines (DESIGN.md §18).

Each baseline consumes the same per-task divergence tables as
:func:`rank_weak_points` and returns execution-point keys, best first. They
exist so that "AgentSeism found the injected weak point" is only reported
relative to what a trivial method already finds.

The LLM-debugger baseline is intentionally absent from V0: it requires a model
call and belongs with the Week-5 experiment harness, not the core library.
"""

from __future__ import annotations

import random
from statistics import mean
from typing import Sequence

from agentseism.alignment import Slot
from agentseism.attribution.weakpoints import DIVERGENCE_THRESHOLD, _pearson
from agentseism.variation.events import PairDivergence

PerTask = dict[str, tuple[Sequence[Slot], Sequence[PairDivergence]]]


def _slot_order(per_task: PerTask) -> dict[str, float]:
    order: dict[str, list[float]] = {}
    for slots, _ in per_task.values():
        for slot in slots:
            order.setdefault(slot.key, []).append(slot.order)
    return {key: mean(values) for key, values in order.items()}


def _scored(scores: dict[str, float], per_task: PerTask) -> list[str]:
    order = _slot_order(per_task)
    return [
        key
        for key, _ in sorted(
            scores.items(), key=lambda kv: (-kv[1], order.get(kv[0], 0.0))
        )
    ]


def random_point(per_task: PerTask, *, seed: int = 0, **_: object) -> list[str]:
    """Random execution point."""
    keys = sorted(_slot_order(per_task))
    random.Random(seed).shuffle(keys)
    return keys


def largest_diff(per_task: PerTask, **_: object) -> list[str]:
    """Rank by mean local divergence -- the "biggest diff wins" heuristic."""
    scores: dict[str, list[float]] = {}
    for _, pairs in per_task.values():
        for pair in pairs:
            for key, value in pair.slots.items():
                scores.setdefault(key, []).append(value)
    return _scored({k: mean(v) for k, v in scores.items()}, per_task)


def first_divergence(
    per_task: PerTask, *, threshold: float = DIVERGENCE_THRESHOLD, **_: object
) -> list[str]:
    """Rank by how often a point is the earliest divergence in a run pair."""
    counts: dict[str, float] = {key: 0.0 for key in _slot_order(per_task)}
    for slots, pairs in per_task.values():
        ordered = sorted(slots, key=lambda s: (s.order, s.key))
        for pair in pairs:
            for slot in ordered:
                if pair.slots.get(slot.key, 0.0) >= threshold:
                    counts[slot.key] = counts.get(slot.key, 0.0) + 1
                    break
    return _scored(counts, per_task)


def correlation_only(per_task: PerTask, **_: object) -> list[str]:
    """Rank by correlation between local divergence and outcome divergence."""
    local: dict[str, list[float]] = {}
    outcomes: dict[str, list[float]] = {}
    for _, pairs in per_task.values():
        for pair in pairs:
            for key, value in pair.slots.items():
                local.setdefault(key, []).append(value)
                outcomes.setdefault(key, []).append(pair.outcome)
    return _scored(
        {k: max(0.0, _pearson(v, outcomes[k])) for k, v in local.items()}, per_task
    )


BASELINES = {
    "random": random_point,
    "first_divergence": first_divergence,
    "largest_diff": largest_diff,
    "correlation": correlation_only,
}

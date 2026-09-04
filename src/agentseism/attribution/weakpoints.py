"""Weak-point ranking (DESIGN.md §14, §15).

    W(e) = LocalVariation(e) * OutcomeAssociation(e) * Propagation(e)

This is association-based attribution, not causal attribution. A high score says
that variation at an execution point co-varies with downstream and outcome
variation across repeated runs -- not that intervening there would change the
outcome. The distinction is load-bearing for the paper and must survive into any
user-facing wording.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from statistics import mean
from typing import Sequence

from agentseism.alignment import Slot
from agentseism.variation.events import PairDivergence

DIVERGENCE_THRESHOLD = 0.15
"""Above this, a pair is treated as having diverged at an execution point."""


@dataclass
class WeakPoint:
    key: str
    label: str
    order: float
    local_variation: float
    propagation: float
    outcome_association: float
    score: float
    n_pairs: int = 0
    coverage: float = 1.0
    tasks: list[str] = field(default_factory=list)


def _pearson(xs: Sequence[float], ys: Sequence[float]) -> float:
    n = len(xs)
    if n < 2:
        return 0.0
    mx, my = mean(xs), mean(ys)
    num = sum((x - mx) * (y - my) for x, y in zip(xs, ys))
    dx = sum((x - mx) ** 2 for x in xs)
    dy = sum((y - my) ** 2 for y in ys)
    if dx <= 0 or dy <= 0:
        return 0.0
    return num / (dx * dy) ** 0.5


def _metrics_for_slot(
    key: str,
    slots: Sequence[Slot],
    pairs: Sequence[PairDivergence],
    threshold: float,
) -> tuple[float, float, float]:
    """Return (local_variation, propagation, outcome_association) for one slot."""
    local = [p.slots.get(key, 0.0) for p in pairs]
    outcomes = [p.outcome for p in pairs]

    order = {slot.key: slot.order for slot in slots}
    downstream_keys = [s.key for s in slots if order[s.key] > order[key]]

    # Propagation: when this point diverges, do the points after it also diverge?
    diverged = [i for i, d in enumerate(local) if d >= threshold]
    if downstream_keys and diverged:
        propagation = mean(
            mean(
                1.0 if pairs[i].slots.get(k, 0.0) >= threshold else 0.0
                for k in downstream_keys
            )
            for i in diverged
        )
    elif not downstream_keys and diverged:
        # Terminal execution point: its own divergence is what reaches the outcome.
        propagation = mean(local[i] for i in diverged)
    else:
        propagation = 0.0

    # Outcome association: does divergence here predict outcome divergence?
    association = max(0.0, _pearson(local, outcomes))

    return (mean(local) if local else 0.0, propagation, association)


def rank_weak_points(
    per_task: dict[str, tuple[Sequence[Slot], Sequence[PairDivergence]]],
    *,
    threshold: float = DIVERGENCE_THRESHOLD,
    min_coverage: float = 0.0,
    exclude: Sequence[str] = (),
) -> list[WeakPoint]:
    """Rank execution points across one or more tasks.

    ``per_task`` maps task id -> (slots, pair divergences), as produced by
    :func:`agentseism.variation.pair_divergences`. Slot metrics are averaged
    across tasks so that a weak point is a property of the agent, not of a
    single input.

    ``exclude`` drops execution points by label. Use it for any point that *is*
    the outcome rather than a step toward it: such a point has an outcome
    association of 1.0 by construction and would always rank first, which says
    nothing. What was excluded is reported, never dropped silently.
    """
    excluded = set(exclude)
    accumulated: dict[str, dict] = {}

    for task_id, (slots, pairs) in per_task.items():
        if not pairs:
            continue
        for slot in slots:
            if slot.label in excluded or slot.key in excluded:
                continue
            local, propagation, association = _metrics_for_slot(
                slot.key, slots, pairs, threshold
            )
            entry = accumulated.setdefault(
                slot.key,
                {
                    "label": slot.label,
                    "order": [],
                    "local": [],
                    "propagation": [],
                    "association": [],
                    "coverage": [],
                    "n_pairs": 0,
                    "tasks": [],
                },
            )
            entry["order"].append(slot.order)
            entry["local"].append(local)
            entry["propagation"].append(propagation)
            entry["association"].append(association)
            entry["coverage"].append(slot.coverage)
            entry["n_pairs"] += len(pairs)
            entry["tasks"].append(task_id)

    weak_points: list[WeakPoint] = []
    for key, entry in accumulated.items():
        coverage = mean(entry["coverage"])
        if coverage < min_coverage:
            continue
        local = mean(entry["local"])
        propagation = mean(entry["propagation"])
        association = mean(entry["association"])
        weak_points.append(
            WeakPoint(
                key=key,
                label=entry["label"],
                order=mean(entry["order"]),
                local_variation=local,
                propagation=propagation,
                outcome_association=association,
                score=local * propagation * association,
                n_pairs=entry["n_pairs"],
                coverage=coverage,
                tasks=sorted(set(entry["tasks"])),
            )
        )

    weak_points.sort(key=lambda w: (-w.score, w.order))
    return weak_points

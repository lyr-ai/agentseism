"""Weak-point localization (DESIGN-FEATURE-PROJECTION.md §14-§21).

    ordered schema     W_f = V_f x A_f x P_f
    unordered schema   W_f = V_f x A_f

Propagation is only used when the adapter declared feature order. When it did
not, the score has no propagation term rather than an invented one (§16, §17).

This is weak-point *localization*, not causal attribution. A feature that merely
inherits variation from the real source correlates with the outcome just as
strongly (§21); separating the two needs intervention, which V0 does not do.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from statistics import mean
from typing import Iterator, Sequence

from agentseism.alignment import FeatureColumn
from agentseism.features import FeatureSchema, ObservationRole
from agentseism.variation.features import PairDivergence

DIVERGENCE_THRESHOLD = 0.15
"""Above this, a pair is treated as having diverged at a feature."""

FAMILY_CORRELATION = 0.9
"""Features whose divergence patterns correlate at least this strongly are
reported as one execution-feature family rather than as independent findings."""

ORDERED_MODE = "V x A x P"
UNORDERED_MODE = "V x A"


@dataclass
class WeakPoint:
    name: str
    local_variation: float
    outcome_association: float
    score: float
    scoring_mode: str
    propagation: float | None = None
    order: float = float("inf")
    coverage: float = 1.0
    n_pairs: int = 0
    tasks: list[str] = field(default_factory=list)
    family: str | None = None
    family_members: list[str] = field(default_factory=list)

    @property
    def label(self) -> str:  # kept for report/back-compat readability
        return self.name


@dataclass
class Ranking:
    """Ranked weak points plus what was excluded and how they were scored."""

    weak_points: list[WeakPoint] = field(default_factory=list)
    excluded: list[str] = field(default_factory=list)
    scoring_mode: str = UNORDERED_MODE
    families: dict[str, list[str]] = field(default_factory=dict)

    def __iter__(self) -> Iterator[WeakPoint]:
        return iter(self.weak_points)

    def __len__(self) -> int:
        return len(self.weak_points)

    def __getitem__(self, index):
        return self.weak_points[index]

    def names(self) -> list[str]:
        return [w.name for w in self.weak_points]


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


def _propagation(
    name: str,
    downstream: Sequence[str],
    pairs: Sequence[PairDivergence],
    threshold: float,
) -> float:
    local = [p.features.get(name, 0.0) for p in pairs]
    diverged = [i for i, d in enumerate(local) if d >= threshold]
    if not diverged:
        return 0.0
    if not downstream:
        # Last declared feature: its own divergence is what reaches the outcome.
        return mean(local[i] for i in diverged)
    return mean(
        mean(1.0 if pairs[i].features.get(k, 0.0) >= threshold else 0.0 for k in downstream)
        for i in diverged
    )


def _families(
    vectors: dict[str, list[float]], ranked: list[WeakPoint], threshold: float
) -> dict[str, list[str]]:
    """Group features whose divergence patterns are near-duplicates (§20)."""
    parent = {name: name for name in vectors}

    def find(x: str) -> str:
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    names = list(vectors)
    for i, a in enumerate(names):
        for b in names[i + 1 :]:
            if _pearson(vectors[a], vectors[b]) >= threshold:
                parent[find(a)] = find(b)

    # Name each family after its highest-scoring member.
    best: dict[str, WeakPoint] = {}
    for wp in ranked:
        root = find(wp.name)
        if root not in best or wp.score > best[root].score:
            best[root] = wp

    families: dict[str, list[str]] = {}
    for wp in ranked:
        representative = best[find(wp.name)].name
        families.setdefault(representative, []).append(wp.name)
    return families


def rank_weak_points(
    per_task: dict[str, tuple[Sequence[FeatureColumn], Sequence[PairDivergence]]],
    schema: FeatureSchema | None = None,
    *,
    threshold: float = DIVERGENCE_THRESHOLD,
    min_coverage: float = 0.0,
    family_correlation: float = FAMILY_CORRELATION,
) -> Ranking:
    """Rank execution features across one or more tasks.

    ``OUTCOME`` observations are rejected by construction and reported as
    excluded: an observation that is the outcome has an association of 1.0 by
    definition (§9, §10).
    """
    ordered = bool(schema and schema.ordered)
    mode = ORDERED_MODE if ordered else UNORDERED_MODE
    downstream_of: dict[str, list[str]] = {}
    if ordered and schema:
        names_in_order = schema.ordered_names()
        for i, name in enumerate(names_in_order):
            downstream_of[name] = names_in_order[i + 1 :]

    excluded: list[str] = []
    accumulated: dict[str, dict] = {}
    vectors: dict[str, list[float]] = {}

    for task_id, (columns, pairs) in per_task.items():
        if not pairs:
            continue
        for column in columns:
            role = schema.spec(column.name).role if schema and schema.spec(column.name) else column.role
            if role is ObservationRole.OUTCOME:
                if column.name not in excluded:
                    excluded.append(column.name)
                continue

            local = [p.features.get(column.name, 0.0) for p in pairs]
            outcomes = [p.outcome for p in pairs]
            entry = accumulated.setdefault(
                column.name,
                {"local": [], "association": [], "propagation": [], "coverage": [],
                 "order": [], "n_pairs": 0, "tasks": []},
            )
            entry["local"].append(mean(local) if local else 0.0)
            entry["association"].append(max(0.0, _pearson(local, outcomes)))
            if ordered:
                entry["propagation"].append(
                    _propagation(column.name, downstream_of.get(column.name, []), pairs, threshold)
                )
            entry["coverage"].append(column.coverage)
            entry["order"].append(column.order)
            entry["n_pairs"] += len(pairs)
            entry["tasks"].append(task_id)
            vectors.setdefault(column.name, []).extend(local)

    weak_points: list[WeakPoint] = []
    for name, entry in accumulated.items():
        coverage = mean(entry["coverage"])
        if coverage < min_coverage:
            continue
        local = mean(entry["local"])
        association = mean(entry["association"])
        propagation = mean(entry["propagation"]) if entry["propagation"] else None
        score = local * association * (propagation if propagation is not None else 1.0)
        weak_points.append(
            WeakPoint(
                name=name,
                local_variation=local,
                outcome_association=association,
                propagation=propagation,
                score=score,
                scoring_mode=mode,
                order=mean(entry["order"]),
                coverage=coverage,
                n_pairs=entry["n_pairs"],
                tasks=sorted(set(entry["tasks"])),
            )
        )

    weak_points.sort(key=lambda w: (-w.score, w.order, w.name))
    families = _families(vectors, weak_points, family_correlation) if weak_points else {}
    members_by_name = {
        name: members for name, members in families.items()
    }
    for wp in weak_points:
        for representative, members in members_by_name.items():
            if wp.name in members:
                wp.family = representative
                if wp.name == representative:
                    wp.family_members = list(members)

    return Ranking(
        weak_points=weak_points,
        excluded=excluded,
        scoring_mode=mode,
        families={k: v for k, v in families.items() if len(v) > 1},
    )

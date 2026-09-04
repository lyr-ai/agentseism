"""Weak-point localization (DESIGN-FEATURE-PROJECTION.md §14-§21).

    positioned feature   W_f = V_f x A_f x P_f
    trajectory aggregate W_f = V_f x A_f

Propagation exists only where the adapter declared execution precedence. A
whole-trajectory aggregate has no position, so its propagation is ``None`` --
never silently 1 or 0 -- and its score is on a different scale. The two groups
are therefore ranked separately and never merged into one ordering.

This is **localization**, not causal attribution. A feature that merely inherits
variation from the real source correlates with the outcome just as strongly
(§21). Separating source from consequence needs intervention; see
DESIGN-INTERVENTION.md.
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

POSITIONED_MODE = "V x A x P"
AGGREGATE_MODE = "V x A"


@dataclass
class WeakPoint:
    name: str
    local_variation: float
    outcome_association: float
    score: float
    scoring_mode: str
    propagation: float | None = None
    positioned: bool = False
    coverage: float = 1.0
    n_pairs: int = 0
    tasks: list[str] = field(default_factory=list)
    family: str | None = None
    family_members: list[str] = field(default_factory=list)

    @property
    def propagation_text(self) -> str:
        if self.propagation is None:
            return "N/A (trajectory aggregate)"
        return f"{self.propagation:.2f}"


@dataclass
class Ranking:
    """Ranked weak points, grouped by scoring mode.

    ``weak_points`` lists positioned features first, then aggregates. Scores
    from the two groups are not comparable -- only a positioned feature is
    multiplied by a propagation factor -- so compare within a group.
    """

    positioned: list[WeakPoint] = field(default_factory=list)
    aggregates: list[WeakPoint] = field(default_factory=list)
    excluded: list[str] = field(default_factory=list)
    families: dict[str, list[str]] = field(default_factory=dict)

    @property
    def weak_points(self) -> list[WeakPoint]:
        return self.positioned + self.aggregates

    @property
    def scoring_mode(self) -> str:
        if self.positioned and self.aggregates:
            return f"{POSITIONED_MODE} / {AGGREGATE_MODE}"
        return POSITIONED_MODE if self.positioned else AGGREGATE_MODE

    @property
    def mixed(self) -> bool:
        return bool(self.positioned) and bool(self.aggregates)

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
    successors: Sequence[str],
    pairs: Sequence[PairDivergence],
    threshold: float,
) -> float:
    """When this feature diverges, does what comes after it diverge too?

    The outcome is the sink of the precedence DAG, so it always counts as one
    downstream item; a positioned feature with no declared successors is still
    measured against the outcome rather than against itself.
    """
    local = [p.features.get(name, 0.0) for p in pairs]
    diverged = [i for i, d in enumerate(local) if d >= threshold]
    if not diverged:
        return 0.0
    return mean(
        mean(
            [1.0 if pairs[i].features.get(k, 0.0) >= threshold else 0.0 for k in successors]
            + [1.0 if pairs[i].outcome >= threshold else 0.0]
        )
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

    best: dict[str, WeakPoint] = {}
    for wp in ranked:
        root = find(wp.name)
        if root not in best or wp.score > best[root].score:
            best[root] = wp

    families: dict[str, list[str]] = {}
    for wp in ranked:
        families.setdefault(best[find(wp.name)].name, []).append(wp.name)
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
    excluded: list[str] = []
    accumulated: dict[str, dict] = {}
    vectors: dict[str, list[float]] = {}

    for task_id, (columns, pairs) in per_task.items():
        if not pairs:
            continue
        for column in columns:
            spec = schema.spec(column.name) if schema else None
            role = spec.role if spec else column.role
            if role is ObservationRole.OUTCOME:
                if column.name not in excluded:
                    excluded.append(column.name)
                continue

            positioned = bool(schema and schema.positioned(column.name))
            local = [p.features.get(column.name, 0.0) for p in pairs]
            outcomes = [p.outcome for p in pairs]
            entry = accumulated.setdefault(
                column.name,
                {"local": [], "association": [], "propagation": [], "coverage": [],
                 "positioned": positioned, "n_pairs": 0, "tasks": []},
            )
            entry["local"].append(mean(local) if local else 0.0)
            entry["association"].append(max(0.0, _pearson(local, outcomes)))
            if positioned and schema:
                successors = [
                    n for n in schema.successors(column.name)
                    if schema.spec(n) and schema.spec(n).role is ObservationRole.FEATURE
                ]
                entry["propagation"].append(
                    _propagation(column.name, successors, pairs, threshold)
                )
            entry["coverage"].append(column.coverage)
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
        positioned = entry["positioned"]
        score = local * association * (propagation if propagation is not None else 1.0)
        weak_points.append(
            WeakPoint(
                name=name,
                local_variation=local,
                outcome_association=association,
                propagation=propagation,
                positioned=positioned,
                score=score,
                scoring_mode=POSITIONED_MODE if positioned else AGGREGATE_MODE,
                coverage=coverage,
                n_pairs=entry["n_pairs"],
                tasks=sorted(set(entry["tasks"])),
            )
        )

    families = _families(vectors, weak_points, family_correlation) if weak_points else {}
    for wp in weak_points:
        for representative, members in families.items():
            if wp.name in members:
                wp.family = representative
                if wp.name == representative:
                    wp.family_members = list(members)

    def order(group: list[WeakPoint]) -> list[WeakPoint]:
        return sorted(group, key=lambda w: (-w.score, w.name))

    return Ranking(
        positioned=order([w for w in weak_points if w.positioned]),
        aggregates=order([w for w in weak_points if not w.positioned]),
        excluded=excluded,
        families={k: v for k, v in families.items() if len(v) > 1},
    )

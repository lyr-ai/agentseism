"""Execution features (DESIGN-FEATURE-PROJECTION.md §3, §6, §9).

An execution feature is a comparable representation extracted from one run that
captures an aspect of agent behavior which may vary across runs. Features -- not
raw events -- are what AgentSeism aligns and attributes, because raw event
occurrence is not a reliable cross-run identity for a dynamic agent.

The core assigns no meaning to feature names. Adapters do.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Iterable

from agentseism.metrics.comparators import Comparator


class ObservationRole(str, Enum):
    """What an observation is for.

    Attribution rejects ``OUTCOME`` observations by construction: an observation
    that *is* the outcome has an outcome association of 1.0 by definition, so
    ranking it would be tautological (§9).
    """

    FEATURE = "feature"
    OUTCOME = "outcome"


class MissingFeature:
    """A feature that did not occur in a run.

    Missingness is an observable execution difference, not a gap to be skipped
    (§12).
    """

    _instance: "MissingFeature | None" = None

    def __new__(cls) -> "MissingFeature":
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __repr__(self) -> str:
        return "MISSING"

    def __eq__(self, other: Any) -> bool:
        return isinstance(other, MissingFeature)

    def __hash__(self) -> int:
        return hash("agentseism.MISSING")

    def __bool__(self) -> bool:
        return False


MISSING = MissingFeature()


@dataclass
class ExecutionFeature:
    name: str
    value: Any
    metadata: dict = field(default_factory=dict)


@dataclass(frozen=True)
class FeatureSpec:
    """Declaration of one projected feature.

    ``predecessors`` states execution precedence: the features that necessarily
    happen before this one. It is a partial order, expressed as a DAG, because
    real agents have one -- a ReAct agent's plan precedes the evidence it
    gathers, which precedes the reasoning before submission -- while its
    whole-trajectory aggregates (tool set, tool sequence, call count) have no
    position at all.

    A feature with a position gets a propagation term. An aggregate does not,
    and its propagation is ``None`` -- never silently 0 or 1 (§16, §17).

    Declare precedence only where the execution semantics really have it.
    Inventing an order to make a score look better would be measuring the
    metric, not the agent.
    """

    name: str
    comparator: Comparator | str | None = None
    predecessors: tuple[str, ...] = ()
    role: ObservationRole = ObservationRole.FEATURE
    description: str = ""


@dataclass
class FeatureSchema:
    """The frozen feature contract of one adapter version (§7, §24)."""

    version: str
    specs: list[FeatureSpec] = field(default_factory=list)

    def __post_init__(self) -> None:
        names = [s.name for s in self.specs]
        duplicates = {n for n in names if names.count(n) > 1}
        if duplicates:
            raise ValueError(f"duplicate feature names in schema: {sorted(duplicates)}")
        declared = set(names)
        for spec in self.specs:
            unknown = set(spec.predecessors) - declared
            if unknown:
                raise ValueError(
                    f"feature {spec.name!r} lists undeclared predecessors {sorted(unknown)}"
                )
        self._check_acyclic()

    def _check_acyclic(self) -> None:
        state: dict[str, int] = {}

        def visit(name: str, path: tuple[str, ...]) -> None:
            if state.get(name) == 2:
                return
            if state.get(name) == 1:
                cycle = " -> ".join(path + (name,))
                raise ValueError(f"precedence cycle in schema: {cycle}")
            state[name] = 1
            spec = self.spec(name)
            for predecessor in (spec.predecessors if spec else ()):
                visit(predecessor, path + (name,))
            state[name] = 2

        for spec in self.specs:
            visit(spec.name, ())

    def spec(self, name: str) -> FeatureSpec | None:
        for candidate in self.specs:
            if candidate.name == name:
                return candidate
        return None

    @property
    def feature_specs(self) -> list[FeatureSpec]:
        return [s for s in self.specs if s.role is ObservationRole.FEATURE]

    @property
    def outcome_specs(self) -> list[FeatureSpec]:
        return [s for s in self.specs if s.role is ObservationRole.OUTCOME]

    @property
    def feature_names(self) -> list[str]:
        return [s.name for s in self.feature_specs]

    @property
    def outcome_names(self) -> list[str]:
        return [s.name for s in self.outcome_specs]

    # -- precedence ---------------------------------------------------------

    def successors(self, name: str) -> list[str]:
        """Features that necessarily happen after ``name`` (transitively)."""
        found: list[str] = []
        frontier = [s.name for s in self.specs if name in s.predecessors]
        while frontier:
            current = frontier.pop()
            if current in found:
                continue
            found.append(current)
            frontier.extend(s.name for s in self.specs if current in s.predecessors)
        return found

    def positioned(self, name: str) -> bool:
        """True when the feature has a place in the precedence DAG.

        A feature is positioned if something precedes it or it precedes
        something. A whole-trajectory aggregate satisfies neither.
        """
        spec = self.spec(name)
        if spec is None:
            return False
        return bool(spec.predecessors) or bool(self.successors(name))

    @property
    def positioned_names(self) -> list[str]:
        return [n for n in self.feature_names if self.positioned(n)]

    @property
    def aggregate_names(self) -> list[str]:
        return [n for n in self.feature_names if not self.positioned(n)]

    @property
    def has_precedence(self) -> bool:
        """True when any attributable feature declares a position."""
        return bool(self.positioned_names)

    def topological_names(self) -> list[str]:
        """Positioned features, earliest first."""
        depth = {n: self._depth(n) for n in self.positioned_names}
        return sorted(depth, key=lambda n: (depth[n], n))

    def _depth(self, name: str, seen: frozenset = frozenset()) -> int:
        spec = self.spec(name)
        if spec is None or not spec.predecessors or name in seen:
            return 0
        return 1 + max(
            self._depth(p, seen | {name}) for p in spec.predecessors
        )


def schema_from_names(
    names: Iterable[str], *, version: str = "inferred", outcome: Iterable[str] = ()
) -> FeatureSchema:
    """Build a schema with no declared precedence, for adapters that only give names."""
    outcome_set = set(outcome)
    return FeatureSchema(
        version=version,
        specs=[
            FeatureSpec(
                name=name,
                role=ObservationRole.OUTCOME if name in outcome_set else ObservationRole.FEATURE,
            )
            for name in names
        ],
    )

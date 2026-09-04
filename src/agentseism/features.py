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

    ``order`` is optional. Declaring it for every feature makes the schema
    *ordered*, which is what licenses a propagation term in the weak-point
    score; leaving it out means the adapter is saying it does not know the
    topology, and the score must not invent one (§16, §17).
    """

    name: str
    comparator: Comparator | str | None = None
    order: int | None = None
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

    @property
    def ordered(self) -> bool:
        """True when every attributable feature declares its position."""
        specs = self.feature_specs
        return bool(specs) and all(s.order is not None for s in specs)

    def order_of(self, name: str) -> float:
        spec = self.spec(name)
        if spec is None or spec.order is None:
            return float("inf")
        return float(spec.order)

    def ordered_names(self) -> list[str]:
        return sorted(self.feature_names, key=self.order_of)


def schema_from_names(
    names: Iterable[str], *, version: str = "inferred", outcome: Iterable[str] = ()
) -> FeatureSchema:
    """Build an unordered schema for adapters that only declare names."""
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

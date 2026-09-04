"""Feature-name alignment (DESIGN-FEATURE-PROJECTION.md §11, §12)."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Sequence

from agentseism.features import MISSING, FeatureSchema, ObservationRole
from agentseism.types import Run


@dataclass
class FeatureColumn:
    """One feature's values across a set of runs."""

    name: str
    values: dict[str, Any] = field(default_factory=dict)
    order: float = float("inf")
    role: ObservationRole = ObservationRole.FEATURE

    @property
    def coverage(self) -> float:
        """Fraction of runs in which the feature was present."""
        if not self.values:
            return 0.0
        return sum(1 for v in self.values.values() if v is not MISSING) / len(self.values)

    def value(self, run_id: str) -> Any:
        return self.values.get(run_id, MISSING)


def align_features(
    runs: Sequence[Run], schema: FeatureSchema | None = None
) -> list[FeatureColumn]:
    """Line up projected features across runs.

    A feature absent from a run is ``MISSING`` rather than skipped: a run that
    never reached an execution point differs from one that did.
    """
    runs = [r for r in runs if r.ok]
    if not runs:
        return []

    if schema is not None and schema.specs:
        names = [s.name for s in schema.specs]
    else:
        names = []
        for run in runs:
            for name in run.features:
                if name not in names:
                    names.append(name)

    columns = []
    for index, name in enumerate(names):
        spec = schema.spec(name) if schema else None
        columns.append(
            FeatureColumn(
                name=name,
                values={
                    run.id: run.features[name].value if name in run.features else MISSING
                    for run in runs
                },
                order=float(spec.order) if spec and spec.order is not None else float(index),
                role=spec.role if spec else ObservationRole.FEATURE,
            )
        )
    return columns

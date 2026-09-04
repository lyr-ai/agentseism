"""Feature projection (DESIGN-FEATURE-PROJECTION.md §2, §6).

    Raw trace -> Agent adapter -> comparable execution features

An adapter (projector) declares a frozen feature schema and converts one run's
raw trace into values for those features. AgentSeism core never guesses what an
execution means; it only compares what the adapter declared.
"""

from __future__ import annotations

from typing import Any, Protocol, runtime_checkable

from agentseism.features import ExecutionFeature, FeatureSchema, schema_from_names
from agentseism.types import Run


@runtime_checkable
class Projector(Protocol):
    """The adapter contract."""

    name: str
    version: str
    schema: FeatureSchema

    def project(self, run: Run) -> dict[str, Any]:
        """Return feature values for one run, keyed by declared feature name."""


def project_run(run: Run, projector: Projector) -> dict[str, ExecutionFeature]:
    """Project one run and wrap the values as features.

    Undeclared names are an error, not a convenience: the schema is frozen per
    adapter version so that results from different schemas are never mixed
    (§7, §24).
    """
    values = projector.project(run) or {}
    declared = {s.name for s in projector.schema.specs}
    if declared:
        undeclared = set(values) - declared
        if undeclared:
            raise ValueError(
                f"projector {projector.name!r} returned undeclared features "
                f"{sorted(undeclared)}; add them to the schema and bump "
                f"version {projector.schema.version!r}"
            )
    return {
        name: ExecutionFeature(name=name, value=value)
        for name, value in values.items()
    }


class EventProjector:
    """Projects recorded raw events into same-named features.

    For agents whose execution points *are* stable -- fixed pipelines, or a
    dynamic agent that deliberately records a repeated semantic step -- the
    event name is already a valid cross-run identity, so occurrence-suffixed
    event names project directly onto features (§32).
    """

    name = "events"

    def __init__(
        self,
        schema: FeatureSchema | None = None,
        *,
        outcome_events: tuple[str, ...] = (),
        version: str = "events/1",
    ) -> None:
        self._schema = schema
        self._seen: list[str] = []
        self._outcome_events = set(outcome_events)
        self.version = schema.version if schema else version

    @property
    def schema(self) -> FeatureSchema:
        if self._schema is not None:
            return self._schema
        return schema_from_names(
            self._seen, version=self.version, outcome=self._outcome_events
        )

    def project(self, run: Run) -> dict[str, Any]:
        values: dict[str, Any] = {}
        seen: dict[str, int] = {}
        for event in run.events:
            label = event.slot
            occurrence = seen.get(label, 0)
            seen[label] = occurrence + 1
            key = label if occurrence == 0 else f"{label}#{occurrence}"
            values[key] = event.output
            if self._schema is None and key not in self._seen:
                self._seen.append(key)
        return values

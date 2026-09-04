"""Core data model.

Deliberately generic: AgentSeism does not assume the type of a task input, an
agent output, or an outcome. It only assumes that runs can be repeated and that
executions can optionally be observed as a sequence of events.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field, asdict
from typing import Any

from agentseism.features import (
    ExecutionFeature,
    FeatureSchema,
    FeatureSpec,
    ObservationRole,
)


@dataclass
class Task:
    """One unit of work presented to an agent."""

    id: str
    input: Any
    metadata: dict = field(default_factory=dict)


@dataclass
class Event:
    """One observable execution point inside a run.

    ``event_type`` is an execution primitive (``model_call``, ``tool_call``,
    ``retrieval``, ``decision``, ``transform``, ``memory_read``,
    ``memory_write``), not a domain concept. ``name`` is an optional stable
    label for the execution point, used by the aligner to match events across
    runs of the same task.
    """

    id: str
    run_id: str
    event_type: str
    input: Any = None
    output: Any = None
    name: str | None = None
    parent_ids: list[str] = field(default_factory=list)
    metadata: dict = field(default_factory=dict)

    @property
    def slot(self) -> str:
        """Label used for name-based alignment."""
        return self.name or self.event_type


@dataclass
class Run:
    """One execution of an agent on a task."""

    id: str
    task_id: str
    input: Any
    output: Any
    outcome: Any
    events: list[Event] = field(default_factory=list)
    features: dict[str, ExecutionFeature] = field(default_factory=dict)
    duration_ms: float | None = None
    error: str | None = None
    metadata: dict = field(default_factory=dict)

    @property
    def ok(self) -> bool:
        return self.error is None


@dataclass
class Experiment:
    """A set of tasks, each executed repeatedly by one agent configuration."""

    id: str
    agent_id: str
    tasks: list[Task] = field(default_factory=list)
    runs: list[Run] = field(default_factory=list)
    schema: FeatureSchema | None = None
    config: dict = field(default_factory=dict)

    def runs_for(self, task_id: str) -> list[Run]:
        return [r for r in self.runs if r.task_id == task_id and r.ok]

    # -- persistence ---------------------------------------------------------
    # Local artifacts only. No database, no server (DESIGN.md §20).

    def to_dict(self) -> dict:
        raw = asdict(self)
        if self.schema is not None:
            raw["schema"] = _schema_to_dict(self.schema)
        return raw

    def save(self, path: str) -> str:
        with open(path, "w", encoding="utf-8") as fh:
            json.dump(self.to_dict(), fh, indent=2, default=_fallback)
        return path

    @classmethod
    def load(cls, path: str) -> "Experiment":
        with open(path, encoding="utf-8") as fh:
            raw = json.load(fh)
        return cls.from_dict(raw)

    @classmethod
    def from_dict(cls, raw: dict) -> "Experiment":
        tasks = [Task(**t) for t in raw.get("tasks", [])]
        runs = []
        for r in raw.get("runs", []):
            r = dict(r)
            r["events"] = [Event(**e) for e in r.get("events", [])]
            r["features"] = {
                name: ExecutionFeature(**value)
                for name, value in (r.get("features") or {}).items()
            }
            runs.append(Run(**r))
        return cls(
            id=raw["id"],
            agent_id=raw.get("agent_id", "unknown"),
            tasks=tasks,
            runs=runs,
            schema=_schema_from_dict(raw.get("schema")),
            config=raw.get("config", {}),
        )


def _schema_to_dict(schema: FeatureSchema) -> dict:
    """Serialise a schema. Callable comparators cannot be persisted, so they are
    dropped and the comparator is re-inferred on load -- recorded here so the
    difference is visible rather than silent."""
    specs = []
    for spec in schema.specs:
        comparator = spec.comparator if isinstance(spec.comparator, str) else None
        specs.append(
            {
                "name": spec.name,
                "comparator": comparator,
                "comparator_was_callable": callable(spec.comparator),
                "order": spec.order,
                "role": spec.role.value,
                "description": spec.description,
            }
        )
    return {"version": schema.version, "specs": specs}


def _schema_from_dict(raw: dict | None) -> FeatureSchema | None:
    if not raw:
        return None
    return FeatureSchema(
        version=raw.get("version", "unknown"),
        specs=[
            FeatureSpec(
                name=spec["name"],
                comparator=spec.get("comparator"),
                order=spec.get("order"),
                role=ObservationRole(spec.get("role", "feature")),
                description=spec.get("description", ""),
            )
            for spec in raw.get("specs", [])
        ],
    )


def _fallback(obj: Any) -> str:
    """Persist anything the user's agent returned, even if it is not JSON."""
    return repr(obj)

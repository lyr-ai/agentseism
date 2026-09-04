"""Run alignment (DESIGN.md §11).

V0 deliberately does not attempt arbitrary graph alignment. Events are matched
by ``(name-or-type, occurrence index)``, which is reliable for agents whose
execution points are stably labelled -- the class of agents V0 targets.

A slot may be missing in some runs (dynamic execution path). That is itself a
form of divergence and is scored as maximal variation rather than skipped.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from statistics import mean
from typing import Sequence

from agentseism.types import Event, Run


@dataclass
class Slot:
    """One aligned execution point across a set of runs."""

    key: str
    label: str
    events: dict[str, Event | None] = field(default_factory=dict)
    order: float = 0.0

    @property
    def coverage(self) -> float:
        """Fraction of runs in which this execution point occurred."""
        if not self.events:
            return 0.0
        return sum(1 for e in self.events.values() if e is not None) / len(self.events)

    def event(self, run_id: str) -> Event | None:
        return self.events.get(run_id)


def align_runs(runs: Sequence[Run]) -> list[Slot]:
    """Align the events of several runs of the same task.

    Returns slots in execution order (mean position across runs).
    """
    runs = [r for r in runs if r.ok]
    if not runs:
        return []

    per_run: dict[str, dict[str, Event]] = {}
    positions: dict[str, list[float]] = {}

    for run in runs:
        seen: dict[str, int] = {}
        keyed: dict[str, Event] = {}
        for position, event in enumerate(run.events):
            label = event.slot
            occurrence = seen.get(label, 0)
            seen[label] = occurrence + 1
            key = label if occurrence == 0 else f"{label}#{occurrence}"
            keyed[key] = event
            positions.setdefault(key, []).append(position)
        per_run[run.id] = keyed

    slots: list[Slot] = []
    for key, seen_positions in positions.items():
        slot = Slot(
            key=key,
            label=key.split("#", 1)[0],
            events={run.id: per_run[run.id].get(key) for run in runs},
            order=mean(seen_positions),
        )
        slots.append(slot)

    slots.sort(key=lambda s: (s.order, s.key))
    return slots

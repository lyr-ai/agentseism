"""Event-level variation (DESIGN.md §12).

For every pair of runs of the same task we record how much each aligned
execution point differs, plus how much the outcome differs. Everything the
attribution ranker needs is derived from this table.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from itertools import combinations
from typing import Sequence

from agentseism.alignment import Slot, align_runs
from agentseism.metrics import resolve_comparator
from agentseism.metrics.comparators import Comparator
from agentseism.types import Run

MISSING_DIVERGENCE = 1.0
"""An execution point present in one run and absent in the other is maximally
divergent: the runs took different paths."""


@dataclass
class PairDivergence:
    """Divergence between two runs of the same task."""

    run_a: str
    run_b: str
    outcome: float
    slots: dict[str, float] = field(default_factory=dict)


def _slot_divergence(slot: Slot, run_a: str, run_b: str, compare: Comparator) -> float:
    ea, eb = slot.event(run_a), slot.event(run_b)
    if ea is None and eb is None:
        return 0.0
    if ea is None or eb is None:
        return MISSING_DIVERGENCE
    return 1.0 - compare(ea.output, eb.output)


def pair_divergences(
    runs: Sequence[Run],
    *,
    outcome_comparator: Comparator | str | None = None,
    event_comparator: Comparator | str | None = None,
    slots: Sequence[Slot] | None = None,
) -> tuple[list[Slot], list[PairDivergence]]:
    """Build the per-pair divergence table for one task's runs."""
    runs = [r for r in runs if r.ok]
    slots = list(slots) if slots is not None else align_runs(runs)
    compare_outcome = resolve_comparator(outcome_comparator)
    compare_event = resolve_comparator(event_comparator)

    pairs: list[PairDivergence] = []
    for a, b in combinations(runs, 2):
        pairs.append(
            PairDivergence(
                run_a=a.id,
                run_b=b.id,
                outcome=1.0 - compare_outcome(a.outcome, b.outcome),
                slots={
                    slot.key: _slot_divergence(slot, a.id, b.id, compare_event)
                    for slot in slots
                },
            )
        )
    return slots, pairs

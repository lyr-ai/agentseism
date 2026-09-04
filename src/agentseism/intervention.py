"""Intervention contract (V1).

**Not implemented.** This module fixes the interface that V1 causal attribution
will use, so that the V0 trace format is shaped by it rather than retrofitted to
it. See DESIGN-INTERVENTION.md for the rationale and the resumption strategies.

V0 localizes by association and cannot separate an introduced variation from an
inherited one. Intervention is how that gets settled:

    P(Y)              observed outcome distribution
    P(Y | do(f = v))  outcome distribution with feature f forced to v
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol, runtime_checkable

from agentseism.types import Run

PROMPT_INJECTION = "prompt-injection"
REPLAY_SUBSTITUTION = "replay-with-substitution"
CHECKPOINT_RESUME = "checkpoint-resume"


@dataclass
class InterventionResult:
    """One forced run, plus whether the force actually took."""

    feature: str
    forced_value: Any
    strategy: str
    run: Run | None
    complied: bool
    """True when the forced value survived into the new run's projected feature.

    A non-compliant intervention measures the harness, not the agent, and must
    be excluded from effect estimates and reported separately.
    """
    notes: dict = field(default_factory=dict)


@runtime_checkable
class Intervenable(Protocol):
    """An adapter that can force an execution feature and resume.

    Adapters implement this in V1. A feature no strategy can force is not
    intervenable, and must be reported as such rather than silently scored by
    association alone.
    """

    def intervention_strategies(self) -> tuple[str, ...]:
        """Strategies this adapter supports, most faithful first."""

    def intervene(
        self, run: Run, feature: str, value: Any, *, strategy: str | None = None
    ) -> InterventionResult:
        """Re-execute ``run`` with ``feature`` forced to ``value``."""

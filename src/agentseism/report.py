"""Scan result and its text rendering (DESIGN.md §19)."""

from __future__ import annotations

from dataclasses import dataclass, field
from statistics import median
from typing import Sequence

from agentseism.attribution import WeakPoint
from agentseism.types import Experiment
from agentseism.variation import TaskVariation

RULE = "═" * 46
THIN = "─" * 46
HIGH_VARIATION = 0.25
"""A task is reported as high-variation above this level. A reporting threshold,
not a claim about acceptable instability."""


@dataclass
class ScanReport:
    agent_id: str
    experiment: Experiment
    tasks: list[TaskVariation] = field(default_factory=list)
    weak_points: list[WeakPoint] = field(default_factory=list)
    excluded_slots: list[str] = field(default_factory=list)
    high_variation_threshold: float = HIGH_VARIATION

    @property
    def n_runs(self) -> int:
        return len(self.experiment.runs)

    @property
    def n_errors(self) -> int:
        return sum(1 for r in self.experiment.runs if not r.ok)

    @property
    def consistency(self) -> float:
        values = [t.consistency for t in self.tasks]
        return sum(values) / len(values) if values else 1.0

    @property
    def median_consistency(self) -> float:
        return median([t.consistency for t in self.tasks]) if self.tasks else 1.0

    @property
    def unstable_tasks(self) -> list[TaskVariation]:
        return sorted(
            [t for t in self.tasks if t.variation > self.high_variation_threshold],
            key=lambda t: -t.variation,
        )

    def top_weak_points(self, n: int = 5) -> list[WeakPoint]:
        return self.weak_points[:n]

    def __str__(self) -> str:
        return self.render()

    def render(self, *, top: int = 3) -> str:
        lines = [
            "AgentSeism",
            RULE,
            "",
            f"Agent: {self.agent_id}",
            "",
            f"{'Tasks':<22}{len(self.tasks):>8}",
            f"{'Executions':<22}{self.n_runs:>8}",
        ]
        if self.n_errors:
            lines.append(f"{'Failed executions':<22}{self.n_errors:>8}")
        if self.n_runs and self.n_errors == self.n_runs:
            lines += ["", "Every execution failed; there is nothing to analyze.", ""]
            return "\n".join(lines)
        lines += [
            "",
            "Behavioral consistency",
            f"{'':<22}{self.consistency:>7.0%}",
            "",
            "High-variation tasks",
            f"{'':<22}{len(self.unstable_tasks):>8}",
            "",
        ]

        unstable = self.unstable_tasks[:top]
        if unstable:
            lines += ["", "Most unstable tasks", THIN, ""]
            for task in unstable:
                modes = ", ".join(f"{m.share:.0%}" for m in task.modes[:3])
                lines.append(
                    f"  {task.task_id:<16}variation {task.variation:.2f}"
                    + (f"   modes {modes}" if len(task.modes) > 1 else "")
                )
            lines.append("")

        if self.weak_points:
            lines += ["", "Top Behavioral Weak Points", THIN, ""]
            for i, wp in enumerate(self.top_weak_points(top), start=1):
                lines += [
                    f"{i}. Event group: {wp.label}",
                    "",
                    f"   {'Local variation':<26}{wp.local_variation:.2f}",
                    f"   {'Downstream propagation':<26}{wp.propagation:.2f}",
                    f"   {'Outcome association':<26}{wp.outcome_association:.2f}",
                    "",
                    f"   {'Weak-point score':<26}{wp.score:.2f}",
                ]
                if wp.score < 0.05:
                    lines += ["", "   Low behavioral impact."]
                lines.append("")
            lines += [
                "Association, not causation: these points co-vary with outcome",
                "variation across runs. Confirm with a controlled intervention.",
                "",
            ]
            if self.excluded_slots:
                lines += [
                    f"Excluded from ranking: {', '.join(self.excluded_slots)} "
                    "(recorded as the outcome, not a step toward it).",
                    "",
                ]
        elif any(r.events for r in self.experiment.runs):
            lines += ["", "No aligned execution points scored above zero.", ""]
        else:
            lines += [
                "",
                "No trace recorded: outcome-level analysis only.",
                "Instrument the agent with a TraceCollector for weak-point attribution.",
                "",
            ]

        return "\n".join(lines)

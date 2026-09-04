"""Scan result and its text rendering (DESIGN.md §19)."""

from __future__ import annotations

from dataclasses import dataclass, field
from statistics import median
from typing import Sequence

from agentseism.localization import Ranking, WeakPoint
from agentseism.localization.weakpoints import AGGREGATE_MODE, POSITIONED_MODE
from agentseism.features import FeatureSchema
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
    ranking: Ranking | None = None
    schema: FeatureSchema | None = None
    high_variation_threshold: float = HIGH_VARIATION

    @property
    def weak_points(self) -> list[WeakPoint]:
        return self.ranking.weak_points if self.ranking else []

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

    def _render_group(self, group: list[WeakPoint]) -> list[str]:
        lines: list[str] = []
        for i, wp in enumerate(group, start=1):
            lines += [
                f"{i}. Execution feature: {wp.name}",
                "",
                f"   {'Local variation':<26}{wp.local_variation:.2f}",
                f"   {'Downstream propagation':<26}{wp.propagation_text}",
                f"   {'Outcome association':<26}{wp.outcome_association:.2f}",
                "",
                f"   {'Weak-point score':<26}{wp.score:.2f}",
            ]
            if len(wp.family_members) > 1:
                others = [m for m in wp.family_members if m != wp.name]
                lines += [
                    "",
                    f"   Feature family with: {', '.join(others)}",
                    "   These co-vary; count them as one finding, not several.",
                ]
            if wp.score < 0.05:
                lines += ["", "   Low behavioral impact."]
            lines.append("")
        return lines

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
            groups = [
                ("Positioned execution features", POSITIONED_MODE, self.ranking.positioned),
                ("Trajectory aggregates", AGGREGATE_MODE, self.ranking.aggregates),
            ]
            for title, mode, group in groups:
                if not group:
                    continue
                lines += ["", f"{title}   (score = {mode})", THIN, ""]
                lines += self._render_group(group[:top])
            if self.ranking.mixed:
                lines += [
                    "Scores are comparable within a group, not across them: only a",
                    "positioned feature carries a propagation factor.",
                    "",
                ]
            lines += [
                "Localization, not causal attribution: these features co-vary with",
                "outcome variation across runs. A feature that merely inherits the",
                "variation looks the same. Confirm with a controlled intervention.",
                "",
            ]
            if self.ranking and self.ranking.excluded:
                lines += [
                    f"Excluded from attribution: {', '.join(self.ranking.excluded)} "
                    "(declared outcome, not a step toward it).",
                    "",
                ]
            if self.schema:
                lines += [f"Feature schema: {self.schema.version}", ""]
        elif any(r.features for r in self.experiment.runs):
            lines += ["", "No execution feature scored above zero.", ""]
        else:
            lines += [
                "",
                "No trace recorded: outcome-level analysis only.",
                "Instrument the agent and give scan() a projector to localize weak points.",
                "",
            ]

        return "\n".join(lines)

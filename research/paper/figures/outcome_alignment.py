"""Twenty runs of one task, aligned on absolute step, coloured by outcome.

Exploratory and post-hoc: four failures. The figure exists to show where the
sample can and cannot say anything, which is as much of its job as showing the
trajectories.
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.lines import Line2D

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from experiments.coding.align_outcomes import gather

BG = "#ffffff"
INK = "#1b1b1d"
MUTED = "#9a9a9f"
RULE = "#dcdce0"
PASS_C = "#2f7f5b"
FAIL_C = "#c8452e"
EDIT = "#2f6f8f"
TEST = "#b3762a"


def main() -> None:
    runs_dir = os.environ.get("RUNS_ROOT", str(ROOT / "data/runs"))
    labels = json.loads((ROOT / "paper/manifests/correctness_labels.json").read_text())["rows"]
    manifest = json.loads((ROOT / "paper/manifests/h2_phase_a1.json").read_text())
    runs = gather(runs_dir, labels, manifest)
    runs.sort(key=lambda r: (r["correct"], r["arm"] or "", r["run"]))

    fig, ax = plt.subplots(figsize=(13, 8))
    fig.patch.set_facecolor(BG)
    ax.set_facecolor(BG)

    longest = max(len(r["steps"]) for r in runs)
    for index, run in enumerate(runs):
        y = len(runs) - index
        colour = PASS_C if run["correct"] else FAIL_C
        steps = run["steps"]
        ax.plot([1, len(steps)], [y, y], color=RULE, lw=1.1, zorder=1)
        for s in steps:
            if s["source_changed"]:
                ax.plot(s["step"], y, "|", ms=9, color=EDIT, mew=1.8, zorder=3)
            if s["is_suite_test"]:
                ax.plot(s["step"], y, ".", ms=4.5, color=TEST, zorder=2)
            if s["is_revert"]:
                ax.plot(s["step"], y, "x", ms=5, color=MUTED, mew=1.2, zorder=3)
        ax.plot(len(steps), y, "o", ms=7, color=colour, zorder=4,
                markeredgecolor="white", markeredgewidth=1.2)
        if run["fork"]:
            ax.plot(run["fork"], y, "^", ms=5, color=INK, zorder=5)
        ax.text(-1.5, y, run["run"], va="center", ha="right", fontsize=8.5,
                color=colour, family="monospace")

    ax.axvspan(0, 10, color="#f0f0f3", zorder=0)
    ax.text(5, len(runs) + 1.4, "pseudo-replicated\n7 distinct histories",
            ha="center", va="bottom", fontsize=8.5, color=MUTED, linespacing=1.4)
    ax.axvline(13.5, color=FAIL_C, lw=1.0, ls=(0, (4, 3)), zorder=1)
    ax.text(14.4, len(runs) + 1.4, "candidate horizon h≈14\ncumulative edits separate",
            ha="left", va="bottom", fontsize=8.5, color=FAIL_C, linespacing=1.4)

    ax.set_xlim(-9, longest + 2)
    ax.set_ylim(0.3, len(runs) + 3.2)
    ax.set_yticks([])
    ax.set_xlabel("absolute agent step", fontsize=10, color=INK, labelpad=6)
    for side in ("top", "right", "left"):
        ax.spines[side].set_visible(False)
    ax.spines["bottom"].set_color(RULE)
    ax.tick_params(axis="x", colors=MUTED, labelsize=9)

    ax.text(-9, len(runs) + 2.5, "Twenty runs of one task, by outcome",
            fontsize=15, color=INK, va="bottom", ha="left")

    handles = [
        Line2D([], [], marker="|", ls="", color=EDIT, mew=1.8, ms=9, label="source edit"),
        Line2D([], [], marker=".", ls="", color=TEST, ms=6, label="repo test suite run"),
        Line2D([], [], marker="x", ls="", color=MUTED, ms=5, label="revert"),
        Line2D([], [], marker="^", ls="", color=INK, ms=5, label="fork point"),
        Line2D([], [], marker="o", ls="", color=PASS_C, ms=7, label="correct"),
        Line2D([], [], marker="o", ls="", color=FAIL_C, ms=7, label="incorrect"),
    ]
    ax.legend(handles=handles, loc="upper left", bbox_to_anchor=(0.0, -0.08),
              frameon=False, fontsize=8.8, labelcolor=MUTED, ncol=6,
              handletextpad=0.5, columnspacing=1.8)
    fig.text(0.125, -0.02,
             "Exploratory and post-hoc: 16 correct, 4 incorrect. Continuations are "
             "shown on absolute steps with their donor prefix included, so every run "
             "in an arm is identical before its fork point.",
             fontsize=8, color=MUTED, va="top", ha="left")

    out = ROOT / "paper/figures"
    fig.savefig(out / "outcome_alignment.svg", format="svg", bbox_inches="tight", facecolor=BG)
    fig.savefig(out / "outcome_alignment.png", dpi=200, bbox_inches="tight", facecolor=BG)
    print(f"{len(runs)} runs plotted; wrote paper/figures/outcome_alignment.svg and .png")


if __name__ == "__main__":
    main()

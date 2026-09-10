"""The pytest attractor, drawn from probe data and nothing else.

Every mark on this figure is a recorded `tracked_diff_hash` from an
AgentSeism probe. Nothing is illustrative, nothing is idealised, and nothing is
labelled correct or incorrect -- these runs have no correctness label yet, and
drawing one would be inventing the result the figure is supposed to show.

What is drawn: one row per execution, the x axis in agent steps, a marker
wherever the tracked source state changes. The shared state is picked out
because it is the point of the figure; the empty diff is greyed because
returning to a clean tree is where every run begins and is not a meeting;
terminal states get their own colour per distinct hash, so runs that ended
alike look alike.

Runs that never reach the shared state are drawn too. One of the thirteen does
not, and leaving it out would turn a measurement into a poster.
"""

from __future__ import annotations

import hashlib
import json
import os
import sys
from glob import glob
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.lines import Line2D

RUNS = os.environ.get("RUNS_ROOT", "")
TASK = "pytest-dev__pytest-10051"
S = "400ed4047a8253a9cc7268069f079099484f0d279b7bd225a309da40609896c0"
EMPTY = hashlib.sha256(b"").hexdigest()

BATCHES = [("primary · 32k", "exp1"),
           ("batch A0 · 128k", "h2_phase_a"),
           ("batch A1 · 128k", "h2_phase_a1")]

INK = "#1b1b1d"
MUTED = "#9a9a9f"
RULE = "#d8d8dc"
ACCENT = "#c8452e"
TERMINAL = ["#2f6f8f", "#4b7f52", "#8a5fa8", "#b3762a", "#3f6d7a",
            "#7a5c3a", "#5a6ea8", "#8f4f6f", "#42806c", "#6b6b8f",
            "#a05a3a", "#4a7a8a"]


def load():
    rows = []
    for label, directory in BATCHES:
        for path in sorted(glob(f"{RUNS}/{directory}/{TASK}__r*.probe.jsonl")):
            run = os.path.basename(path).split("__r")[-1].split(".")[0]
            steps = [json.loads(line) for line in open(path)]
            rows.append({"batch": label, "run": f"r{run}", "steps": steps})
    return rows


def main() -> None:
    if not RUNS:
        sys.exit("set RUNS_ROOT to the directory holding exp1/ h2_phase_a/ h2_phase_a1/")
    rows = load()
    finals = []
    for row in rows:
        final = row["steps"][-1]["tracked_diff_hash"]
        if final not in finals:
            finals.append(final)
    colour = {h: TERMINAL[i % len(TERMINAL)] for i, h in enumerate(finals)}

    height = 0.62 * len(rows) + 2.6
    fig, ax = plt.subplots(figsize=(11, height))
    fig.patch.set_facecolor("white")
    ax.set_facecolor("white")

    longest = max(len(r["steps"]) for r in rows)
    y = len(rows)
    reached = revisits = 0
    for index, row in enumerate(rows):
        y = len(rows) - index
        steps = row["steps"]
        ax.plot([1, len(steps)], [y, y], color=RULE, lw=1.2, zorder=1,
                solid_capstyle="round")

        first_S = next((x["step"] for x in steps if x["tracked_diff_hash"] == S), None)
        if first_S is not None:
            reached += 1
        previous = None
        for step in steps:
            state = step["tracked_diff_hash"]
            if state == previous:
                continue
            previous = state
            x = step["step"]
            if state == S:
                revisits += x != first_S
                ax.plot(x, y, "o", ms=9.5, color=ACCENT, zorder=4,
                        markeredgecolor="white", markeredgewidth=1.4)
            elif state == EMPTY:
                ax.plot(x, y, "o", ms=4.5, color="white", zorder=3,
                        markeredgecolor=MUTED, markeredgewidth=1.1)
            else:
                ax.plot(x, y, "o", ms=5.5, color=MUTED, zorder=3)

        final = steps[-1]["tracked_diff_hash"]
        ax.plot(len(steps), y, "o", ms=10, color=colour[final], zorder=5,
                markeredgecolor="white", markeredgewidth=1.4)
        ax.text(len(steps) + 1.2, y, final[:8], va="center", ha="left",
                fontsize=8.5, color=colour[final], family="monospace")
        ax.text(-1.5, y, row["run"], va="center", ha="right", fontsize=9, color=INK)

    # batch bands, drawn on the left margin rather than as gridlines
    start = len(rows)
    for label, _ in BATCHES:
        count = sum(1 for r in rows if r["batch"] == label)
        top, bottom = start, start - count + 1
        ax.plot([-6.2, -6.2], [bottom - 0.32, top + 0.32], color=RULE, lw=2.4,
                solid_capstyle="round", clip_on=False)
        ax.text(-7.0, (top + bottom) / 2, label, va="center", ha="right",
                fontsize=9, color=MUTED, rotation=90)
        start -= count

    ax.set_xlim(-8, longest + 12)
    ax.set_ylim(0.3, len(rows) + 1.6)
    ax.set_xlabel("agent step", fontsize=10, color=INK, labelpad=8)
    ax.set_yticks([])
    for side in ("top", "right", "left"):
        ax.spines[side].set_visible(False)
    ax.spines["bottom"].set_color(RULE)
    ax.tick_params(axis="x", colors=MUTED, labelsize=9, length=3)

    ax.text(-8, len(rows) + 1.25, "Same source state, different futures",
            fontsize=17, color=INK, va="bottom", ha="left")
    ax.text(-8, len(rows) + 0.72,
            f"temperature 0 · one SWE-bench task · one model · "
            f"{reached} of {len(rows)} executions pass through the identical source state",
            fontsize=9.5, color=MUTED, va="bottom", ha="left")

    legend = [
        Line2D([], [], marker="o", ls="", ms=9, color=ACCENT,
               markeredgecolor="white", label=f"shared state  {S[:8]}"),
        Line2D([], [], marker="o", ls="", ms=5.5, color=MUTED, label="other source state"),
        Line2D([], [], marker="o", ls="", ms=4.5, color="white",
               markeredgecolor=MUTED, label="empty diff (clean tree)"),
        Line2D([], [], marker="o", ls="", ms=9, color=TERMINAL[0],
               markeredgecolor="white", label="final state (colour per distinct hash)"),
    ]
    # Below the axis, not inside it: at this row spacing an in-plot legend sits
    # on top of the last two executions.
    ax.legend(handles=legend, loc="upper left", bbox_to_anchor=(0.0, -0.055),
              frameon=False, fontsize=8.8, labelcolor=MUTED, ncol=4,
              handletextpad=0.6, columnspacing=2.2, borderaxespad=0)

    note = ("Each mark is a recorded tracked_diff_hash: the canonical git diff of the "
            "repository against the instance's base commit, sampled after every action.\n"
            "Marks appear where that state changes. No run is labelled correct or incorrect "
            "— these executions carry no correctness label.")
    if revisits:
        note += (f"\n{revisits} execution{'s' if revisits > 1 else ''} enter"
                 f"{'' if revisits > 1 else 's'} the shared state more than once: a run can "
                 f"leave it and come back.")
    ax.text(-8, -1.35, note, fontsize=8, color=MUTED, va="top", ha="left", linespacing=1.6)

    fig.tight_layout()
    out = Path("paper/figures")
    fig.savefig(out / "attractor.svg", format="svg", bbox_inches="tight",
                facecolor="white")
    fig.savefig(out / "attractor.png", dpi=220, bbox_inches="tight", facecolor="white")
    print(f"{len(rows)} executions, {reached} reach {S[:8]}, "
          f"{len(finals)} distinct final states")
    print("wrote paper/figures/attractor.svg and .png")


if __name__ == "__main__":
    main()

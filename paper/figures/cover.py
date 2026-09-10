"""Blog cover, second attempt: the finding, not the mood.

The first cover was an abstract with a slogan on it. It looked fine and said
nothing -- anyone can write "same state, different futures", so there is no
reason to click. The covers that work on engineering posts show the thing:
an annotated diagram, a chart with a punchline, a before and after.

So this one is the result. Three numbers on the left, and on the right the real
thirteen executions, stripped to what survives a thumbnail: no hashes, no axes,
no run labels. The geometry is the same probe data the paper figure uses.

Still no correctness marks. These runs carry no correctness label, and a cover
that implied one would be selling something the article cannot deliver.
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

RUNS = os.environ.get("RUNS_ROOT", "")
TASK = "pytest-dev__pytest-10051"
S = "400ed4047a8253a9cc7268069f079099484f0d279b7bd225a309da40609896c0"
EMPTY = hashlib.sha256(b"").hexdigest()
BATCHES = ["exp1", "h2_phase_a", "h2_phase_a1"]

BG = "#0a0b0f"
LINE = "#3d4a57"
ACCENT = "#ff7043"
TEXT = "#f2f3f5"
MUTED = "#7d858f"
ENDS = ["#7fb3d5", "#7fc8a9", "#b39ddb", "#e0b25f", "#8fb8c9", "#c9a88f",
        "#9fa8da", "#d99fb8", "#84c4ae", "#a5a5c9", "#d4a07a", "#8fb0c0"]

for family in ("Helvetica Neue", "Helvetica", "Arial"):
    if any(family.lower() in f.name.lower() for f in matplotlib.font_manager.fontManager.ttflist):
        plt.rcParams["font.family"] = family
        break


def load():
    rows = []
    for directory in BATCHES:
        for path in sorted(glob(f"{RUNS}/{directory}/{TASK}__r*.probe.jsonl")):
            rows.append([json.loads(line) for line in open(path)])
    return rows


def main() -> None:
    if not RUNS:
        sys.exit("set RUNS_ROOT")
    runs = load()
    finals = []
    for steps in runs:
        final = steps[-1]["tracked_diff_hash"]
        if final not in finals:
            finals.append(final)
    colour = {h: ENDS[i % len(ENDS)] for i, h in enumerate(finals)}
    reached = sum(1 for s in runs if any(x["tracked_diff_hash"] == S for x in s))

    fig = plt.figure(figsize=(16, 9), dpi=100)
    fig.patch.set_facecolor(BG)

    ax = fig.add_axes([0.455, 0.10, 0.525, 0.80])
    ax.set_facecolor(BG)
    ax.axis("off")
    longest = max(len(s) for s in runs)

    for index, steps in enumerate(runs):
        y = len(runs) - index
        ax.plot([1, len(steps)], [y, y], color=LINE, lw=1.5, zorder=1,
                solid_capstyle="round")
        # The runs sit on the shared state for many consecutive steps, so a marker
        # per step draws a caterpillar. Draw the span they hold it instead: the
        # segment says when they arrived and how long they stayed, which is more
        # of the finding than a dot is.
        spans, start = [], None
        for step in steps:
            here = step["tracked_diff_hash"] == S
            if here and start is None:
                start = step["step"]
            elif not here and start is not None:
                spans.append((start, step["step"] - 1)); start = None
        if start is not None:
            spans.append((start, steps[-1]["step"]))
        for a, b in spans:
            for width, alpha in ((11, 0.10), (7, 0.20)):
                ax.plot([a, max(b, a + 0.4)], [y, y], color=ACCENT, lw=width,
                        alpha=alpha, solid_capstyle="round", zorder=2)
            ax.plot([a, max(b, a + 0.4)], [y, y], color=ACCENT, lw=3.4,
                    solid_capstyle="round", zorder=3)
        final = steps[-1]["tracked_diff_hash"]
        # Big enough to survive a feed thumbnail: the scatter of these dots
        # against the alignment of the orange bars is the whole cover.
        ax.plot(len(steps), y, "o", ms=11, color=colour[final], zorder=5)

    ax.set_xlim(-2, longest + 4)
    ax.set_ylim(0.2, len(runs) + 0.8)

    fig.text(0.055, 0.855, "S A M E   T A S K      S A M E   M O D E L      "
                           "T E M P E R A T U R E   =   0",
             fontsize=10.5, color=MUTED, va="center")

    rows = [(f"{len(runs)}", "independent executions", TEXT),
            ("1", "shared source state", ACCENT),
            (f"{len(finals)}", "different endings", TEXT)]
    # Labels on a fixed column rather than offset by digit count: "1" and "13"
    # are different widths and the ragged left edge was the tell.
    y = 0.655
    for number, label, tone in rows:
        fig.text(0.165, y, number, fontsize=76, color=tone, va="center", ha="right")
        fig.text(0.190, y - 0.008, label, fontsize=19, color=MUTED,
                 va="center", ha="left")
        y -= 0.175

    fig.text(0.055, 0.135, "Same state. Different futures.",
             fontsize=27, color=TEXT, va="center")
    fig.text(0.055, 0.072,
             f"{reached} of {len(runs)} executions pass through the identical source state",
             fontsize=13.5, color=MUTED, va="center")

    out = Path("paper/figures")
    fig.savefig(out / "cover.png", dpi=100, facecolor=BG)
    fig.savefig(out / "cover.svg", format="svg", facecolor=BG)
    print(f"{len(runs)} runs, {reached} reach S, {len(finals)} distinct finals")
    print("wrote paper/figures/cover.png (1600x900) and cover.svg")


if __name__ == "__main__":
    main()

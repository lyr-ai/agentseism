"""Cover as a research poster: three findings, all from recorded data.

The earlier covers were one idea each -- a slogan, then a single chart. This one
carries what the work actually found, because a cover for an engineering post is
read by people deciding whether the article has anything in it.

    left     one task, thirteen executions: they meet, they end apart
    middle   how fast agreement with a donor decays, by granularity
    right    across ten tasks, the fate of divergence differs by task

Every number is computed here from probe files and the frozen analysis modules,
not typed in. Nothing is marked correct or incorrect: these runs carry no
correctness label.
"""

from __future__ import annotations

import collections
import hashlib
import importlib.util
import itertools
import json
import os
import sys
from glob import glob
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.lines import Line2D

ROOT = Path(__file__).resolve().parents[2]
RUNS = os.environ.get("RUNS_ROOT", "")
TASK = "pytest-dev__pytest-10051"
S = "400ed4047a8253a9cc7268069f079099484f0d279b7bd225a309da40609896c0"

BG = "#0a0b0f"
PANEL = "#101218"
LINE = "#39434f"
TEXT = "#f2f3f5"
MUTED = "#7d858f"
DIM = "#565e69"
ACCENT = "#ff7043"
BLUE = "#7fb3d5"
GREEN = "#7fc8a9"
ENDS = ["#7fb3d5", "#7fc8a9", "#b39ddb", "#e0b25f", "#8fb8c9", "#c9a88f",
        "#9fa8da", "#d99fb8", "#84c4ae", "#a5a5c9", "#d4a07a", "#8fb0c0"]
TOPO = {"absorbed": GREEN, "persistent": BLUE, "re-divergence": ACCENT}

for family in ("Helvetica Neue", "Helvetica", "Arial"):
    if any(family.lower() in f.name.lower() for f in matplotlib.font_manager.fontManager.ttflist):
        plt.rcParams["font.family"] = family
        break


def load_module(name, relative):
    spec = importlib.util.spec_from_file_location(name, ROOT / relative)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def frame(ax, title, number, caption):
    ax.set_facecolor(PANEL)
    for side in ax.spines.values():
        side.set_visible(False)
    ax.tick_params(colors=MUTED, labelsize=8.5, length=2.5)
    box = ax.get_position()
    ax.figure.text(box.x0, box.y1 + 0.088, number, fontsize=13, color=ACCENT,
                   va="center", family="monospace")
    ax.figure.text(box.x0 + 0.022, box.y1 + 0.088, title, fontsize=14.5, color=TEXT,
                   va="center")
    # Captions are wrapped by hand rather than by width: at this panel pitch an
    # unwrapped line runs into the next panel's title, and the right-hand one
    # runs off the canvas entirely.
    ax.figure.text(box.x0, box.y1 + 0.038, caption, fontsize=9.6, color=MUTED,
                   va="center", linespacing=1.55)


def panel_attractor(ax):
    runs = []
    for directory in ("exp1", "h2_phase_a", "h2_phase_a1"):
        for path in sorted(glob(f"{RUNS}/{directory}/{TASK}__r*.probe.jsonl")):
            runs.append([json.loads(line) for line in open(path)])
    finals = list(dict.fromkeys(s[-1]["tracked_diff_hash"] for s in runs))
    colour = {h: ENDS[i % len(ENDS)] for i, h in enumerate(finals)}
    reached = sum(1 for s in runs if any(x["tracked_diff_hash"] == S for x in s))

    for index, steps in enumerate(runs):
        y = len(runs) - index
        ax.plot([1, len(steps)], [y, y], color=LINE, lw=1.1, zorder=1)
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
            ax.plot([a, max(b, a + 0.5)], [y, y], color=ACCENT, lw=6.5, alpha=0.18,
                    solid_capstyle="round", zorder=2)
            ax.plot([a, max(b, a + 0.5)], [y, y], color=ACCENT, lw=2.6,
                    solid_capstyle="round", zorder=3)
        ax.plot(len(steps), y, "o", ms=6, color=colour[steps[-1]["tracked_diff_hash"]], zorder=4)

    ax.set_xlim(-1, max(len(s) for s in runs) + 3)
    ax.set_ylim(0.3, len(runs) + 0.7)
    ax.set_yticks([])
    ax.set_xlabel("agent step", fontsize=9, color=MUTED, labelpad=3)
    ax.spines["bottom"].set_visible(True)
    ax.spines["bottom"].set_color(LINE)
    return reached, len(runs), len(finals)


def panel_decay(ax):
    data = json.loads((ROOT / "paper/manifests/h3_pytest_exploratory.json").read_text())
    for arm, style, alpha in (("A", "-", 1.0), ("B", (0, (3, 2)), 0.75)):
        for grain, colour in (("signature", BLUE), ("command", ACCENT)):
            points = [p for p in data["censored"][arm]["points"][grain]
                      if p["survival"] is not None and p["h"] <= 16]
            ax.plot([p["h"] for p in points], [p["survival"] for p in points],
                    ls=style, color=colour, lw=2.0, alpha=alpha, solid_capstyle="round")
    ax.set_xlim(0.6, 16.4)
    ax.set_ylim(-0.04, 1.06)
    ax.set_yticks([0, 0.5, 1.0])
    ax.set_yticklabels(["0", "½", "1"])
    ax.set_xticks([1, 4, 8, 12, 16])
    ax.set_xlabel("steps after the fork", fontsize=9, color=MUTED, labelpad=3)
    ax.axhline(0.5, color=DIM, lw=0.8, ls=(0, (2, 3)), zorder=0)
    ax.text(15.9, 0.545, "half", fontsize=8, color=DIM, ha="right")
    ax.text(3.15, 0.86, "exact command", fontsize=9.5, color=ACCENT)
    ax.text(8.4, 0.62, "action type", fontsize=9.5, color=BLUE)
    ax.legend(handles=[Line2D([], [], color=MUTED, lw=1.6, label="donor A"),
                       Line2D([], [], color=MUTED, lw=1.6, ls=(0, (3, 2)), label="donor B")],
              loc="upper right", frameon=False, fontsize=8.2, labelcolor=MUTED,
              handlelength=1.8, borderaxespad=0.3)


def panel_topology(ax):
    divergence = load_module("divergence_mod", "experiments/coding/divergence.py")
    runs = divergence.load(f"{RUNS}/exp1")
    counts = {}
    for task in sorted(runs):
        usable = [r for r in sorted(runs[task]) if runs[task][r]["exit"] == "Submitted"]
        if len(usable) < 2:
            continue
        labels = collections.Counter(
            divergence.classify(runs[task][x], runs[task][y])["topology"]
            for x, y in itertools.combinations(usable, 2))
        counts[task.split("__")[-1].split("-")[0]] = labels

    order = sorted(counts, key=lambda t: (-counts[t].get("re-divergence", 0),
                                          -counts[t].get("persistent", 0)))
    for index, task in enumerate(order):
        y = len(order) - index
        left = 0
        for name, colour in TOPO.items():
            width = counts[task].get(name, 0)
            if width:
                ax.barh(y, width, left=left, height=0.56, color=colour, zorder=2)
                left += width
        ax.text(-0.25, y, task, ha="right", va="center", fontsize=9, color=MUTED)
    ax.set_xlim(0, 3.15)
    ax.set_ylim(0.3, len(order) + 0.7)
    ax.set_yticks([])
    ax.set_xticks([0, 1, 2, 3])
    ax.set_xlabel("pairs of runs", fontsize=9, color=MUTED, labelpad=3)
    ax.spines["bottom"].set_visible(True)
    ax.spines["bottom"].set_color(LINE)
    total = collections.Counter()
    for c in counts.values():
        total.update(c)
    return total


def main() -> None:
    if not RUNS:
        sys.exit("set RUNS_ROOT")
    fig = plt.figure(figsize=(16, 9), dpi=100)
    fig.patch.set_facecolor(BG)

    top, height = 0.125, 0.50
    ax_a = fig.add_axes([0.045, top, 0.265, height])
    ax_b = fig.add_axes([0.395, top, 0.250, height])
    ax_c = fig.add_axes([0.760, top, 0.200, height])

    reached, n_runs, n_finals = panel_attractor(ax_a)
    panel_decay(ax_b)
    total = panel_topology(ax_c)

    frame(ax_a, "They meet, then end apart", "01",
          f"{n_runs} executions of one task, three batches\n"
          f"{reached} hold one identical source state · {n_finals} distinct endings")
    frame(ax_b, "Agreement decays with horizon", "02",
          "continuations forked from that state, compared\n"
          "against the execution they were forked from")
    frame(ax_c, "The fate differs by task", "03",
          f"{sum(total.values())} pairs of runs, 9 tasks\n"
          + " · ".join(f"{v} {k}" for k, v in total.most_common()))

    fig.text(0.045, 0.945, "S A M E   T A S K      S A M E   M O D E L      "
                           "T E M P E R A T U R E   =   0",
             fontsize=10.5, color=MUTED, va="center")
    fig.text(0.045, 0.872, "Same state. Different futures.",
             fontsize=40, color=TEXT, va="center")
    fig.text(0.045, 0.807,
             "Reproducibility in long-horizon agent execution is not one number: "
             "it depends on how far you look and how closely.",
             fontsize=14, color=MUTED, va="center")

    handles = [Line2D([], [], marker="s", ls="", ms=8, color=c, label=k)
               for k, c in TOPO.items()]
    fig.legend(handles=handles, loc="lower right", bbox_to_anchor=(0.962, 0.040),
               frameon=False, fontsize=9.5, labelcolor=MUTED, ncol=3,
               handletextpad=0.5, columnspacing=1.6)
    fig.text(0.045, 0.050,
             "Every value computed from AgentSeism probe records: the canonical git diff "
             "of the repository, sampled after each action.\nNo execution is labelled "
             "correct or incorrect — these runs carry no correctness label.",
             fontsize=8.5, color=DIM, va="center", linespacing=1.6)

    out = ROOT / "paper/figures"
    fig.savefig(out / "poster.png", dpi=100, facecolor=BG)
    fig.savefig(out / "poster.svg", format="svg", facecolor=BG)
    print(f"panel 1: {n_runs} runs, {reached} reach S, {n_finals} finals")
    print(f"panel 3: {dict(total)}")
    print("wrote paper/figures/poster.png (1600x900) and poster.svg")


if __name__ == "__main__":
    main()

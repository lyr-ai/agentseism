"""Blog cover. A diagram, not a measurement.

The empirical figure next to it carries the evidence -- thirteen real
executions, real hashes, real steps. This one carries a question, and it is
drawn rather than measured: the line count and the spacing are chosen for
legibility at thumbnail size, not read off the data.

It is kept honest by what it refuses to say. No tick marks, no failure marks,
no hashes, no counts, no claim about which future is right. The runs behind
this work carry no correctness label, so a cover that implied one would be
promising something the article cannot deliver.
"""

from __future__ import annotations

from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

BG = "#0a0b0f"
LINE = "#5c6b7a"
GLOW = "#7fa6c9"
ACCENT = "#ff7043"
TEXT = "#f2f3f5"
MUTED = "#7d858f"

for family in ("Helvetica Neue", "Helvetica", "Arial"):
    if any(family.lower() in f.name.lower() for f in matplotlib.font_manager.fontManager.ttflist):
        plt.rcParams["font.family"] = family
        break


def ease(a: float, b: float, n: int = 220) -> tuple[np.ndarray, np.ndarray]:
    """A curve that leaves flat and arrives flat, so the node reads as a meeting."""
    t = np.linspace(0, 1, n)
    return t, a + (b - a) * (1 - np.cos(np.pi * t)) / 2


def main() -> None:
    fig = plt.figure(figsize=(16, 9), dpi=100)
    fig.patch.set_facecolor(BG)
    ax = fig.add_axes([0, 0, 1, 1])
    ax.set_facecolor(BG)
    ax.set_xlim(0, 1)
    ax.set_ylim(0, 1)
    ax.axis("off")

    node = (0.5, 0.665)
    left, right = 0.085, 0.915
    incoming = np.array([0.80, 0.755, 0.71, 0.62, 0.575, 0.53])
    # Wider than the fan on the left: what follows the meeting is more dispersed
    # than what preceded it, which is the one structural fact the cover borrows.
    outgoing = np.array([0.86, 0.79, 0.725, 0.605, 0.54, 0.47])

    def draw(x0, x1, y0, y1, warm):
        t, y = ease(y0, y1)
        x = x0 + (x1 - x0) * t
        # Three passes of decreasing width: the halo has to survive being scaled
        # down to a LinkedIn thumbnail, where a single hairline disappears.
        for width, alpha in ((9.0, 0.035), (5.0, 0.065), (2.6, 0.12)):
            ax.plot(x, y, lw=width, color=GLOW, alpha=alpha, solid_capstyle="round",
                    zorder=2)
        ax.plot(x, y, lw=1.5, color=ACCENT if warm else LINE,
                alpha=0.95 if warm else 0.82, solid_capstyle="round", zorder=3)

    for index, y0 in enumerate(incoming):
        draw(left, node[0], y0, node[1], warm=index == 2)
    for index, y1 in enumerate(outgoing):
        draw(node[0], right, node[1], y1, warm=index == 3)

    # The node is the whole picture: it is where the reader is meant to stop.
    for radius, alpha in ((40, 0.035), (28, 0.06), (18, 0.11), (11, 0.22)):
        ax.plot(*node, "o", ms=radius, color=ACCENT, alpha=alpha, zorder=4)
    ax.plot(*node, "o", ms=10.5, color=ACCENT, zorder=5)
    ax.plot(*node, "o", ms=4.2, color="#ffffff", zorder=6)

    ax.text(0.5, 0.925, "S A M E   T A S K      S A M E   M O D E L      "
                        "T E M P E R A T U R E   =   0",
            ha="center", va="center", fontsize=11.5, color=MUTED, zorder=7)

    ax.text(0.5, 0.325, "Same State.", ha="center", va="center",
            fontsize=64, color=TEXT, zorder=7)
    ax.text(0.5, 0.205, "Different Futures.", ha="center", va="center",
            fontsize=64, color=ACCENT, zorder=7)
    ax.text(0.5, 0.085, "What stochastic agent executions reveal about reliability",
            ha="center", va="center", fontsize=15, color=MUTED, zorder=7)

    out = Path("paper/figures")
    fig.savefig(out / "hero.png", dpi=100, facecolor=BG)
    fig.savefig(out / "hero.svg", format="svg", facecolor=BG)
    print("wrote paper/figures/hero.png (1600x900) and hero.svg")


if __name__ == "__main__":
    main()

"""Operating characteristics of the surface-2 dual gate. No API, no runs.

    .venv/bin/python analysis/ci_v1/operating_characteristics.py > out.md

Gate 2 (capability regression) is evaluated **exactly**, by enumerating both
arms' binomial outcomes through the product's own `capability.evaluate`.

Gate 1 (broad reliability) is simulated. The product's bootstrap is seeded
(`random.Random(0)`), so its resample indices depend only on K. They are
regenerated here with the identical call sequence, and the percentile interval
is computed in exact integer arithmetic. `check_equivalence` then compares this
engine decision by decision against the product's `_paired_bootstrap`, and the
script refuses to print anything if a single decision differs.

Across n, the frozen rule is applied mechanically: eligibility is the fraction
0.875, the warning is 0.375, and the minimum evidence is n trials. At n = 5 and
n = 6 that means a perfect baseline is required.
"""

from __future__ import annotations

import copy
import random
from functools import lru_cache
from math import comb

import numpy as np

from agentseism import capability as cap
from agentseism.capability import TaskCounts as T
from agentseism.cli import _paired_bootstrap

NS = (5, 6, 8, 10)
BOOT, SEED = 2000, 0
SIMS = 4000
THR = 0.10
RNG = np.random.default_rng(20260925)


# ── gate 2, exact ─────────────────────────────────────────────────────────
def spec(n: int) -> dict:
    s = copy.deepcopy(cap.DEFAULTS)
    s["minimum_evidence"] = {"trials_per_condition": n}
    return s


@lru_cache(maxsize=None)
def fires(b: int, c: int, n: int, k: int) -> bool:
    """Does the product gate fire on one task with these counts, at K?"""
    others = {f"o{i}": T(n, n, n, n) for i in range(k - 1)}
    return "t" in cap.evaluate(spec(n), others | {"t": T(b, n, c, n)})["fired"]


def binom(n: int, x: int, p: float) -> float:
    return comb(n, x) * p ** x * (1 - p) ** (n - x)


def g2_prob(pb: float, pc: float, n: int, k: int) -> float:
    """P(gate 2 fires on one task), over both arms' sampling, eligibility included."""
    return sum(binom(n, b, pb) * binom(n, c, pc)
               for b in range(n + 1) for c in range(n + 1) if fires(b, c, n, k))


def g2_worst_null(n: int, k: int) -> tuple[float, float]:
    return max((g2_prob(p, p, n, k), p) for p in np.linspace(0.01, 0.99, 99))


def min_drop(n: int, k: int, base: int) -> float | None:
    got = [(base - c) / n for c in range(n + 1) if fires(base, c, n, k)]
    return min(got) if got else None


# ── gate 1, simulated with the product's exact bootstrap ──────────────────
@lru_cache(maxsize=None)
def boot_idx(k: int) -> np.ndarray:
    rng = random.Random(SEED)
    return np.array([[rng.randrange(k) for _ in range(k)] for _ in range(BOOT)])


def g1_fires(delta: np.ndarray, n: int) -> np.ndarray:
    """delta: (S, K) integer candidate-minus-baseline successes per task.

    Fires iff mean <= -0.10 and the upper percentile <= -0.10, decided exactly:
    a resample's mean is sum / (n K), and `sum / (n K) <= -1/10` is
    `10 sum <= -n K`.
    """
    s, k = delta.shape
    point = delta.sum(axis=1)
    out = np.empty(s, dtype=bool)
    idx = boot_idx(k)
    hi_i = int(.975 * BOOT) - 1
    for a in range(0, s, 500):
        blk = delta[a:a + 500]
        sums = blk[:, idx].sum(axis=2)
        hi = np.sort(sums, axis=1)[:, hi_i]
        out[a:a + 500] = (10 * point[a:a + 500] <= -n * k) & (10 * hi <= -n * k)
    return out


def check_equivalence(cases: int = 300) -> int:
    """Decision by decision against the product. Returns the case count."""
    rng = random.Random(1)
    for _ in range(cases):
        n, k = rng.choice(NS), rng.choice((4, 5, 7, 10))
        b = [rng.randint(0, n) for _ in range(k)]
        c = [rng.randint(0, n) for _ in range(k)]
        base = {f"t{i}": [1.0] * b[i] + [0.0] * (n - b[i]) for i in range(k)}
        cand = {f"t{i}": [1.0] * c[i] + [0.0] * (n - c[i]) for i in range(k)}
        eff, lo, hi = _paired_bootstrap(base, cand)
        product = eff <= -THR and hi <= -THR
        # product keys are sorted task names; mirror that order
        order = sorted(base)
        d = np.array([[c[int(t[1:])] - b[int(t[1:])] for t in order]])
        assert bool(g1_fires(d, n)[0]) == product, (n, k, b, c, eff, hi)
    return cases


def sim(pb: np.ndarray, pc: np.ndarray, n: int, sims: int = SIMS):
    """Draw both arms; return (gate 1 fired, gate 2 fired on any task)."""
    k = len(pb)
    b = RNG.binomial(n, pb, size=(sims, k))
    c = RNG.binomial(n, pc, size=(sims, k))
    g1 = g1_fires((c - b).astype(np.int32), n)
    g2 = np.zeros(sims, dtype=bool)
    for i in range(sims):
        g2[i] = bool(cap.evaluate(spec(n), {f"t{j}": T(int(b[i, j]), n, int(c[i, j]), n)
                                            for j in range(k)})["fired"])
    return g1, g2


# ── cost model, from measured CI v0 per-run costs ─────────────────────────
COST = {"baseline": 0.261, "null": 0.261, "step40": 0.143, "step15": 0.063}


def main() -> None:
    n_eq = check_equivalence()
    p = print
    p("<!-- generated by analysis/ci_v1/operating_characteristics.py -->")
    p(f"Gate 1 engine matched the product's `_paired_bootstrap` on {n_eq}/{n_eq} "
      "random cases. Gate 2 is the product's `capability.evaluate`.\n")

    p("### T1. Smallest observed drop that fires (gate 2)\n")
    p("From a perfect baseline, and from the lowest eligible baseline "
      "(fraction 0.875). `—` means nothing fires.\n")
    p("| K | " + " | ".join(f"n={n} from {n}/{n}" + (
        f" | n={n} from {n-1}/{n}" if (n - 1) / n >= 0.875 else "") for n in NS) + " |")
    cols = sum(2 if (n - 1) / n >= 0.875 else 1 for n in NS)
    p("|---|" + "---|" * cols)
    for k in range(1, 11):
        row = []
        for n in NS:
            for base in ((n, n - 1) if (n - 1) / n >= 0.875 else (n,)):
                d = min_drop(n, k, base)
                row.append("—" if d is None else f"{d:.2f}")
        p(f"| {k} | " + " | ".join(row) + " |")

    p("\n### T2. Gate 2 power per task (exact), K = 7\n")
    for n in NS:
        p(f"\nn = {n}\n\n| true p_base \\ p_cand | 0.75 | 0.50 | 0.25 | 0.10 |")
        p("|---|---|---|---|---|")
        for pb in (1.0, 0.95, 0.90):
            p(f"| {pb:.2f} | " + " | ".join(f"{g2_prob(pb, pc, n, 7):.2f}"
                                           for pc in (0.75, 0.5, 0.25, 0.1)) + " |")

    p("\n### T3. False blocks\n")
    p("Gate 2, worst case over the true rate (same rate in both arms, "
      "eligibility included). Per task, and family-wise as 1 − (1 − q)^K:\n")
    p("| n | K=4 per task | K=4 family | K=7 per task | K=7 family | K=10 per task | K=10 family |")
    p("|---|---|---|---|---|---|---|")
    for n in NS:
        cells = []
        for k in (4, 7, 10):
            q, _ = g2_worst_null(n, k)
            cells += [f"{q:.4f}", f"{1 - (1 - q) ** k:.4f}"]
        p(f"| {n} | " + " | ".join(cells) + " |")

    profiles = {
        "all tasks 0.95": lambda k: np.full(k, 0.95),
        "Stage-A-like (one task 0.6, rest 0.95)": lambda k: np.r_[0.6, np.full(k - 1, 0.95)],
        "spread 0.3–0.95": lambda k: np.linspace(0.3, 0.95, k),
    }
    p(f"\nUnchanged candidate, simulated ({SIMS} draws per cell). "
      "P(block) for gate 1, gate 2 and either:\n")
    p("| null profile | K | n | gate 1 | gate 2 | either |")
    p("|---|---|---|---|---|---|")
    for name, f in profiles.items():
        for k in (5, 7, 10):
            for n in (5, 8, 10):
                r = f(k)
                g1, g2 = sim(r, r, n)
                p(f"| {name} | {k} | {n} | {g1.mean():.4f} | {g2.mean():.4f} | "
                  f"{(g1 | g2).mean():.4f} |")

    p(f"\n### T4. Power of the dual gate against two kinds of regression "
      f"({SIMS} draws per cell)\n")
    p("Baseline: every task at 0.95.\n")
    p("| scenario | K | n | gate 1 | gate 2 | either |")
    p("|---|---|---|---|---|---|")
    scen = {
        "broad: every task −0.20": lambda k: np.full(k, 0.75),
        "broad: every task −0.30": lambda k: np.full(k, 0.65),
        "one task → 0.10": lambda k: np.r_[0.10, np.full(k - 1, 0.95)],
        "one task → 0.25": lambda k: np.r_[0.25, np.full(k - 1, 0.95)],
        "two tasks → 0.10": lambda k: np.r_[0.10, 0.10, np.full(k - 2, 0.95)],
        "Stage-B-like (0, 0.6, rest untouched)": lambda k: np.r_[0.0, 0.6, np.full(k - 2, 0.95)],
    }
    for name, f in scen.items():
        for k in (5, 7, 10):
            for n in (5, 8, 10):
                g1, g2 = sim(np.full(k, 0.95), f(k), n)
                p(f"| {name} | {k} | {n} | {g1.mean():.3f} | {g2.mean():.3f} | "
                  f"{(g1 | g2).mean():.3f} |")

    p("\n### T5. Size and expected cost of the confirmatory study, K = 7\n")
    p("Four arms (baseline, null, step 40, step 15). Per-run costs measured in "
      "CI v0: $0.261 full, $0.143 at step 40, ≤ $0.063 at step 15.\n")
    p("| n | runs per arm | max runs | runs without step-40 arm | expected cost | without step-40 arm |")
    p("|---|---|---|---|---|---|")
    for n in NS:
        r = 7 * n
        full = sum(COST.values()) * r
        p(f"| {n} | {r} | {4 * r} | {3 * r} | ${full:.1f} | "
          f"${full - COST['step40'] * r:.1f} |")

    p("\n### T6. More tasks or more repeats? Fixed runs per arm\n")
    p("Baseline 0.95 everywhere. Gate 2: one task collapses to 0.25 or 0.10. "
      "Gate 1: every task −0.20. Exact for gate 2, simulated for gate 1.\n")
    p("| runs/arm | K × n | gate 2: one task → 0.25 | gate 2: one task → 0.10 | gate 1: all −0.20 |")
    p("|---|---|---|---|---|")
    for budget, combos in ((40, ((5, 8), (8, 5))),
                           (56, ((7, 8), (8, 7), (14, 4))),
                           (60, ((6, 10), (10, 6), (12, 5))),
                           (80, ((8, 10), (10, 8), (16, 5)))):
        for k, n in combos:
            g1, _ = sim(np.full(k, 0.95), np.full(k, 0.75), n)
            p(f"| {budget} | {k} × {n} | {g2_prob(0.95, 0.25, n, k):.2f} | "
              f"{g2_prob(0.95, 0.10, n, k):.2f} | {g1.mean():.3f} |")


if __name__ == "__main__":
    main()

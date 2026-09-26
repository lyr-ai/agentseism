# Stage C — confirmatory results, by checkpoint

v1 is frozen at `bdd3f93`, and the predictions were declared in
`PREDICTIONS.md` (`8e09985`) before any candidate arm. Each checkpoint is
recorded as observed. Near-misses and oddities are noted and never acted on.

## Checkpoint 2 — null arm: **PASS. F1 did not fire.**

The null arm ran from `.runs/stageC_null` at `4fff043` (chain frozen before
execution), from 2026-09-26 03:10:35Z. It finished without interruption.

- The candidate was unchanged: `step_limit` 250, 7 × 8 = 56 runs, blind.
- The baseline copy was byte-identical to Stage C's (sha256 `4c35321f9ecdef3b…`).
- The task keys paired exactly.

| | |
|---|---|
| **combined v1 verdict** | **PASS** ("no gating feature regressed"), no warnings |
| gate 1, broad reliability | 0.857 → 0.821. Effect −0.036, interval [−0.107, 0.000]. Did not fire: the effect is far from −0.10, and so is `ci_high` |
| gate 2, capability regression | K = 7, per-task limit p ≤ 0.0071, 6 eligible. **Fired on none, no warnings.** pylint not monitored (baseline 0/8) |
| invalid runs | 0 / 56 |
| cost | arm \$13.44, **study total \$27.14** of the \$60 stop |
| report file | `runs/last-report.json` sha256 `70652f4a11e3edde…` |

| task | baseline | null | drop | p | gate 2 |
|---|---|---|---|---|---|
| psf__requests-1142 | 8/8 | 8/8 | 0 | 1.000 | PASS |
| pydata__xarray-2905 | 8/8 | 8/8 | 0 | 1.000 | PASS |
| pylint-dev__pylint-4551 | 0/8 | 0/8 | — | — | not monitored |
| pytest-dev__pytest-10051 | 8/8 | 8/8 | 0 | 1.000 | PASS |
| scikit-learn__scikit-learn-10297 | 8/8 | 8/8 | 0 | 1.000 | PASS |
| sphinx-doc__sphinx-10323 | 8/8 | 6/8 | 0.25 | 0.233 | PASS (below the 3/8 warning) |
| sympy__sympy-11618 | 8/8 | 8/8 | 0 | 1.000 | PASS |

**What this establishes:** fresh-data specificity for the frozen dual gate on
one unchanged candidate. The natural variation was one task going 8/8 → 6/8,
and neither gate blocked on it. This is one draw from the null. It is
consistent with the simulated false-block rate of ≤ 1–2% on realistic
profiles, but it does not measure that rate.

**Noted, not acted on:** gate 1's `ci_high` is 0.000 again, as it was in
CI v0 Stage A. Under the frozen rule that is not a near-miss, because the rule
also needs `effect ≤ −0.10` and the effect is −0.036. It would matter only to
the looser `ci_high < 0` alternative rejected in design §2.1.

**Next:** checkpoint 3 (step 40) needs separate approval. The null arm's
verdict does not start it.

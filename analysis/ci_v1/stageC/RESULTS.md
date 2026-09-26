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

## Checkpoint 3 — step 40: **REGRESSION. F3 did not fire. Gate 2 fired on both predicted collapses.**

The step-40 arm ran from `.runs/stageC_step40` on branch `stageC/step40` @
`1bf46d9`, which is `a141bb9` (chain frozen before execution) plus the single
change `step_limit` 250 → 40. The branch is not merged. The arm started at
2026-09-26 15:02:44Z and finished without interruption.

- The pre-flight verified that everything except `agent_config.json` is
  identical to `bdd3f93`, and that `agent_config.json` is the freeze plus
  `step_limit` 40.
- The baseline copy was byte-identical to Stage C's (`4c35321f9ecdef3b…`).
- The task keys paired exactly. 56 runs, blind.

| | |
|---|---|
| **combined v1 verdict** | **REGRESSION** |
| gate 1, broad reliability | 0.857 → 0.250. Effect −0.607, interval [−0.857, −0.339]. **Fired** |
| gate 2, capability regression | K = 7, limit p ≤ 0.0071, 6 eligible. **Fired on 3**: xarray, pytest, sphinx. **Warned on 2**: requests, scikit-learn |
| `LimitsExceeded` | 42 / 56, all scored FAIL through the empty-patch path |
| invalid runs | 0 / 56 |
| cost | arm \$8.61, **study total \$35.75** of the \$60 stop |
| report file | `runs/last-report.json` sha256 `b48e1c0095287bab…` |

| task | baseline | step 40 | drop | p | gate 2 | LimitsExceeded | declared prediction |
|---|---|---|---|---|---|---|---|
| pydata__xarray-2905 | 8/8 | 0/8 | 1.000 | 0.0001 | **FIRED** | 8/8 | **collapse ✓** |
| pytest-dev__pytest-10051 | 8/8 | 0/8 | 1.000 | 0.0001 | **FIRED** | 8/8 | **collapse ✓** |
| sphinx-doc__sphinx-10323 | 8/8 | 1/8 | 0.875 | 0.0007 | **FIRED** | 7/8 | none |
| psf__requests-1142 | 8/8 | 3/8 | 0.625 | 0.0128 | WARNING | 5/8 | none |
| scikit-learn__scikit-learn-10297 | 8/8 | 4/8 | 0.500 | 0.0385 | WARNING | 4/8 | none |
| sympy__sympy-11618 | 8/8 | 6/8 | 0.250 | 0.2333 | PASS | 2/8 | none |
| pylint-dev__pylint-4551 | 0/8 | 0/8 | — | — | not monitored | 8/8 | collapse (unmonitored) ✓ |

**Against the declared criteria:**
- **F3 did not fire.** Both eligible predicted collapses happened (0/8), and
  gate 2 fired on both.
- **No implementation fault.** Every eligible task at or below the §4 boundary
  (≤ 2/8 from 8/8) fired. The two warnings sit just above it, at 3/8 and 4/8,
  exactly where the frozen boundary says they should not fire.
- **F4 was not applicable.** No task was predicted unaffected.
- **Every declared prediction held,** including pylint's unmonitored collapse.

**Noted, not acted on:**
1. **This arm turned out broad, not concentrated.** Six of seven tasks lost
   success, so gate 1 fired as well. The REGRESSION verdict therefore does not
   isolate gate 2. Gate 2's per-task decisions are the evidence for it, and
   they are recorded above. Unlike CI v0 Stage B, a step-40 cut on these
   tasks is not a concentrated regression. The step counts said it would not
   be: most "no prediction" tasks straddled 40.
2. **The "no prediction" tasks went both ways:**
   - sphinx collapsed (1/8) and fired;
   - requests (3/8) and scikit-learn (4/8) dropped 0.50–0.625 and only
     warned. That is the collapse-only resolution documented in the OC study,
     observed on real data: a 50–60 point drop does not block at K = 7, n = 8;
   - sympy barely moved (6/8).
3. **The prediction rule was coarse.** "Collapse" needed all eight baseline
   runs above 40, and "unaffected" needed all eight at or below 30. Four of
   seven tasks fell between the two and got no prediction.

**Next:** checkpoint 4 (step 15, which attacks gate 1) needs separate
approval. This verdict does not start it.

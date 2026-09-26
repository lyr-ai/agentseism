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

## Checkpoint 4 — step 15: **REGRESSION. F2 did not fire.**

The step-15 arm ran from `.runs/stageC_step15` on branch `stageC/step15` @
`68aec9d`, which is `3db49da` (chain frozen before execution) plus the single
change `step_limit` 250 → 15. The branch is not merged. The arm started at
2026-09-26 17:41:43Z and finished without interruption.

- The pre-flight verified method identity with `bdd3f93` plus the
  intervention.
- The baseline copy was byte-identical (`4c35321f9ecdef3b…`).
- The task keys paired exactly. 56 runs, blind.

| | |
|---|---|
| **combined v1 verdict** | **REGRESSION** |
| gate 1, broad reliability | 0.857 → 0.000. Effect −0.857, interval [−1.000, −0.571]. **Fired** |
| gate 2, capability regression | **Fired on all 6 eligible tasks**, each 8/8 → 0/8, p = 0.0001. pylint not monitored |
| `LimitsExceeded` | 56 / 56, every run stopped at 15 steps and scored FAIL via the empty-patch path |
| invalid runs | 0 / 56 |
| cost | arm \$2.74, **study total \$38.49** of the \$60 stop |
| report file | `runs/last-report.json` sha256 `4dab5f45f343987e…` |

Every declared step-15 prediction ("collapse" on all seven tasks) held.

As recorded in `PREDICTIONS.md`, this was an easy test of gate 1. It confirms
that gate 1 fires on a total broad collapse, and nothing about moderate
broad drops.

---

# Stage C — conclusion

**v1 survived all three testable falsification criteria in the fresh
confirmatory study. F4 was not testable under the observed baseline.**

| criterion | test | outcome |
|---|---|---|
| **F1** null arm returns REGRESSION | fresh unchanged candidate | **survived**: PASS. Neither gate blocked natural variation (sphinx 8/8 → 6/8) |
| **F2** step-15 arm not REGRESSION | fresh total broad collapse | **survived**: gate 1 fired, −0.857 [−1.000, −0.571] |
| **F3** gate 2 fires on no predicted collapse | step 40, xarray and pytest predicted | **survived**: both collapsed 8/8 → 0/8, and gate 2 fired on both |
| **F4** gate 2 fires on a task predicted unaffected | — | **not testable**: the baseline gave no task an "unaffected" prediction |

Other checks held too:
- no implementation fault: every eligible task at or below the §4 boundary
  fired, and none above it did;
- 0 invalid runs in 224;
- no interruption, no threshold, task or intervention changed, and method
  code identical to `bdd3f93` in every arm;
- \$38.49 of the \$60 stop spent.

## What Stage C established

1. **Fresh-data specificity on one unchanged candidate.** It is one draw from
   the null, consistent with the simulated false-block rate of 1–2% or less.
   It does not measure that rate.
2. **Gate 2 identifies pre-declared capability collapse on unseen tasks.**
   This validates gate 2 as designed. It does **not** show gate 2's value
   beyond gate 1: in both degraded arms gate 1 fired too, so the overall
   verdict would have been REGRESSION without gate 2.
3. **Gate 1 fires on a total broad collapse.**
4. **Gate 2 has collapse-only resolution on real data.** requests 8/8 → 3/8
   (−62.5 points) and scikit-learn 8/8 → 4/8 (−50 points) produced WARNING,
   not REGRESSION, exactly as the OC study said. v1's capability gate is a
   near-collapse detector, not a severe-regression detector.

## What Stage C did not establish

- **Gate 2's incremental value.** That needs a fresh concentrated collapse on
  which gate 1 does not fire. CI v0 Stage B had that shape, but it is
  development data.
- **Sensitivity to moderate broad regressions.** The OC study says gate 1
  mostly misses −0.20, and step 15 did not test it.
- **Generality beyond step-budget degradations.** Every degraded arm here
  (and in CI v0) cut `step_limit`. Prompt, tool, model or retrieval changes
  are untested.
- **Measured false-block rate, cost-per-PR viability, and usefulness to anyone
  outside the project.**

## Evidence level

**Confirmatory real, for the claims above, on seven SWE-bench Verified tasks,
one agent (mini-swe-agent 2.4.6), one model (Claude Haiku 4.5), and
step-budget degradations only.** It is not external-user evidence.

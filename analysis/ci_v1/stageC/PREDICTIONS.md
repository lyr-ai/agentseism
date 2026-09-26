# Stage C — baseline results and predictions

Written 2026-09-25, **after the baseline and before any candidate arm**, from
the baseline alone. Only the information §7 allows was read:
- success counts and eligibility;
- step counts (`model_calls`);
- validity;
- cost.

The rules are the frozen ones: *collapse predicted* if all eight baseline runs
used more steps than the arm's limit; *unaffected predicted* if all eight used
at most 0.75 × the limit; *no prediction* otherwise.

## Baseline

The baseline ran from `.runs/stageC` at `118dea1`, with the method frozen
at `bdd3f93`, from 2026-09-25 23:54:52Z. It finished without interruption.

| | |
|---|---|
| runs | 56 / 56, **0 invalid**, all `Submitted` |
| cost | $13.71 ($0.245 per run) |
| contract | `f759edc7adc57c6c` (surface-2, capability-2) |
| baseline file | `baselines/main.json` sha256 `4c35321f9ecdef3b…` |

| task | success | eligible (≥ 7/8) | steps, sorted | step 40 | step 15 |
|---|---|---|---|---|---|
| psf__requests-1142 | 8/8 | yes | 37 38 38 39 40 40 41 56 | no prediction | **collapse** |
| pydata__xarray-2905 | 8/8 | yes | 54 56 58 60 62 62 73 73 | **collapse** | **collapse** |
| pylint-dev__pylint-4551 | 0/8 | **no** | 56 73 76 77 77 79 85 86 | collapse (not monitored) | collapse |
| pytest-dev__pytest-10051 | 8/8 | yes | 47 49 51 57 61 64 64 67 | **collapse** | **collapse** |
| scikit-learn__scikit-learn-10297 | 8/8 | yes | 36 36 36 37 42 46 48 51 | no prediction | **collapse** |
| sphinx-doc__sphinx-10323 | 8/8 | yes | 32 41 43 46 51 53 54 85 | no prediction | **collapse** |
| sympy__sympy-11618 | 8/8 | yes | 37 40 40 45 46 47 48 51 | no prediction | **collapse** |

K = 7 (the suite). Per-task limit α/K = 0.0071. Six tasks are eligible.
pylint is not monitored by gate 2, but it stays in K.

## Consequences, declared now

- **Step-40 arm is informative.** Collapse is predicted on two eligible tasks,
  xarray and pytest, so the arm is not skipped.
  - **F3:** the study is falsified if gate 2 fires on neither of them.
  - It is an implementation fault if either is observed at or below 2/8 and
    gate 2 does not fire on it.
- **No task is predicted unaffected** at step 40 or step 15. No task has all
  eight runs within 30 steps (or 11). So F4 cannot be triggered in either
  degraded arm. That is recorded here, not changed.
- **Step-15 arm predicts collapse everywhere.**
  - **F2:** the study is falsified if the verdict is not REGRESSION.
  - Recorded weakness: with every task predicted to collapse, this arm is an
    easy test of gate 1. It confirms gate 1 fires on a total broad collapse,
    not that it catches a moderate broad drop, which the OC study already
    shows it mostly does not.
- **Null arm** is next in order. **F1:** REGRESSION from either gate
  falsifies v1 and stops the study.

## Cost projection against the $60 stop

| | |
|---|---|
| baseline (actual) | $13.71 |
| null (at baseline cost) | ≈ $13.71 |
| step 40 (linear upper bound, each run capped at 40/steps of its baseline cost) | ≤ $9.89 |
| step 15 (same bound) | ≤ $3.76 |
| **projected total** | **≈ $41.06**, under $60, so the study may continue |

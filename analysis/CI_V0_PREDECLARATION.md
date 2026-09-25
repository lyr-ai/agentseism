# CI v0 — agent choice and pre-declared degradation

Written **before any run**, which is the only thing that makes the positive
control a control. Nothing here may be adjusted after seeing a result; if it
turns out to be wrong, the run is recorded as failed and a new declaration is
written and dated.

2026-09-25, branch `product/ci-v0`.

## The two candidates, checked against the code

| requirement | `agents/coding/` (SWE-bench via mini-swe-agent) | `agents/gaia_markazhang.py` |
|---|---|---|
| repeated stochastic execution | yes | yes |
| **deterministic evaluator** | **yes** — SWE-bench tests pass/fail, `experiments/coding/c2h_checker.py:label_from_report`, run locally today against real images | **no** — `agents/gaia.py` provides an *equivalence relation between two runs*, and says so in its own docstring: "not a grader". `benchmarks/gaia_pilot.json` carries `task_ids` only, no gold |
| baseline/candidate comparison | yes | yes |
| a clean pre-declarable degradation | **yes** — `step_limit` on the agent config | unclear; the LangGraph recursion limit is not exposed by the adapter |
| dataset access | images pull publicly; verified on a real host and locally | GAIA is gated; the upstream agent is not vendored (no license) |
| matches the shipped contract | **yes** — `contracts/default.yaml` already declares `evaluator: swebench_resolved` | no |

**Recommendation: the coding agent.** GAIA is not merely more expensive, it is
disqualified on the requirement that matters most — there is no deterministic
gold evaluator in this repository for it, and a CI verdict cannot rest on a
two-run equivalence relation.

## What is still missing, beyond the GitHub Action

The audit said the Action was the only gap. Against this agent that was
incomplete, and the correction belongs here rather than in a later surprise:

1. **A runner adapter in the product's shape.** `seism` invokes
   `command: "... --task {task_file} --out {artifact_dir}"`. No script in the
   repository has that interface for the coding agent; the existing entry points
   belong to the experiment runner. A thin wrapper is needed — invoke the agent
   on one instance, write the patch and metadata into `{artifact_dir}`.
2. **An evaluator command in the same shape.** `c2h_checker` exists and is
   correct; it needs a small CLI front that reads `{artifact_dir}` and exits
   0/1, or emits the JSON the contract expects.
3. **`mini-swe-agent` is not a declared dependency on this branch.** It is
   installed in the local venv (2.4.6) but absent from `pyproject.toml` here;
   the pin lives on the research branch. It must be declared before CI can
   install it.

None of the three is large. All three are product code, not research code.

## The pre-declared degradation

**Change:** the agent's `step_limit`, **250 → 40**. Nothing else moves — same
model, same prompt, same tasks, same evaluator, same trial count, same images.

**Why this is a real regression and not a contrivance.** A step limit is a
genuine configuration value a team changes for cost. Cutting it truncates runs
that need more turns than the cap before the fix is complete, so fewer tasks
resolve. The mechanism is stated in advance and is independent of the outcome:
it predicts *fewer resolved tasks*, with *tool reliability unchanged*, which is
what distinguishes it from "the agent got worse somehow".

These exact values were registered as the pilot's `M1` arm on 2026-09-20 with
that predicted direction, before any of today's data existed. That is a stronger
pre-declaration than one written now, and the reason to reuse it rather than
invent a fresh number.

**Direction, declared:** `task_success` decreases. A run in which it increases,
or does not move, is a **failed positive control** — not a reason to pick a
different degradation.

## The paired control

| arm | change | required verdict |
|---|---|---|
| negative control | none — candidate identical to baseline | **PASS** |
| positive control | `step_limit` 250 → 40 | **REGRESSION** |

Same agent, same 5 tasks, same 5 trials per condition. Neither half counts
alone: a tool that always returned PASS would satisfy the first, and one that
always returned REGRESSION would satisfy the second.

## Scale and cost

| | |
|---|---|
| tasks | 5 |
| trials per condition | 5 |
| conditions | baseline, unchanged candidate, degraded candidate |
| **agent invocations** | **75** (5 × 5 × 3) |
| evaluator invocations | 75, local Docker, no API cost |
| estimated API cost | **$8–25**, from the observed shape of a real run — one smoke cell issued 54 model requests at `step_limit` 250 |
| wall clock | 3–5 hours locally; the degraded arm is faster because it truncates |
| GPU | none |

The baseline arm is reusable, so a re-run of only the two candidate arms costs
about two thirds of that.

## A measured warning about sample size

`tests/test_cli.py::test_regression_when_the_agent_degrades` is the synthetic
positive control on `master`. Measured today over 20 fresh processes:
**14 passed, 6 failed — a 30% false-negative rate.**

Its degradation is enormous: the fake agent's failure rate goes from 15% to
55%. If a 40-point effect at this trial count misses three times in ten, a real
`step_limit` cut may also fail to register.

The cause is that the fake agent seeds with `random.Random(hash((task, out)))`,
and `hash()` on a string is randomised per process, so the seed — and the
pass/fail pattern — differs every run. That is a defect in the test, not
necessarily in the thresholds; but the flake is only visible *because* the
sample is small enough for seed choice to change the verdict, and that part is
about the sample.

**This is recorded as a prior, not acted on.** The thresholds and the trial
count stay exactly as declared. If the positive control fails on the real
agent, the first hypothesis to test is sample size, and that test is a new
declaration written afterwards — not an adjustment made during the run.

## Hard stop

One fix-forward. If the second end-to-end attempt does not produce a verdict,
the milestone is recorded as not achieved, the defect is fixed offline with a
test that reproduces it, and no further paid run happens until that test exists.

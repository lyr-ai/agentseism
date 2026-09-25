# CI v0 — frozen validation run card

For approval **before any paid execution**. Everything below is fixed; if any
of it turns out to be wrong the run is recorded as failed and a new card is
written and dated. Nothing here may be adjusted after a result is seen.

Frozen 2026-09-25 on `product/ci-v0` @ `b15db36`.
Companion to `analysis/CI_V0_PREDECLARATION.md`, which fixed the agent and the
degradation before this card existed.

## What is already verified, at zero API cost

The complete product path was driven end to end with a stubbed model, against
**real Docker containers and the real SWE-bench harness**:

```
seism baseline --trials 1   ok    outcome success=0, label FAIL, patch 376 B
seism check    --trials 1   INSUFFICIENT_EVIDENCE — "not a pass"
```

The verdict is correct and is the point: one task at one trial is below the
contract's minimum of five scenarios and three trials, and the tool refused to
call it a pass. Machine-readable result, markdown report and exit code all
produced.

So what the paid run buys is **not** "does the plumbing work". It is the one
thing no stub can answer: whether the decision rule separates noise from a real
regression on a real stochastic agent.

## The run

| | |
|---|---|
| branch / commit | `product/ci-v0` @ `b15db36` |
| agent | mini-swe-agent `2.4.6`, pinned |
| model | to be named at launch and recorded in the fingerprint |
| tasks | 5 SWE-bench Verified instances, listed in `.agentseism/tasks.yaml` before the first call |
| trials per condition | 5 |
| contract | `contracts/default.yaml`, `task_success` gating, threshold 0.10, paired bootstrap over tasks |
| evaluator | `agents/coding/swebench_evaluator.py` — deterministic, local Docker, no API cost |

### Two stages, and the first one can stop the second

**Stage A — negative control (50 invocations).**
`seism baseline --trials 5`, then `seism check --trials 5` with **no change**.

Required: **PASS**, or a defensible `INSUFFICIENT_EVIDENCE`.

A `REGRESSION` here is a false positive and **ends the milestone**. The degraded
arm is not run, because a detector that alarms on its own noise cannot be
measured for sensitivity.

**Stage B — positive control (25 invocations).** Only if Stage A passes.
Apply the frozen degradation, `step_limit` 250 → 40 in
`agents/coding/agent_config.json`, and re-run `seism check --trials 5`.

Required: **REGRESSION**, with `task_success` named, an effect and an interval.

### Cost

| stage | invocations | estimate |
|---|---|---|
| A — baseline + unchanged candidate | 50 | $5–17 |
| B — degraded candidate | 25 | $2–8 |
| **total if both run** | **75** | **$7–25** |

Evaluation is local Docker throughout and costs nothing. Wall clock 3–5 hours;
Stage B is faster because it truncates. No GPU, no rented host.

## Acceptance

Both halves, or neither:

| | required |
|---|---|
| specificity | unchanged candidate → **PASS** |
| sensitivity | degraded candidate → **REGRESSION**, with effect and interval |
| report | a reader who did not run it can tell whether to merge, and which feature moved |

Neither counts alone. A tool returning PASS unconditionally satisfies the
first; one returning REGRESSION unconditionally satisfies the second.

**Not required for acceptance:** a GitHub Action run on a real pull request.
The workflow exists and is committed, but posting a comment is plumbing this
run does not need to prove. Keeping it out of the criteria keeps the paid run
pointed at the decision rule.

## What is deliberately excluded

Localization and `seism diagnose` (still a stub, by decision), the paper, GPU
work, memory experiments, feature-identifiability studies, any threshold or
trial-count change, and any adjustment to the frozen degradation.

## Stop conditions

1. **Stage A alarms.** False positive. Stop, do not run Stage B.
2. **One fix-forward, total.** If a second attempt does not produce a verdict,
   the milestone is recorded as not achieved and the defect is fixed offline
   with a test that reproduces it before any further spend.
3. **Cost passes $30.** Stop and re-cost, whatever the state.
4. **Three consecutive invalid runs.** Already enforced in `run_trials`, which
   refuses to spend the rest of a batch proving an infrastructure fault.

## The prior that is recorded and not acted on

`analysis/CI_V0_PREDECLARATION.md` reports that the synthetic positive control
was failing 6 times in 20 before its seed was made deterministic. After the fix
it is 50/50 on the positive control and 50/50 on the negative, with no change
to thresholds, trial count, degradation or decision logic — so the 30% was a
fixture defect, not the decision rule.

What remains true is narrower and still unaddressed: a stable synthetic gate at
a 40-point effect says nothing about whether a real `step_limit` cut produces
an effect that large. If Stage B fails, sample size is the first hypothesis —
tested by a new dated declaration afterwards, never by an adjustment during the
run.

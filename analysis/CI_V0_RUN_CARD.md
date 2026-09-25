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

## The run — every identifier frozen

| field | value |
|---|---|
| branch | `product/ci-v0` |
| commit | `5e0ecb797818bda3d029823f29829b419f5ed4f8` (this card is one commit later; the run uses the tree at the tip) |
| agent | `mini-swe-agent==2.4.6` (exact pin, `pyproject.toml` extra `coding-agent`) |
| evaluator | `agents/coding/swebench_evaluator.py`, local Docker, **no API cost** |
| dataset | `SWE-bench/SWE-bench_Verified`, split `test` |
| model | `anthropic/claude-sonnet-5` (fallback `anthropic/claude-sonnet-4-5-20250929`, mini-swe-agent's pinned default, if litellm does not resolve it) |
| config manifest | `analysis/ci_v0/MANIFEST.sha256`, digest `972846daa4a9f732` |
| contract | `analysis/ci_v0/contract.yaml`, sha256 `f89a7d43e0606eaa…` |
| trials per condition | **5** |
| baseline `step_limit` | **250** |
| negative candidate `step_limit` | **250** (identical to baseline — that is the control) |
| positive candidate `step_limit` | **40** (Stage B only) |
| Stage A stop | **50 invocations or $25 actual accumulated cost, whichever comes first** |
| global bound | 75 invocations across both stages |

### The five tasks, chosen before any call

Rule, applied mechanically and not for any property of the result: the SWE-bench
Verified instances whose images are **already present locally**, sorted
ascending by instance id, first five. All twelve local images are from distinct
repositories, so the first five are too. Using local images removes a pull
failure as a confound; it does not select for difficulty, which was never
inspected.

```text
astropy__astropy-12907
django__django-10097
matplotlib__matplotlib-13989
mwaskom__seaborn-3069
pallets__flask-5014
```

Frozen with their problem statements in `analysis/ci_v0/tasks/`, hashed in the
manifest above. Five scenarios is exactly the contract's
`minimum_evidence.scenarios`, so a single unusable task drops the run below the
minimum and yields `INSUFFICIENT_EVIDENCE` — which is the correct answer, not a
reason to substitute a sixth.

## The one open field: the model

**No API credentials are configured in this environment.** `ANTHROPIC_API_KEY`,
`OPENAI_API_KEY`, `GEMINI_API_KEY`, `DEEPSEEK_API_KEY`, `TOGETHER_API_KEY` and
`OPENROUTER_API_KEY` are all unset, and mini-swe-agent's global config carries
no key either. Stage A cannot start until a model and its credential are
supplied.

The model identity must be fixed **before** the first call and recorded here,
because it enters the comparability fingerprint: a model that changed between
the baseline and candidate arms would make them incomparable, and the contract
would say so rather than report a regression.

The cost estimates below assume a mid-priced frontier model. A cheaper model
changes the estimate but not the design.

### Two stages, and the first one can stop the second

**Stage A — negative control (50 invocations).**
`seism baseline --trials 5`, then `seism check --trials 5` with **no change**.

Required: **PASS**, or a defensible `INSUFFICIENT_EVIDENCE`.

A `REGRESSION` here is a false positive and **ends the milestone**. The degraded
arm is not run, because a detector that alarms on its own noise cannot be
measured for sensitivity.

**Stage B — positive control (25 invocations). Requires separate approval.**
Stage A passing does not release it; the data is reviewed first.
Apply the frozen degradation, `step_limit` 250 → 40 in
`agents/coding/agent_config.json`, and re-run `seism check --trials 5`.

Required: **REGRESSION**, with `task_success` named, an effect and an interval.

### Cost

| stage | invocations | cost |
|---|---|---|
| A — baseline + unchanged candidate | 50 | measured, not capped |
| B — degraded candidate | 25 | separate approval |
| **total if both run** | **75** | reported after each stage |

**The $17 estimate is withdrawn, and the reason matters.** It came from a vLLM
run and was never grounded in Claude pricing. mini-swe-agent's registered
SWE-bench config sets `cost_limit: 3.0` **per run**, so 50 invocations have a
$150 ceiling — about nine times the figure the card originally carried.

The bound is therefore **the invocation count, not a dollar figure**: 50 for
Stage A, 25 for Stage B, and the cost is measured and reported rather than
predicted. Lowering `cost_limit` to force a dollar cap was considered and
rejected: a run that hits a cost ceiling truncates, which is exactly what the
Stage B degradation does, so a truncating baseline would make the specificity
control measure the cost limit instead of the agent.

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
3. **Stage A reaches 50 invocations, or $25 of actual accumulated cost,
   whichever comes first.** If the dollar stop fires the outcome is
   **`COST_STOP / incomplete`**: not a verdict, not a PASS, not a REGRESSION,
   and the partial data is **not** read as specificity evidence.

   This is an *external* budget on the experiment, measured by accumulating
   reported spend between invocations. It is a different thing from
   mini-swe-agent's per-run `cost_limit: 3.0`, which stays untouched —
   lowering that would truncate individual runs and confound the control.
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

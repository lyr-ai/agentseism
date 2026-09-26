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
| commit | config frozen at `5e0ecb7`; model frozen at `e662ffd`; Stage A runs the branch tip |
| agent | `mini-swe-agent==2.4.6` (exact pin, `pyproject.toml` extra `coding-agent`) |
| evaluator | `agents/coding/swebench_evaluator.py`, local Docker, **no API cost** |
| dataset | `SWE-bench/SWE-bench_Verified`, split `test` |
| model | **`anthropic/claude-haiku-4-5-20251001`** — frozen by the probe (`analysis/CI_V0_PROBE.md`), all five criteria held at $0.0995/run |
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

## The model is no longer open

Frozen to `anthropic/claude-haiku-4-5-20251001` by the pre-registered probe.
All five criteria held; measured cost **$0.0995 per run** over 24 model calls.

That measurement revises the Stage A projection from ~$15 to **~$5**, so the
$25 stop carries roughly 5× headroom rather than being likely to fire. The
earlier ±2× error bar was too narrow and wrong in the cheap direction: steps
per run were assumed at ~40 and observed at 24.

The probe is **not** Stage A evidence and its artifacts are not Stage A data.

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

## Deviation, 2026-09-25 — Stage A attempt 1 aborted by infrastructure

Added after the fact and dated. Nothing above this section was changed.

**What happened.** Stage A attempt 1 ran from `/tmp/stageA` against `0d10701`,
starting 2026-09-24 23:46 PDT. The baseline arm finished at 08:55 (25/25). The
candidate arm had done 10 invocations and was partway through its 11th when
macOS rebooted at about 10:01. macOS clears `/tmp` on boot, so the frozen
baseline (`baselines/main.json`), every `agent_run.json` (cost, steps, exit
status, invalid flags) and the chain log are gone. The total is roughly
**35 completed invocations plus 1 interrupted**, at roughly **$7**. The exact
figure was stored only in the lost `agent_run.json` files.

**What survived, and was not read.** The SWE-bench harness wrote 36
per-instance directories to `logs/run_evaluation/`. They contain resolved
labels. They were moved **unopened** to
`.runs/aborted-stageA-2026-09-25/run_evaluation/` and listed in `MOVED.txt`
there. That way the new attempt's harness output cannot be mixed up with them.
No partial result was read or interpreted, and none will be. Rebuilding a
baseline from these files was considered and rejected: cost and validity are
missing, and a baseline put together after an interruption is not the one the
card froze.

**The fix-forward.** This counts as the single fix-forward that stop
condition 2 allows. Stage A restarts at 0/50 and does not resume.

- State goes to `.runs/stageA` inside the repository (gitignored), not `/tmp`.
- The whole chain, `analysis/ci_v0/stageA_chain.sh`, runs under `caffeinate`.
- A watchdog enforces the $25 stop while each arm is running. Attempt 1
  enforced it only between arms plus a manual monitor.
  The $25 is a stop target, not a hard ceiling. Spend is read from each
  finished run's `agent_run.json`, so the run in flight when the threshold is
  crossed can add up to its own cost (at most mini-swe-agent's per-run
  `cost_limit` of $3.0). The recorded total can therefore exceed $25 by at
  most one run.
- Unchanged: model, the five tasks, contract, thresholds, 5 trials per arm,
  `step_limit` 250, the $25 Stage A stop, and the decision rule. The money lost
  in attempt 1 does not reduce the trial count or change any design choice.

**The 75-call bound, clarified.** The "global bound 75 invocations" above means
**planned, valid evidence runs**: 50 in Stage A and 25 in Stage B. Calls
aborted by infrastructure are logged here as wasted execution cost. They are
not counted in that bound and are never part of the statistical sample.

| attempt | invocations | cost | evidence? |
|---|---|---|---|
| Stage A attempt 1 | ~35 + 1 interrupted | ~$7 (exact figure lost) | no, aborted, unread |
| Stage A attempt 2 | up to 50 | measured | yes |

If attempt 2 also ends without a verdict, the milestone is recorded as not
achieved, as stop condition 2 already says.

## Stage A result, attempt 2 — 2026-09-25

Ran from `.runs/stageA` at `7a3d293`, from 2026-09-25 17:38:40Z to
about 21:28Z, under `caffeinate`. It finished without interruption. The
decision rule is the one frozen above. Nothing was read or changed while it
ran.

**Verdict: PASS** ("no gating feature regressed", no warnings).

| | value |
|---|---|
| task_success, baseline → candidate | 0.92 → 0.88 |
| paired effect [95% interval] | −0.04 [−0.12, +0.00], bootstrap over 5 tasks |
| invalid runs | 0 / 50 (baseline 25/25 valid, candidate 25/25 valid) |
| invocations | 50 (25 baseline + 25 unchanged candidate) |
| cost | $13.07 (baseline $6.96), $25 stop not reached |
| comparability | precheck passed before the first candidate call; contract `6e9aa552c90a2cda` |
| baseline file | `baselines/main.json` sha256 `373abf2a57e4b288…` |
| report file | `runs/last-report.json` sha256 `7fc6b240c3c44bf5…` |

Per-task outcomes (1 = resolved), trials 0–4:

| task | baseline | unchanged candidate |
|---|---|---|
| astropy__astropy-12907 | 1 1 1 1 1 | 1 1 1 1 1 |
| django__django-10097 | 1 1 1 1 1 | 1 1 1 1 1 |
| matplotlib__matplotlib-13989 | 1 1 1 1 1 | 1 1 1 1 1 |
| mwaskom__seaborn-3069 | 0 1 1 1 0 | 1 0 0 1 0 |
| pallets__flask-5014 | 1 1 1 1 1 | 1 1 1 1 1 |

**What it shows, and how far that goes.** On 50 real executions of a
stochastic coding agent, an unchanged candidate showed natural outcome
variation (seaborn 3/5 → 2/5) and was not called a regression. That is the
specificity half of acceptance. It is narrow evidence. Four of the five tasks
sat at the ceiling in both arms, so the noise the rule absorbed came almost
entirely from one task. The PASS does not show specificity under broader or
larger per-task variance.

Cost per run averaged $0.26, against the probe's $0.0995. The single-task
probe underestimated the five-task mix by about 2.6×. The stop was never at
risk, and nothing about the design depended on the estimate.

**Stage B has not been run.** It still needs separate approval. Nothing in the
Stage B rows above has been changed.

## Deviation before Stage B, 2026-09-25 — evaluator defect found by code audit

Found by a read-only audit after Stage A and before any Stage B call. No run
exposed it.

**The defect.** A run that hits `step_limit` ends in mini-swe-agent's
`LimitsExceeded` with an empty submission. The SWE-bench harness silently
drops empty predictions (`run_evaluation.py:627`) and writes no per-instance
report. The evaluator therefore returned `invalid`, which contradicted its own
docstring. Under this contract's `invalid_policy: stop`, a single invalid
candidate run gives `INSUFFICIENT_EVIDENCE`, and `run_trials` stops after three
in a row. Stage B's intervention works precisely by making runs hit the limit.
Run as frozen, Stage B would have been scored as a measurement failure, never
as a task failure. It would have tested the evaluator's labelling, not the
decision rule.

**The fix** (`2725192`, stop condition 2: fixed offline with a reproducing test
before further spend). An empty patch is scored `FAIL` without the harness only
after an agent-level end: `LimitsExceeded` (step or cost budget) or
`Submitted` with an empty diff. It stays `invalid` in these cases:
- an empty patch after `TimeExceeded` (wall clock, host-dependent),
  `RepeatedFormatError`, an unknown status or no status;
- a real patch the harness failed to judge;
- a missing or malformed artifact.

The new tests fail on the old evaluator and pass on the fix, and the full
suite is 475 passed.

**Zero-cost end-to-end check.** This used a disposable worktree at `2725192`
with `step_limit` 1, a local stub model that never submits, a real Docker
container, and the real runner, evaluator, `run_trials`, `_measure` and
`decide()`. No API was called. The results were:
- `exit_status: LimitsExceeded`, a 0-byte patch, and the outcome
  `success: 0, label: FAIL, scored_by: empty_patch`;
- the run was valid, and `task_success` reached the measurement as 0.00;
- the verdict was `INSUFFICIENT_EVIDENCE` for being below minimum evidence
  (1 task, 1 trial), not `invalid_stop`.

This is not Stage B evidence.

**Stage A is unaffected.** All 50 of its runs were valid, so none took the
empty-patch path, and the fix cannot change its outcome.

**Unchanged:** tasks, model, contract, `practical_threshold` 0.10, minimum
evidence, paired bootstrap over tasks (seed 0, 2000 resamples), 5 trials, and
the Stage B intervention `step_limit` 250 → 40.

### What the frozen rule detects, recorded before any Stage B data

REGRESSION on `task_success` requires `effect ≤ −0.10` **and**
`ci_high ≤ −0.10`, with at least 5 scenarios, at least 3 trials and no invalid
runs. The interval is a bootstrap over only five tasks, so the rule detects a
**broad, cross-task** regression and not a concentrated one. Measured with the
real `_paired_bootstrap` and `decide()`, against the Stage A baseline:

| candidate pattern | effect | interval | verdict |
|---|---|---|---|
| one task 5/5 → 0/5 | −0.20 | [−0.60, 0.00] | PASS |
| two tasks each lose 3/5 | −0.24 | [−0.48, 0.00] | PASS |
| four tasks lose 1/5, one loses 4/5 | −0.28 | [−0.56, −0.08] | PASS |
| every task loses 1/5 | −0.20 | [−0.20, −0.20] | REGRESSION |
| four tasks lose 2/5, one unchanged | −0.32 | [−0.40, −0.16] | REGRESSION |

In words, the product currently answers "did this PR broadly lower
reliability across these tasks?" It does not answer "did this PR badly break
at least one task?" Both are legitimate CI questions. This is recorded as a
limitation and is **not** changed before Stage B: changing the statistics now
would mean redesigning the experiment after seeing Stage A. A per-task
severity gate is a question for after Stage B.

It also frames how Stage B will read. A `step_limit` cut that truncates only
some tasks can produce a large aggregate drop and still PASS under this rule.
That would be a real result about the rule's sensitivity, not grounds for
adjustment.

**Stage B has not been run.** It needs separate approval.

## Stage B result — 2026-09-25

Ran from `.runs/stageB` on branch `stageB/step-limit-40` @ `6a5af4c`.
That branch is `b2f1bdf` plus the single pre-declared change,
`step_limit` 250 → 40, and is **not** merged into `product/ci-v0`. It
started at 21:46:52Z and finished without interruption. The chain is committed
as `analysis/ci_v0/stageB_chain.sh` for audit.

Before the first paid call the chain checked:
- Docker and the five images;
- the task files were byte-identical to the frozen ones;
- the tree was clean and `step_limit` was 40;
- the baseline and contract copies were byte-identical to Stage A's (baseline
  sha256 `373abf2a57e4b288…`, as recorded above);
- baseline and candidate task keys paired exactly on all five tasks.

Neither the intervention nor anything else was changed during the run, and no
partial outcome was read.

### Three things, kept separate

| | |
|---|---|
| **observed effect** | task_success 0.92 → 0.52: **−0.40**, 95% interval **[−0.72, −0.08]** (paired bootstrap over 5 tasks) |
| **product verdict** | **PASS** ("no gating feature regressed") |
| **why** | the frozen rule needs `effect ≤ −0.10` **and** `ci_high ≤ −0.10`. The effect passed (−0.40); `ci_high` was −0.08 and did not, so REGRESSION did not fire |

| | value |
|---|---|
| invalid runs | 0 / 25 |
| `LimitsExceeded` | 12 / 25, all scored `FAIL` via the empty-patch path (`2725192`) |
| invocations | 25 |
| cost | $3.56 |
| comparability | precheck passed; contract `6e9aa552c90a2cda` |
| report file | `runs/last-report.json` sha256 `16efb971b740a1aa…` |

### By task

| task | baseline (Stage A) | degraded (Stage B) | change | Stage B exits | Stage B steps | Stage A baseline steps |
|---|---|---|---|---|---|---|
| astropy__astropy-12907 | 5/5 | 5/5 | 0.0 | 5 Submitted | 29–33 | 28–35 |
| pallets__flask-5014 | 5/5 | 5/5 | 0.0 | 5 Submitted | 25–38 | 23–44 |
| matplotlib__matplotlib-13989 | 5/5 | 3/5 | −0.4 | 3 Submitted, 2 LimitsExceeded | 31–40 | 29–42 |
| mwaskom__seaborn-3069 | 3/5 | 0/5 | −0.6 | 5 LimitsExceeded | 40 ×5 | 98–160 |
| django__django-10097 | 5/5 | 0/5 | −1.0 | 5 LimitsExceeded | 40 ×5 | 44–102 |

Steps are `model_calls` from each run's `agent_run.json`.

**The mechanism.** Stage A's baseline step counts predict the pattern exactly:
- tasks the agent solves in under 40 steps (astropy, flask) were untouched;
- the task that straddles 40 (matplotlib) was hit partially;
- the tasks that need 44–160 steps (django, seaborn) collapsed completely.

Every run that hit the limit failed, and every run that submitted resolved.
The degradation is real, large and mechanistically explained. It is also
**concentrated**: two tasks at −1.0 and −0.6, one at −0.4, and two at 0.

### Conclusion

**CI v0 specificity established; sensitivity not established. Milestone not
achieved.**

Acceptance requires both halves (see *Acceptance*). The unchanged candidate
passed. The pre-declared degraded candidate, which lost 40 points with two
tasks collapsing completely, also passed.

The finding is about the method: **the frozen estimand and decision rule (a
paired bootstrap over five tasks, requiring the interval's upper end to clear
−0.10) do not detect a concentrated regression.** This is the case recorded in
the pre-Stage-B deviation above, before any Stage B data existed, and it
occurred as described there.

This is not attributed to sample size. That explanation has not been tested
and is not claimed here. The frozen rule was also not re-run with other
settings. `ci_high` −0.08 against a −0.10 bar is a PASS under the rule as
frozen, and it stays one.

### What this does not change

No product decision semantics, threshold, minimum evidence, bootstrap logic,
task set or product code changed, and the Stage B intervention was not merged.
Any redesign, starting with what should count as a regression in agent CI
(broad population regression, severe per-task regression, or both), is a new,
separately declared stage. It is not a revision of this one.

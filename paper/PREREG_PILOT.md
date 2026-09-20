# Pre-registration — Gate 2 feasibility pilot

**Written 2026-09-20, before any pilot run exists and before any machine is
rented.** `study_mode: feasibility`, `verdict_authority: descriptive_only`.
**This pilot cannot produce a release claim**, and the contract enforces that
rather than a footnote.

---

## 1. Subject

| | |
|---|---|
| Agent | `mini-swe-agent`, pinned to the exact commit recorded at setup |
| Scaffold | `InteractiveAgent`, `mode: yolo`, prompt version `mode-b-pilot-0` |
| Model | `Qwen/Qwen3.6-27B-FP8` @ `e89b16ebf1988b3d6befa7de50abc2d76f26eb09` |
| Serving | `inference/configs/model_h2.yaml` — `max_model_len` 131072, prefix caching, `max_num_seqs` 4, `enable_auto_tool_choice`, `tool_call_parser qwen3_coder`, `reasoning_parser qwen3` |
| Evaluator | SWE-bench `resolved`, deterministic, the checker verified 20/20 offline (`c2h_checker.py`) |
| Images | official SWE-bench per instance, digest resolved and frozen before run 0 |

### Task selection — mechanical, and fixed before any run

Three SWE-bench Verified instances, drawn by this rule and **not** by which
produce a larger effect:

1. restrict to instances whose official image pulls on the host;
2. sort by instance id, ascending, lexicographically;
3. take the first three that are **not** `pytest-dev__pytest-10051`.

The exclusion is deliberate: that instance produced the frozen donors and the
two existing counterexamples, and reusing it would let prior familiarity into a
set meant to test the method.

The drawn ids are recorded in the run manifest **before** the first run and are
not revised.

### Baseline reuse

One baseline arm is shared across all three mutations, on the condition that
the agent, scaffold, prompt, model, serving configuration, image digests, task
set and evaluator are byte-identical. Any difference and the comparability gate
refuses before trials — it is not a judgement call.

## 2. Mutations

Exactly one configuration value changes per arm. **Tool timeout stays
deferred**: measured through wall clock, it inherits the machine's variance,
and the reference runs span 258 s to 3107 s on identical configuration.

### M1 — reduce `max_steps`

- **Changes:** the agent's step limit, and nothing else.
- **Causal hypothesis:** tasks needing more steps than the limit are truncated
  before a fix is complete, so fewer resolve.
- **Primary feature:** `task_success`, direction **decrease**.
- **Negative control:** `tool_reliability` — the agent loses budget, not the
  ability to call tools.
- **Practical threshold:** 0.10 (risk difference).
- **Supports** the hypothesis: task success falls past threshold while tool
  reliability holds, and truncated-run rate rises.
- **Weakens** it: tool reliability falls in step, suggesting the mutation is
  less targeted than claimed.
- **Cannot answer:** fewer than the registered minimum scenarios yield a valid
  comparison.

### M2 — remove the malformed-call recovery hint

- **Changes:** one instruction removed from the prompt.
- **Causal hypothesis:** without it the agent retries a malformed call the same
  way instead of correcting it, so runs that hit a malformed call stop
  recovering.
- **Primary feature:** `recovery_success`, direction **decrease**.
- **Negative control:** runs that never hit a malformed call — their
  `task_success` should be unchanged.
- **Practical threshold:** 0.15 (risk difference, conditional on the event).
- **Supports:** recovery falls past threshold among eligible runs while clean
  runs hold.
- **Weakens:** clean runs fall too, meaning the removed text did more than
  recovery.
- **Cannot answer:** too few runs encounter a malformed call to estimate the
  conditional rate — a real possibility, recorded here rather than discovered
  as a disappointment.

### M3 — prune context earlier

- **Changes:** the context-pruning trigger, and nothing else.
- **Causal hypothesis:** facts needed late are dropped, so long tasks fail more.
- **Primary feature:** `task_success`, direction **decrease**.
- **Negative control:** `tool_reliability` — pruning changes what is remembered,
  not whether a call executes.
- **Practical threshold:** 0.10.
- **Supports:** task success falls past threshold, concentrated in longer runs,
  with tool reliability held.
- **Weakens:** the fall is uniform across run lengths, which the hypothesis does
  not predict.
- **Cannot answer:** all three tasks resolve in few steps, so pruning never
  triggers.

## 3. Trial design

```
3 tasks × [baseline + M1 + M2 + M3] × 2 repetitions = 24 runs
per-run wall-clock cap: 1200 s
```

**Two repetitions is thin, and that is a property of a $30 pilot, not an
oversight.** It estimates within-scenario variance barely. It is registered as
a limitation, and §5 forbids adding repetitions later to change a result.

The cap is registered, not operational. A run exceeding it is **INVALID** under
the contract's `invalid_policy`, and the invalid rate is reported beside every
number. It exists because the tail is what breaks the budget: at the reference
distribution, one run in five exceeds 1200 s, and without a cap a single
3107-second run costs more than a whole arm.

`study_mode: feasibility` · `verdict_authority: descriptive_only`.

## 4. Statistics, frozen

- **Independent unit: scenario.** Repetitions estimate within-scenario
  randomness and are **never** counted as independent N.
- Paired scenario-level comparison; the pairing is the task.
- Effect: risk difference for rates, median ratio for cost; intervals by paired
  bootstrap **over tasks**.
- Invalid-run policy from the contract; invalid runs are never scored as
  failures.
- Three consecutive invalid runs stop the batch (infrastructure fail-fast).
- Aggregation across gating features: `any`, declared in advance.
- Trace features never gate. They annotate.
- RCA runs **only** if a `REGRESSION` arises naturally.

## 5. The four-cell trap, closed in advance

**Obtaining a `REGRESSION` is not a success condition for this pilot.**

If a registered mutation produces no regression, the result stands as a null:

- the mutation is **not** strengthened;
- the tasks are **not** changed;
- the threshold is **not** lowered;
- repetitions are **not** added to earn one.

The conclusion is then: *this mutation did not cause a detectable practical
degradation in this pilot.* Gate 2 is incomplete — **the experiment is not.**

`INSUFFICIENT_EVIDENCE` must likewise arise from real evidence conditions.
**Deliberately under-running an arm to fill a report cell is forbidden.** The
existing fake-run artifacts already prove the software path; the pilot exists
to test the method's behaviour, and a manufactured cell tests neither.

## 6. Cost model

From the reference distribution — median 475 s, mean 1050 s, max 3107 s per run
— at $3.29/h with 0.6 h of setup, download and retrieval:

| Design | Cap | Runs | Worst | Median |
|---|---:|---:|---:|---:|
| 3×4×3 = 36 | none | 36 | **$104** | $17.60 |
| 3×4×3 = 36 | 900 s | 36 | $31.58 | $17.60 |
| cached baseline, 27 | 1200 s | 27 | $31.58 | $13.69 |
| **3×4×2 = 24** | **1200 s** | **24** | **$28.29** | **$12.39** |

**Only the last fits $30 at the worst case**, and it has the lowest invalid
risk of the fitting designs (1 reference run in 5 exceeds 1200 s, against 2 in 5
at a 600 s or 900 s cap).

The uncapped 36-run shape the review proposed has a **mean** of $36.51 — above
the absolute stop. It would not have overrun occasionally; it would have been
truncated on a typical day.

**Stops**, on cumulative spend measured against a baseline frozen before run 0:

| | |
|---|---|
| $20 | warning |
| $25 | start no new arm |
| $30 | absolute stop |

Re-estimated at three fixed points only: after setup, after the baseline arm,
and before each mutation arm. **If the conservative estimate exceeds $30 before
starting, the design shrinks or the run does not happen. Cells are never
deleted once running.**

## 7. Gate 2 criteria

- features extract stably across all arms;
- **at least two mutations move in the registered direction** — direction, not
  significance;
- negative controls do not degrade in step with their primaries;
- a harmless trace change does not trigger the gate;
- a fingerprint mismatch returns `INCOMPARABLE` with **zero** trials;
- the report is legible to a developer without a walkthrough;
- if a regression arises, RCA localises to the stage actually modified.

## 8. Open before this is executable

- the three task ids, drawn by §1's rule;
- the agent commit and image digests;
- the exact `max_steps`, pruning trigger and prompt-line values for M1–M3;
- confirmation of the 24-run / 1200 s design, which trades repetitions for
  budget certainty and is the one choice here that is a judgement rather than
  an arithmetic consequence.

---

# Amendment P.1 — boundaries on the 1200 s cap and the 24-run shape

**2026-09-20, before any run.** The design is accepted as a **budget-censored
feasibility pilot**, not a small statistical experiment. These six boundaries
exist so the cap cannot leak into the interpretation of the results.

## 1. A timeout is not a task failure

```
1200 s reached → INVALID / CENSORED
```

**Never scored as a failed task.** Otherwise a budget rule manufactures a
regression out of long tasks, and the longest tasks are exactly the ones M1 and
M3 are hypothesised to affect.

Reported beside every number:

- capped runs per arm;
- capped runs per task;
- steps completed before the cap;
- **differential censoring** between baseline and each candidate.

If a mutation hits the cap more often than baseline, that is a **feasibility
observation** and is reported as one. It is **not** written as an outcome
regression: "the run was stopped for cost" and "the agent got worse" are
different statements, and only the second is a regression.

## 2. A cell needs 2 of 2 valid to be interpreted

Each `task × arm` is registered for two repetitions.

| Valid | Treatment |
|---|---|
| 2 / 2 | descriptive comparison permitted |
| 1 / 2 | **cell is insufficient** |
| 0 / 2 | **cell is insufficient** |

No re-running. No substituting another task. No borrowing evidence from another
cell. Without this, "exactly two repetitions" quietly becomes "two, and more
when two is not enough", which is optional stopping on the quantity being
measured.

## 3. $28.29 is not margin

It is $1.71 under the stop, and the following are not in it: pre-start time,
download and warm-up, billing lag, artifact retrieval, and a bill that updates
only after a block has begun.

All three stops stand:

| | |
|---|---|
| $20 | warning |
| $25 | **start no new block** |
| $30 | absolute stop |

**At $25 the run does not continue because "only the last block is left".**
That sentence is exactly how a ceiling becomes advisory.

So **24 runs is the planned shape, not a guaranteed one.** If the budget
truncates it, the output is a `budget-censored feasibility run` and **no Gate 2
verdict** — the same rule as §6.4 of the C2-H registration.

## 4. Block order: frozen, interleaved, hashed

Not all baseline first, then mutations in order. Drift over the session would
then align with arm.

Generated from seed `20260920`, fixed here, entering the manifest hash:

```
rep 0  task_1: M3, M1, baseline, M2
rep 0  task_2: M2, baseline, M1, M3
rep 0  task_3: M2, baseline, M1, M3
rep 1  task_1: baseline, M3, M2, M1
rep 1  task_2: M2, baseline, M1, M3
rep 1  task_3: M2, M1, M3, baseline

order_hash  a0d4df1f7729e04e      24 cells
```

**Not adjustable during the run.** A reordering mid-session is a different
experiment, and the hash says so.

## 5. `max_steps` and the wall-clock cap are different terminations

M1 changes the **agent's step budget**. 1200 s is **infrastructure spend
protection**. They must never be recorded as the same event:

| Termination | Meaning |
|---|---|
| agent stopped by `max_steps` | a **mutation outcome** — this is what M1 does |
| harness stopped at 1200 s | a **censored observation** — says nothing about the agent |

Collapsing them would let the budget cap masquerade as M1's effect, which is
the single most likely way this pilot could produce a wrong answer that looks
right.

## 6. What this pilot can and cannot answer

**Can:** whether the three features extract stably · whether each mutation
moves in its registered direction · whether a negative control moves in step ·
whether invalid runs and censoring make the design unusable · whether the PR
report is intelligible · whether the system completes most or all of the plan
within budget.

**Cannot:** statistical power · a calibrated false-positive rate · general
effectiveness · a release-grade regression · generalisation across agents.

**The independent unit count is three.** Two repetitions do not make `N = 6`,
and no sentence in the write-up may imply otherwise.

## Decision

> **3 tasks × 4 arms × 2 repetitions, 1200 s cap.**

The only shape that keeps three tasks, three mutations and repeated
observation under $30. The price is that every conclusion is descriptive
feasibility, and **no censored cell is ever re-run**.

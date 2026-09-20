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

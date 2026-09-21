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

---

# Amendment P.2 — final pilot parameters

**2026-09-20, before any run.** Supersedes the arm set, the trial shape and the
order in §2–§3 and P.1 §4. Everything else stands.

## The three arms

| Arm | Recovery challenge | `step_limit` | `format_error_template` |
|---|---|---:|---|
| baseline | yes | 250 | full guidance |
| **M1** | yes | **40** | full guidance |
| **M2** | yes | 250 | **`<error>` only** |

Both comparisons remain single-axis: **M1 vs baseline** changes only the step
limit; **M2 vs baseline** changes only the recovery guidance.

**M3 is removed.** `mini-swe-agent` has no context-pruning axis — `AgentConfig`
exposes `step_limit`, `cost_limit`, `wall_time_limit_seconds` and
`max_consecutive_format_errors`, and neither environments nor models carry
pruning or context-window management. Building the feature in order to test it
would be circular, and filling the slot with `cost_limit` would only restate
M1's resource-exhaustion mechanism.

### M1 = 40, and what chose it

| `step_limit` | binds | % of live reference runs |
|---:|---:|---:|
| 30 | 24 | 83% |
| **40** | **15** | **52%** |
| 45 | 6 | 21% |
| 125 | 0 | 0% |

250 never binds — the largest observed run is 81 steps — so halving it would
have changed nothing.

**29 of the 32 reference runs come from one task family.** The 52% is a
strength-selection input, **not a prediction of activation on the held-out
tasks**, and no sentence may treat it as one.

### The recovery challenge is a test condition, not a scored mutation

Every arm meets the same injected malformed call at the same point: the first
valid tool call is recorded, **never executed**, and the agent travels its
ordinary `FormatError` path. Injecting only into M2 would make baseline differ
from it on two axes — the event and the guidance — and nothing could be
attributed.

Feasibility verified with a fake model and environment
(`tests/test_recovery_challenge.py`, 10 tests): the injection point, all three
arms, exactly once per run, baseline/M2 identical but for the guidance text,
the suppressed call never reaching the environment, and the artifact keeping
the original call, the event and the recovery.

## The limit this creates, written before the results

> **M1 estimates the conditional effect of a lower step limit *after* one
> pre-registered malformed-call challenge — not the general step-limit effect
> on ordinary fault-free runs.**

Admissible:

> Under the registered recovery challenge, reducing `step_limit` from 250 to
> 40 produced the observed change.

**Not admissible:**

> ~~`step_limit = 40` generally reduces success.~~

Likewise **M2 measures recovery after a controlled challenge, and estimates
nothing about how often malformed calls occur in production.** The natural rate
in the reference data is 5 of 32 runs, which is why the event is registered
rather than awaited.

## Rules that follow

- `NOT_ELIGIBLE` runs — those that never produced a first valid tool call —
  enter **neither** the recovery denominator **nor** the failure count.
- The steps the challenge itself consumes are **not** refunded from M1's
  40-step budget. M1 is "40 steps, one of which met a challenge", and that is
  what is reported.
- Termination codes stay separate: an agent stopped by its **step budget** is a
  mutation outcome; a harness stop at **1200 s** is a censored observation
  (P.1 §5).
- If many runs are `NOT_ELIGIBLE`, M2's conclusion is **insufficient**. No
  additional injection, no re-running.

## Shape and order

```
3 tasks × 3 arms × 2 replicates = 18 runs
per-run infrastructure cap: 1200 s
worst case ≈ $21 against a $30 stop — real margin, not $1.71
```

Regenerated from seed `20260920` over the **new 18-cell set**, not by deleting
M3 from the old 24-cell order, so the sequence is determined by the registered
set as a whole:

```
rep 0  task_1: baseline, M1, M2
rep 0  task_2: M2, M1, baseline
rep 0  task_3: baseline, M2, M1
rep 1  task_1: M2, M1, baseline
rep 1  task_2: M2, baseline, M1
rep 1  task_3: M2, M1, baseline

order_hash  cfe8856c9c9167b5      18 cells      (supersedes a0d4df1f7729e04e)
```

Not adjustable during the run.

## Remaining, and mechanical

On the instance, before any run: draw the three tasks by §1's rule, freeze the
agent commit, resolve the image digests, verify the model and serving stack,
enter the billing baseline, and hold a final review.

**No real pilot run is produced until all six are done.**

---

# Amendment P.3 — repository diversity in the task draw

**2026-09-21, before any instance is launched, with zero pilot runs in
existence and no pilot outcome of any kind.** `pilot_runs = 0` at the time of
writing, and the only hosts ever rented produced no cell.

## What was found

§1's rule was:

1. restrict to instances whose official image pulls on the host;
2. sort by instance id, ascending, lexicographically;
3. take the first three that are not `pytest-dev__pytest-10051`.

Resolving it against SWE-bench Verified **before launch** showed what it
mechanically produces: the ids sort ascending, `astropy__astropy-*` occupies
the head of the list, and all three slots are filled from that one repository.

That is not a bad draw because of what the tasks are. It is a bad draw because
the pilot reports three scenarios and treats the scenario as the independent
unit (§4). Three instances of one repository share a codebase, a test runner,
a dependency set and a failure vocabulary, so the extrapolation the design
assumes is narrower than the design claims. The defect is in the rule, not in
any result.

## Why this is a pre-run amendment and not a post-hoc one

No pilot outcome exists to have influenced it. Nothing about the drawn tasks'
difficulty, success rate or effect size is known, and no run has been scored.
What was inspected is the **shape of the candidate list**, which is a property
of the universe and the sorting rule alone. Fixing it now costs nothing; the
same fix after the run would be selecting tasks with knowledge of results, and
would be inadmissible.

## The rule, as amended

1. exclude `pytest-dev__pytest-10051`;
2. sort all candidates by instance id, ascending;
3. walk the sorted list in order;
4. a candidate is selected only if its image pulls **and** its repository is
   not already represented;
5. stop at three tasks from three distinct repositories;
6. every candidate examined is written down with why it was skipped —
   `excluded_registered`, `duplicate_repository`, `pull_failed`, or `selected`;
7. if the list is exhausted with fewer than three distinct repositories,
   preflight **stops**. The rule is not relaxed to finish the draw.

**Ordering note.** In the implementation the repository check runs *before* the
pull, and that ordering is an efficiency decision with no effect on the result:
a candidate whose repository is already represented is never selected under
either ordering, so the drawn set is identical. `select_tasks` is tested
against a pull-first implementation to prove it. Pulling first would fetch
every remaining instance of an already-selected repository — on this universe
more than a hundred multi-gigabyte images — only to discard them.

**Nothing else may move a draw.** The rule is given the ascending id order, the
exclusion list, the repository derived from the id, and whether a pull
succeeded. It is not given how long a pull took, how hard a task looks, or
anyone's preference among instances.

## What moves, and what does not

| | |
|---|---|
| `protocol_hash` | **`3ee68b88bb99894d` → `e1f786939faeb9ea`** |
| `ORDER_HASH` | **`cfe8856c9c9167b5`, unchanged** |

How the tasks are drawn is part of the experimental design, so
`TASK_SELECTION` is now inside `protocol_hash` and the hash moves with it. The
18-cell order does **not** move: it binds the *positions* `task_1..task_3`, and
never the ids that fill them. A test asserts the order hash is identical for
`["task_1", "task_2", "task_3"]`, for real instance ids, and for arbitrary
strings.

## Scope

Arms, step limits, the recovery-hint variant, task count, replicates, the
1200 s cap, the budget stops and the block order are all untouched. This
amendment changes which three tasks are drawn and nothing else.

`study_mode: feasibility` · `verdict_authority: descriptive_only`.

---

# Amendment P.4 — a pre-registered infrastructure smoke test

**2026-09-21, written before the next machine is rented, with `pilot_runs = 0`
and `model_requests = 0`.** No pilot cell has ever executed, so nothing about
the drawn tasks' behaviour is known and nothing here can have been chosen with
knowledge of a result.

## What this fixes

Host 2 passed every environment check and reported
`READY_FOR_MANUAL_PILOT_CONFIRMATION` while the component that executes a cell
did not exist. `agentseism.pilot` refused `--backend real` with a placeholder,
and the only backend in the tree was `fake_backend`. **Preflight verified the
environment and never verified that a cell could run.**

Two answers, and they are different in kind. A *construction* check belongs in
preflight: the real backend must be importable and constructible, or preflight
fails. A *path* check cannot be done by construction, because a container that
starts, an agent that emits a tool call, a challenge that fires once and an
evaluator that returns a definite verdict are only demonstrated by running
something. Hence a smoke test — and a smoke test has to be registered, or it
becomes the place where the experiment is quietly tuned.

## The smoke test, frozen

| | |
|---|---|
| Task | `pytest-dev__pytest-10051`, **one** instance |
| Arm | `baseline` only — `step_limit` 250, `hint` full, `challenge` True |
| Replicates | 1 |
| Cap | 1200 s wall clock, the registered pilot cap |
| Output | `data/runs/smoke/`, never `data/runs/pilot/` |
| Marking | every artifact carries `smoke: true` and `pilot_evidence: false` |

**The task is the excluded one on purpose.** `pytest-dev__pytest-10051`
produced the frozen donors and both counterexamples, and P.3 excludes it from
the pilot for exactly that reason. That disqualification is what makes it the
right smoke subject: it cannot enter the pilot's task set, so using it here
cannot narrow or bias the draw, and prior familiarity with it is an advantage
when the question is *did the plumbing work* rather than *how hard is this
task*.

**One arm, no comparison.** The smoke test runs `baseline` and nothing else. It
does not compare arms, does not estimate an effect, and cannot produce or
inform a verdict. A smoke test that ran M1 alongside baseline would be a
one-scenario pilot with an unregistered analysis, whatever it was called.

## Pass criteria — the chain, not the outcome

The smoke test passes if and only if all of these hold:

1. the task image starts and `/testbed` is present at the base commit;
2. the agent produces at least one **valid** tool call;
3. the challenge fires **exactly once**, and the original malformed action is
   **not** executed;
4. the run terminates with a code in the registered set, with
   `INFRA_TIMEOUT_1200S` and `STEP_LIMIT_REACHED` distinguishable in the
   record;
5. the evaluator returns an explicit `resolved` true **or** false — an
   infrastructure error is neither, and is not counted as a failure;
6. the artifact is written atomically and verifies against its own digest.

**Whether the task resolves is not a pass criterion.** A smoke test that
required success would be a difficulty filter wearing a plumbing test's name,
and `resolved: false` with the chain intact is a pass.

## If it fails

Stop. No pilot runs. Record which of the six conditions failed and terminate
the host. The smoke test is not re-run with adjusted parameters to obtain a
pass: a chain that needs adjusting to work is a chain that was not frozen.

## Cost and ordering

Smoke spend is **inside** the pilot's registered cost — §1 puts launch,
preparation, download and teardown there, and this is preparation. So the
order on the next host is fixed:

```
baseline read with nothing running  →  launch  →  reading #1
  →  preflight (envs, draw, weights, vLLM)  →  smoke test
  →  read Usage  →  after_setup checkpoint   ← captures the smoke cost
  →  read Usage  →  before_block 0           ← one reading, one block
```

`after_setup` follows the smoke test so that the smoke test's spend is inside
the checkpoint rather than outside it.

**The smoke test runs on the same vLLM session that will serve the pilot**, and
the serving fingerprint is taken **after** it. The session that is bound is
therefore the session that actually served something, which is a stronger
binding than one taken against a server that has answered nothing. All 18 cells
already share one session, so a session that has served one extra task before
cell 0 is not a new kind of variation — it is the variation the design already
accepts, made uniform at the start.

## Scope

Arms, step limits, the recovery-hint variant, task count, replicates, the
1200 s cap, the budget stops, the block order and the P.3 draw are all
untouched. This amendment adds a gate before run 0 and changes nothing the
pilot measures.

`study_mode: feasibility` · `verdict_authority: descriptive_only`.

---

# Amendment P.5 — the recovery hint, frozen as text

**2026-09-21, before Host 3 is rented, with `pilot_runs = 0` and
`model_requests = 0`.** No pilot cell has ever executed and no outcome of any
kind exists.

## What was missing

`ARMS` recorded `M2: hint: "error_only"` and §2 described the mutation as
"remove the malformed-call recovery hint". **Neither template existed
anywhere in the tree.** `error_only` appeared in exactly three places: the arm
definition, one test assertion, and the deployment checklist. Nothing said what
text it stood for.

That is not a documentation gap. How much of the guidance comes out *is* M2's
effect size: remove the whole block and the mutation is large, remove one line
and it may be undetectable at 18 runs. Left as it was, whoever implemented the
backend would have chosen the mutation's magnitude while writing it.

## The source

| | |
|---|---|
| Package | `mini-swe-agent==2.4.6`, pinned in `inference/requirements-eval.lock.txt` |
| File | `minisweagent/config/benchmarks/swebench.yaml` |
| Key | `model.format_error_template` |
| File sha256 | `9a9c86ac10428b86b932c972b15fefc2f7b6e92230bac5ebdc47e83232a8315e` |

`full` is that value byte-for-byte. It is what `recovery_challenge.py` already
renders through `self.model.config.format_error_template`, so the baseline arm
is the upstream default and not a variant authored here.

## The transformation

> In the `else` branch keep `Tool call error:` and the `<error>` block; delete
> from `Here is general guidance on how to submit correct toolcalls:` to the
> end of that branch. The `finish_reason` branch is kept verbatim.

The rule is recorded **and both results are frozen byte-for-byte**. A rule
alone would let a different upstream version produce a different mutation under
the same registration, which is the failure this amendment exists to close.

```
full        878 bytes   sha256 0f35cfbd448dd46e17e80b571d346256d4a75cd5ceffafc5c0d088ed0e1c0d9a
error_only  447 bytes   sha256 450d5d015b1518c7903a90b6c1fcba6a76923c32582b9448b8300a7a29da428c
```

Both live in `pilot_protocol.HINTS`, in full.

### `full`

```jinja
{% if finish_reason is defined and (finish_reason == "length" or (finish_reason == "tool_calls" and not has_tool_calls)) -%}
Your previous response reached the output token limit (finish_reason={{ finish_reason }}) before you produced a tool call, so it was cut off. Respond more concisely and finish with exactly one bash tool call. If you need to think more, do so briefly.
{%- else -%}
Tool call error:

<error>
{{error}}
</error>

Here is general guidance on how to submit correct toolcalls:

Every response needs to use the 'bash' tool at least once to execute commands.

Call the bash tool with your command as the argument:
- Tool: bash
- Arguments: {"command": "your_command_here"}

If you have completed your assignment, please consult the first message about how to
submit your solution (you will not be able to continue working on this task after that).
{%- endif %}
```

### `error_only`

```jinja
{% if finish_reason is defined and (finish_reason == "length" or (finish_reason == "tool_calls" and not has_tool_calls)) -%}
Your previous response reached the output token limit (finish_reason={{ finish_reason }}) before you produced a tool call, so it was cut off. Respond more concisely and finish with exactly one bash tool call. If you need to think more, do so briefly.
{%- else -%}
Tool call error:

<error>
{{error}}
</error>
{%- endif %}
```

The whole guidance block is removed, not part of it. For a feasibility pilot
that is the defensible boundary: a mutation too small to detect at n = 18
teaches nothing, and P.1 forbids strengthening it afterwards to obtain a
result. The contrast is clean — error content plus how to recover, against
error content alone — so what M2 varies is the presence of explicit recovery
guidance rather than the wording of one example.

## Estimand, deliberately narrow

> Under the registered synthetic malformed-call challenge, compare recovery
> when the agent receives the complete upstream recovery guidance against the
> error content alone.

It does **not** generalise to "removing error handling reduces agent success",
and it estimates nothing about how often malformed calls occur naturally. The
challenge is part of the scenario, identical in every arm, and registered
before any run.

## Binding rules

1. The backend resolves the template as `HINTS[arm["hint"]]`, exactly. No
   fallback, no runtime transformation, and no re-reading from the installed
   package.
2. `verify_hints()` runs at startup: both frozen templates must hash to their
   registered digests, **and** `full` must still be byte-identical to the
   pinned upstream. A mismatch stops the run. A newer `mini-swe-agent` that
   reworded the template is a different experiment; the frozen text is not
   adapted to it.

## What moves

| | |
|---|---|
| `protocol_hash` | **`e1f786939faeb9ea` → `a23ff8975a04f627`** |
| `ORDER_HASH` | **`cfe8856c9c9167b5`, unchanged** |

The hint digests enter `protocol_hash` because the template *is* the mutation.
The order still binds positions, not ids or text.

## Scope

Arms, step limits, task count, replicates, the 1200 s cap, the budget stops,
the block order, the P.3 draw and the P.4 smoke test are untouched. This
amendment gives M2's registered axis a referent and changes nothing else.

`study_mode: feasibility` · `verdict_authority: descriptive_only`.

---

# Amendment P.6 — `FORMAT_ERROR_LIMIT_REACHED`, and the exit-status mapping

**2026-09-21, before Host 3 is rented, with `pilot_runs = 0` and
`model_requests = 0`.**

## What was found

Mapping `mini-swe-agent` 2.4.6's exit statuses onto the registered
terminations left one with nowhere to go: `RepeatedFormatError`, raised when
the agent hits `max_consecutive_format_errors`.

**That is exactly M2's predicted failure mode.** M2 removes the recovery
guidance and asks whether recovery gets worse; an agent told nothing about how
to fix a malformed call is the agent that repeats one until the limit. Mapping
it to `INVALID` would have made it non-scorable, so the harder the mutation
bit, the more runs would leave the denominator and the less of the effect would
remain measurable. That is not a conservative default. It is self-cancelling.

## The registered mapping

| `mini-swe-agent` exit | termination | scored |
|---|---|---|
| `Submitted` | `COMPLETED` | yes |
| `LimitsExceeded` | `STEP_LIMIT_REACHED` | yes |
| `TimeExceeded` | `INFRA_TIMEOUT_1200S` | **no** — censored, cost control |
| `RepeatedFormatError` | `FORMAT_ERROR_LIMIT_REACHED` | yes |

`FORMAT_ERROR_LIMIT_REACHED` joins `TERMINATIONS` and `SCORABLE`. It is
structurally identical to `STEP_LIMIT_REACHED`: an agent-behaviour termination,
not an infrastructure fault; it keeps its real name; the evaluator runs; and it
enters the outcome only on an explicit boolean `resolved`.

```text
agent_termination_code: FORMAT_ERROR_LIMIT_REACHED
evaluator_resolved:     true | false
outcome_state:          RESOLVED_TRUE | RESOLVED_FALSE
enters_pilot_outcome:   true
```

## Two boundaries

- **The challenge never fired** — no first valid tool call, so nothing was
  injected: `NOT_ELIGIBLE`. Out of M2's recovery denominator, and never a
  recovery failure.
- **The challenge fired once, then the format-error limit was reached**:
  `FORMAT_ERROR_LIMIT_REACHED`. The evaluator runs and the run counts. This is
  M2's interpretable mechanism, not an invalid run.

## What the mapping rests on

Two claims about the pinned package, registered because they are not things
upstream states.

**`cost_limit = 0` disables the cost branch.** From
`DefaultAgent.query` in 2.4.6:

```python
if 0 < self.config.step_limit <= self.n_calls \
        or 0 < self.config.cost_limit <= self.cost:
    raise LimitsExceeded(...)
```

`0 < 0` is false, so with `cost_limit = 0` the cost branch is unreachable. Only
`step_limit` is a registered axis, so it is set to 0 and `LimitsExceeded` can
then mean only one thing.

**`LimitsExceeded` carries no structured reason.** One exception serves both
limits, and its payload is the bare string `"LimitsExceeded"` — there is no
field naming which limit fired. The mapping to `STEP_LIMIT_REACHED` is
therefore sound *only* because the cost branch is unreachable. The backend
additionally asserts `n_calls >= step_limit` when it fires; **if that assertion
fails the run is `BACKEND_ERROR`, not a step limit.**

Both claims are asserted against the installed source by
`tests/test_exit_mapping.py`, so a later version that adds a reason, renames a
status, or changes the counting is a visible break rather than a silent
misclassification.

## What moves

| | |
|---|---|
| `protocol_hash` | **`a23ff8975a04f627` → `5f4b95c9a250fccf`** |
| `ORDER_HASH` | **`cfe8856c9c9167b5`, unchanged** |

`EXIT_STATUS_MAP` and `SCORABLE` are inside `protocol_hash`: how an agent exit
becomes a termination, and which terminations may be scored, are part of the
design.

## Scope

Arms, step limits, the hint text, task count, replicates, the 1200 s cap, the
budget stops, the block order, the P.3 draw and the P.4 smoke test are
untouched.

`study_mode: feasibility` · `verdict_authority: descriptive_only`.

---

# Amendment P.7 — the post-block cost check

**2026-09-21, before Host 3 is rented, before any block has been executed and
before any block cost exists.** `pilot_runs = 0`.

## Why it is registered rather than applied

The cost model says roughly `$21` for 18 runs plus the smoke test — about
`$1.17` a run, so about `$3.50` for a three-cell block. It would be easy to
treat "block 0 cost more than `$3.50`, stop" as an operational judgement.

It is not one. It is a **stopping rule**, and a stopping rule adopted while
looking at the number it applies to is the thing this registration exists to
prevent. It is written here, before Host 3 exists, so that it cannot be.

## The rule

> After Block 0, use the pre-specified bracketing billing readings to compute
> marginal cost per run and project the remaining 15 runs. If the resulting
> projected cumulative pilot spend would exceed the already-registered `$30`
> absolute stop, halt before releasing subsequent blocks and re-model the
> remaining execution.

The bracketing readings are already required by the budget machine and are not
new instrumentation: the reading that authorised Block 0, and the reading
taken after it — which is the same reading that would authorise Block 1. The
block is therefore judged by the number that would release the next one.

```
block_cost    = spend_after_block − spend_before_block
marginal      = block_cost ÷ cells_in_block
projected     = spend_after_block + marginal × cells_remaining
halt          = projected > ABSOLUTE_LIMIT_USD
```

## `$3.50` is an expectation, not a threshold

`COST_EXPECTATION_PER_RUN = 1.17` is **reported** beside every
projection and decides nothing. The decision boundary is the `$30` absolute
stop that was registered before any of this existed.

This matters in both directions, and both are tested:

- a block costing `$3.60` is **above** the expectation and changes nothing,
  because the projection still lands at `$23.69`, inside the stop;
- a block costing `$6.00` halts, because finishing at that rate reaches
  `$38.09`.

Anchoring to `$30` also means the rule cannot be gamed by arguing about
whether `$3.50` was the right sanity number.

## The projection is optimistic on purpose

It charges the remaining runs at the marginal rate and adds **nothing** for
idle time between blocks, for teardown, or for the fixed cost of a session
that stays up. So it is a lower bound on what finishing would cost, and a
projection that already exceeds the limit cannot be rescued by arguing the
estimate was harsh.

Exactly at the limit is not past it: `halt` is strictly `>`.

## What a halt means

Not a failed experiment. The run becomes what §3 already provides for — a
**censored feasibility run**, with its artifacts kept and its cost model
recorded as the thing that failed. Blocks are not released at a rate already
observed to break the budget the registration set.

Nothing about the analysis changes: `study_mode: feasibility`,
`verdict_authority: descriptive_only`, and a halt yields fewer interpretable
cells, which §4 already handles.

## What moves

| | |
|---|---|
| `protocol_hash` | **`5f4b95c9a250fccf` → `8706c5300ea8e065`** |
| `ORDER_HASH` | **`cfe8856c9c9167b5`, unchanged** |

The check is a stopping rule, so it is inside `protocol_hash`. The order binds
positions and is untouched.

## Scope

Arms, step limits, the hint text, task count, replicates, the 1200 s cap, the
`$20`/`$25`/`$30` stops, the block order, the P.3 draw, the P.4 smoke test and
the P.6 exit mapping are all untouched. This amendment adds one check between
blocks and changes nothing the pilot measures.

`study_mode: feasibility` · `verdict_authority: descriptive_only`.

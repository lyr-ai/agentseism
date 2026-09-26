# Telecom confirmatory protocol

Written before any Telecom run. Bank is the discovery set and is frozen: no Bank
run informs anything below, and no Bank run may be added to rescue a result.

The discovery observation being tested is `commit_step -> Y_reason`,
`A_f = +0.34`, `p = 0.063` over 80 pairs, underpowered, with two of four features
below the pre-registered power threshold. It is suggestive and nothing more.

## Part 1 — Observational confirmation

### Primary hypothesis, one test

> **H1.** Within the same incident, runs that commit to a single root-cause
> component before completing the prescribed discriminating step reach less
> stable *reason* conclusions than runs that do not.

One-sided: earlier commitment associated with *more* reason instability. A
result in the opposite direction is a failure to confirm, not a finding.

### The feature, frozen

`early_commit`, boolean, defined from OpenRCA's own policy rather than from any
threshold observed in Bank:

    early_commit = the first instruction naming exactly one candidate component
                   occurs at or before the first instruction requesting trace data

The scaffold's rules make trace analysis the step that discriminates among
several simultaneously faulty components: *"If multiple faulty components are
identified at the same level, you should use traces and logs to identify the root
cause component."* Naming one component at or before that request means the
choice came from metrics and the trace was gathered to confirm it. The "at or
before" is deliberate -- in the discovery set two runs named their component
inside the very instruction that requested the trace.

Raw `commit_step` is not used: step indices confound with trajectory length. A
normalised `commit_step / total_steps` was considered and rejected for this test,
because choosing between it and any other continuous encoding would mean
comparing encodings on the discovery set. `early_commit` needs no threshold.

**Feasibility gate, declared here in advance.** If `early_commit` is constant
across the Bank discovery runs it cannot support any test and this protocol is
void; that check is a property of the definition, not a tuning step, and its
result is reported whichever way it falls. The definition does not change either
way -- a degenerate feature means abandoning the test, not re-cutting it.

### Primary outcome

`Y_reason`, the reported root-cause reason, compared exactly.

### Tasks

Telecom, every row whose required output includes **both component and reason**:
`task_6` (6 rows) and `task_7` (9 rows), 15 tasks, taken in file order. This is
the closest match to the Bank discovery setting that reaches an adequate task
count -- Telecom has only 9 `task_7` rows -- and the rule follows from the
hypothesis, which is about reason conclusions reached while localizing a
component.

`Y_occurrence` is undefined for `task_6` and is analysed on `task_7` rows only,
as an exploratory quantity.

### Trials and sample size

5 runs per task, 75 runs, 150 within-task pairs.

Tasks rather than trials, and no power calculation from the Bank effect estimate:
`A_f = +0.34` over 80 clustered pairs is too noisy to size an experiment from,
and treating clustered pairs as independent observations would understate the
requirement. 15 incidents against Bank's 8 is close to double the independent
units, which is the axis that matters.

### Statistics

- Within-task permutation, 20,000 shuffles, one-sided, `alpha = 0.05`.
- **One primary test.** No correction, because there is one hypothesis.
- Report `A_f` with both arms and the 2x2 margins.
- Estimable only if all four margins are non-empty; powered only if
  `min(n10+n11, n00+n01) >= 20`. An underpowered result is reported as
  underpowered whatever its p-value.

### Everything else is exploratory

`Y_component`, `Y_occurrence`, `candidate_width`, `telemetry_path`,
`service_focus`, accuracy against ground truth, per-task breakdowns. Reported,
never presented as confirmed, and not eligible to replace H1 if H1 fails.

`service_focus -> Y_component` stays excluded as outcome-proximal.

### What counts as failure

`p >= 0.05`, or an effect in the opposite direction, is recorded as a failure to
confirm. In that case the Bank signal is written up as a discovery-set artifact
and the commitment mechanism is not carried into the paper's claims. No
additional Telecom tasks, no additional trials, no re-cut feature.

## Part 2 — Intervention

Independent runs. Observational Telecom runs are not reused as the control arm,
so that any difference cannot come from being collected at a different time.

### The manipulation

Minimal and local. It does not tell the agent what to conclude and does not
insert a candidate the agent was not already entertaining:

    CONTROL    unmodified OpenRCA policy

    TREATMENT  at the first instruction naming exactly one candidate component,
               that instruction is returned unexecuted once, with a request to
               retain the alternatives it had itself listed and gather one more
               round of evidence. Control returns to the agent afterwards.

Fired at most once per run, at the point `early_commit` is defined over, so the
manipulation and the measured feature are the same event.

**One extra round, fixed.** Not tuned -- comparing one round against two on Bank
would be using the frozen discovery set to set an intervention parameter. One is
the minimal manipulation that can test the mechanism.

### Where the alternatives come from

The retained candidates must be ones the agent itself still had active: the
components named in its own most recent multi-candidate instruction or analysis.
If no such set exists in the run's own history, the intervention does not fire
and the run is recorded as non-compliant rather than given a synthetic candidate
set. Injecting a candidate the agent never considered would test a different
question.

### Comparisons

Primary: `Y_reason` divergence rate, treatment against control, within task.

Secondary, all exploratory: `Y_component` divergence, accuracy on all three
fields, trajectory length, compliance rate.

### Reading the outcome

Success is not defined as improved accuracy.

- Reason variation falls, accuracy unchanged -- supports the mechanism: premature
  narrowing amplifies variation without carrying information.
- Reason variation falls, accuracy falls -- also informative, and a
  stability/performance trade-off worth reporting as such.
- Reason variation unchanged -- the mechanism is not supported, whatever
  accuracy does.

Accuracy is reported in every case and decides nothing on its own.

## Frozen inputs

| | |
|---|---|
| Agent | `OpenRCA` RCA-agent, unmodified in Part 1 |
| Model | `gpt-4o-2024-05-13` |
| Temperature | 0.0 |
| Schema | `openrca/1` plus `early_commit`, frozen before any Telecom run |
| Systems | Telecom for confirmation; Market held back entirely |

Market is not touched. If Telecom confirms, Market is the only remaining
independent system, and spending it now would leave nothing to replicate on.

---

## Amendment — budget-constrained design, written before any Telecom outcome was examined

The 15-task design is infeasible at measured cost. Nothing below was chosen after
seeing a Telecom result: one Telecom run exists (row 4, run 0, from the batch
stopped when the balance ran low) and its prediction, trajectory and features
have not been read. It is discarded and row 4 is rerun as a clean batch, the same
treatment given to Bank row 23.

### What changed and why

Measured cost is **~$1.1 per run**, against the ~$0.04–0.21 per case reported for
this benchmark. The gap is structural: the controller resends its full history
every step (118k input tokens per run, measured over the 40 Bank runs), and the
Executor holds a second conversation that never appears in the controller's
saved prompts, so any estimate read off those files is a lower bound. 15 tasks x
5 runs is ~$83; the available balance is $32.

`gpt-4o-mini` was tested as a cheaper backbone and rejected -- see the feasibility
entry in `experiments.md`. It is not a drop-in: under the same scaffold it fails
to converge within the upstream 25-step budget, and `early_commit` does not mean
the same thing when commitment is not terminal.

### Revised design

**4 tasks x 5 runs = 20 runs, ~$22.** Tasks are the first four of the eligible
pool already fixed by the original rule -- Telecom rows 4, 7, 11, 12 -- taken in
file order, not reselected.

Five trials, not four: inference is within-task, and 5 runs give 10 pairs per
task against 4 runs' 6. Task count is what the budget cuts, as the original
protocol already specified.

About $10 of the balance is reserved for the intervention smoke test and for
failed runs, and is not available to this study.

### Everything else is unchanged

One primary hypothesis, `early_commit -> Y_reason`, one-sided, `alpha = 0.05`,
within-task permutation, no correction because there is one test. Same frozen
feature, same exclusions, same secondary list.

### This is a small study and will be reported as one

Four tasks is fewer independent units than Bank's eight, so a null result is
weak evidence against the hypothesis and a positive one is fragile. The honest
outcomes are:

- `p < 0.05` in the predicted direction: consistent with the discovery
  observation, on four incidents, and still requiring replication.
- `p >= 0.05` in the predicted direction: **directionally consistent but
  underpowered; independent confirmation inconclusive.**
- Opposite direction: failure to confirm.

No fifth task is added if the result falls just short. Adding tasks after seeing
a p-value is optional stopping whatever the budget allows.

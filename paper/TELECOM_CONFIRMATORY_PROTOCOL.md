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

# Stage C — Regression semantics design

2026-09-25, on `product/ci-v0` after `1f17ac1`. Design only: no code changes,
no runs, and the v0 decision logic is untouched.

**Status of every number drawn from Stage A/B below: exploratory.** This rule
was designed after both results were seen. Its agreement with them is
consistency by construction, not validation. Validation is the confirmatory
study in §5, on tasks the rule has never seen.

## 1. What went wrong in v0, in one line each

- **Stage A** showed that natural variation is not a regression. seaborn went
  3/5 → 2/5 on an unchanged candidate, and a gate must absorb that.
- **Stage B** showed that a single population estimand misses concentrated
  failure. Task success fell 0.92 → 0.52 and django went 5/5 → 0/5, yet the
  verdict was PASS, because a bootstrap over five tasks keeps `ci_high` near
  zero whenever some tasks are untouched.

These are two different risks. v1 names both and gives each its own
endpoint, instead of stretching one bootstrap rule to cover both.

## 2. The two risks

| | Gate 1 — broad regression | Gate 2 — severe task regression |
|---|---|---|
| question | Did the PR lower reliability across the suite? | Did a task that reliably worked stop working? |
| estimand | mean over tasks of `p_cand,t − p_base,t` (risk difference) | per task, `p_base,t − p_cand,t`, on eligible tasks only |
| experimental unit | task; trials are averaged within a task first | task; trials are Bernoulli draws of the agent on that task |
| minimum evidence | ≥ 5 tasks, ≥ 3 trials per arm (unchanged) | ≥ 5 valid trials per arm on the task |
| eligibility | all tasks | baseline success ≥ 0.8 (≥ 4/5). Others are **not monitored** by this gate and are listed in the report |
| practical threshold | 0.10 (unchanged) | observed drop ≥ 0.5 |
| uncertainty | paired bootstrap over tasks, 95%, seed 0, 2000 resamples (unchanged) | one-sided Fisher exact test on the 2×2 of successes by arm |
| fires when | `effect ≤ −0.10` **and** `ci_high ≤ −0.10` (unchanged) | drop ≥ 0.5 **and** `p ≤ 0.05 / K` |
| multiplicity | one test | Bonferroni over the K eligible tasks, fixed from the baseline before any candidate run |
| critical-task declaration | n/a | **not required in v1**, see §2.3 |
| invalid runs | `invalid_policy: stop` (unchanged) | any invalid run on a task makes that task ineligible, and it is reported |
| non-blocking signal | none | eligible task with drop ≥ 0.4 that did not fire → WARNING |

### 2.1 Why gate 1 is not changed

An alternative, `effect ≤ −0.10 and ci_high < 0`, would have fired on Stage B
(`ci_high` −0.08). On Stage A, though, it sits exactly on the edge
(`ci_high` = 0.00), so an unchanged candidate would have been one bootstrap
draw from a false block. Loosening gate 1 after seeing B is tuning to B, and
the concentrated case is gate 2's job anyway. Gate 1 keeps its v0 meaning:
confident that the suite lost at least 10 points.

### 2.2 How repeated runs are used, and why that is legitimate here

Gate 1 must not treat trials as independent evidence about the population:
five runs of one task are not five tasks. Gate 2 asks a question about a
**single task**: did the agent's success probability on this task drop? For
that question the trials *are* the sample, as repeated independent draws of a
stochastic agent on a fixed input. Each gate uses the unit its own question
needs.

### 2.3 Why critical tasks are not declared in v1

Declaring some tasks as critical means giving them a separate or larger share
of α. That is a second design decision, and it would need its own validation.
v1 treats every eligible task as equally important. A `critical:` list is a
candidate for v2.

### 2.4 What gate 2 can and cannot see (exact, not simulated)

One-sided Fisher p-values at 5 trials per arm:

| baseline → candidate | p |
|---|---|
| 5/5 → 0/5 | 0.0040 |
| 5/5 → 1/5 | 0.0238 |
| 4/5 → 0/5 | 0.0238 |
| 5/5 → 2/5 | 0.0833 |
| 3/5 → 0/5 | 0.0833 |
| 5/5 → 3/5 | 0.2222 |

What the gate can detect, and its false-alarm rate:

| trials per arm | K | fires from a perfect baseline at | worst-case false alarm per task |
|---|---|---|---|
| 5 | 5 or 7 | ≤ 0/5 (total collapse only) | 0.0010 |
| 8 | 5 or 7 | ≤ 2/8 | 0.0021 |
| 10 | 7 | ≤ 4/10 | 0.0018 |

The worst case is taken over the true success probability, with the same
probability in both arms. Across K = 7 tasks the family-wise false-block rate
is at most about 0.007, well under the nominal 0.05, because the discrete
exact test is conservative.

**The honest consequence: at 5 trials, gate 2 catches collapse and nothing
less.** 5/5 → 1/5 does not fire. Catching partial severe drops costs more
trials per task, and that is a budget decision, not a statistics trick.

## 3. Verdict semantics

In order:

1. **INCOMPARABLE**: fingerprint mismatch, checked before any run (unchanged).
2. **REGRESSION**: gate 1 fired, or gate 2 fired on any task. The report names
   the gate and, for gate 2, the task, its counts and p. Gate 2's evidence is
   specific to the task: it stands even if gate 1 is below minimum evidence,
   provided the task that fired had no invalid runs.
3. **INSUFFICIENT_EVIDENCE**: gate 1 is below minimum evidence or stopped on
   invalid runs, and gate 2 did not fire.
4. **PASS**, listing any gate 2 WARNINGs and any not-monitored tasks.

## 4. Exploratory check against Stage A/B (not validation)

| | gate 1 | gate 2 eligible (K) | gate 2 | warnings | not monitored | v1 verdict | v0 verdict |
|---|---|---|---|---|---|---|---|
| Stage A | PASS (−0.04, `ci_high` 0.00) | astropy, django, matplotlib, flask (4) | none fires | none | seaborn (3/5) | **PASS** | PASS |
| Stage B | PASS (−0.40, `ci_high` −0.08) | same 4, α/K = 0.0125 | **django 5/5 → 0/5, p = 0.004** | matplotlib 5/5 → 3/5 (drop 0.4, p = 0.22) | seaborn (3/5 → 0/5) | **REGRESSION** | PASS |

Read this as "the rule does what it was designed to do on the data it was
designed from", and nothing stronger.

Two things this check exposes and v1 accepts:
- seaborn went from 3/5 to 0/5 and is not monitored, because a task the
  baseline does not solve reliably cannot be the subject of a "stopped
  working" claim.
- matplotlib's 5/5 → 3/5 is reported, but it does not block.

## 5. The smallest confirmatory study

**Tasks.** All seven SWE-bench Verified instances whose images are already
local and were not used in CI v0. The selection is mechanical (the full
remaining set), and every one is from a different repository than the CI v0
tasks:
- `psf__requests-1142`
- `pydata__xarray-2905`
- `pylint-dev__pylint-4551`
- `pytest-dev__pytest-10051`
- `scikit-learn__scikit-learn-10297`
- `sphinx-doc__sphinx-10323`
- `sympy__sympy-11618`

`pytest-10051` appeared in earlier pilot experiments, but never in CI rule
development.

**Protocol.** The agent, model and contract are those of CI v0. v1 is frozen
in code, with tests, **before** step 1.

1. **Baseline**: `step_limit` 250, 7 × 5 = 35 runs.
2. **Declare the predictions from the baseline alone**, dated and committed
   before any candidate run:
   - K and the eligible set;
   - for each degraded arm and each task, *collapse predicted* when all five
     baseline runs used more steps than the arm's limit, *unaffected
     predicted* when all five used at most 0.75 × the limit, and *no
     prediction* otherwise.
3. **Candidate arms**, each 35 runs against the same baseline:
   - **null**: unchanged. Tests specificity.
   - **severe**: `step_limit` 40. Tests gate 2 on fresh tasks. If step 2
     predicts collapse on no eligible task, this arm is declared uninformative
     in advance and **not run**.
   - **broad**: `step_limit` 15. Tests gate 1. It is expected to truncate
     nearly every task; Stage A's minimum was 23 steps.

**Size and cost.** 140 runs at most. Estimated from CI v0 per-run costs:
- baseline and null: 70 × $0.26 ≈ $18;
- severe: 35 × ~$0.14 ≈ $5;
- broad: 35 × ~$0.05 ≈ $2.

That is about **$25**, with a proposed external stop at $40. The wall clock is
about 6–8 hours, run under the same `.runs/`, `caffeinate` and pre-flight
discipline as CI v0.

**Known limit.** Both degradations belong to one family, the step budget. A
pass would validate the rule against budget-induced failure on fresh tasks,
not against regressions in general. A second family, such as a tool or prompt
degradation, is the next study, not this one.

## 6. Proposed v1 decision contract

```yaml
contract_version: surface-2
features:
  task_success:
    role: outcome
    evaluator: swebench_resolved
    gates:
      broad:                       # unchanged from surface-1
        effect: risk_difference
        independent_unit: scenario
        regression_direction: decrease
        practical_threshold: 0.10
        uncertainty: paired_bootstrap   # over tasks, 95%, seed 0, 2000
        minimum_evidence: {scenarios: 5, trials_per_condition: 3}
        invalid_policy: stop
      severe:
        effect: per_task_drop
        independent_unit: trial_within_scenario
        eligibility: {baseline_success_min: 0.8}
        practical_threshold: 0.5
        test: fisher_exact_one_sided
        alpha: 0.05
        multiplicity: bonferroni_over_eligible
        minimum_evidence: {trials_per_condition: 5}
        invalid_policy: exclude_task
        warn_threshold: 0.4
aggregation: any                   # REGRESSION if either gate fires
```

## 7. Falsification criterion

v1 is **falsified** if any of the following happens in the confirmatory study:

- **F1** The null arm returns REGRESSION from either gate.
- **F2** The broad arm (`step_limit` 15) does not return REGRESSION.
- **F3** The severe arm is run, the eligible tasks predicted to collapse are
  observed at 0/5, and gate 2 does not fire on them.
- **F4** Gate 2 fires on a task predicted unaffected in any arm.

v1 is **confirmed for budget-induced regressions** if none of F1–F4 occurs and
every arm that was run produced its predicted verdict. Anything else, such as
predictions left open or an arm declared uninformative, is reported as it
happened and does not count as confirmation.

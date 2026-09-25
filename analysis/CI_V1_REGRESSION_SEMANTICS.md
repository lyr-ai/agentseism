# Stage C — Regression semantics design

2026-09-25, on `product/ci-v0` after `1f17ac1`. Revision 2. Design only: no
code, no runs, and the v0 decision logic is untouched. **v1 is not
implemented.** A statistical specification freeze (§8) comes before any code.

Revision 2 changes the following:
- 8 trials per task instead of 5;
- eligibility for gate 2 raised to ≥ 7/8;
- the estimands and independence assumptions are stated explicitly (§3);
- exact decision boundaries for every K from 1 to 7;
- exact run counts and cost for the confirmatory study;
- gate 2 renamed **capability regression**.

**Status of every number drawn from Stage A/B below: exploratory.** The rule
was designed after both results were seen. Its agreement with them is
consistency by construction, not validation. Validation is the confirmatory
study in §6, on tasks the rule has never seen.

## Revision 3 — 2026-09-25: gate 2's K is the declared suite size

One change: the Bonferroni family for gate 2 is **every task in the declared
suite**, fixed before any outcome is seen. It was the eligible tasks.

**Why.** Eligibility is decided on the same baseline the test then uses. A
flaky agent leaves few tasks eligible, α/K relaxes, and the gate loosens
exactly where noise is highest. Revision 2 false-blocked 3.3–3.8% of
unchanged PRs on a flaky agent, where the plain count heuristic
`≥ 7/8 and ≤ 2/8` managed 1.4–2.7%. A decision threshold must not be moved by
the stochastic outcomes it is judging.

**Basis.** Offline simulation only (`analysis/CI_V1_BASELINE_CHALLENGE.md`
§3). No fresh data had been seen, so this is a methodology correction, not
tuning to a result.

**Effect at n = 8:**
- flaky-agent false block falls to 0.4–0.8%;
- per-task power at K = 7 is unchanged (0.87 against a collapse to 0.10);
- at larger K it falls as multiplicity requires (0.75 at K = 10).

**Nothing else changed:**
- gate 1;
- eligibility ≥ 7/8;
- the 0.50 drop threshold;
- the 3/8 warning;
- n = 8;
- the verdict order;
- the prediction rule;
- the cost stop;
- F1–F4.

Implemented as `capability-2`, with `multiplicity: bonferroni_over_suite`.
The eligible-K option was removed rather than kept as a choice.

## Specification freeze — 2026-09-25

Frozen before any confirmatory run. Implemented as `capability-1` in
`src/agentseism/capability.py`, and exercised by `tests/test_capability.py`,
which asserts this document's §4 tables.

- **Gate 1:** unchanged from surface-1.
- **Gate 2, positioned as a catastrophic capability regression gate:**
  - eligibility: baseline ≥ 7/8 (the fraction 0.875);
  - a one-sided Fisher exact test, with Bonferroni over the K tasks of the
    declared suite (revision 3);
  - practical drop ≥ 0.50;
  - **WARNING at a drop of ≥ 3/8**;
  - a task with any invalid run is excluded;
  - the task-specific inference assumptions in §3.2.
- **Also frozen:** the verdict order (§5), the prediction rule and cost stop
  semantics (§7), and F1–F4 (§9).
- **Product claim:** detects near-collapse of a task that reliably worked;
  the smallest firing drop is 0.75 at n = 8, K ≥ 4. It is **not** "any drop of
  50 points or more".

The operating characteristics are in `analysis/CI_V1_OPERATING_CHARACTERISTICS.md`.
**The confirmatory study (§7) has not been run.**

## 1. What v0 taught, in one line each

- **Stage A:** natural variation is not a regression. seaborn went 3/5 → 2/5
  on an unchanged candidate, and a gate must absorb that.
- **Stage B:** one population estimand misses concentrated failure. Task
  success fell 0.92 → 0.52 and django went 5/5 → 0/5, yet the verdict was PASS,
  because a bootstrap over five tasks keeps `ci_high` near zero whenever some
  tasks are untouched.

These are two different risks, so v1 gives each its own endpoint.

## 2. The two gates

| | Gate 1 — broad reliability | Gate 2 — capability regression |
|---|---|---|
| question | Did the PR lower reliability across the suite? | Did something that reliably worked stop working? |
| estimand | see §3.1 | see §3.2 |
| minimum evidence | ≥ 5 tasks, ≥ 3 trials per arm (unchanged) | 8 valid trials per arm on the task |
| eligibility | all tasks | baseline ≥ 7/8. Others are **not monitored** by this gate and are listed in the report |
| practical threshold | 0.10 (unchanged) | observed drop ≥ 0.50 |
| uncertainty | paired bootstrap over tasks, 95%, seed 0, 2000 resamples (unchanged) | one-sided Fisher exact test on the task's 2×2 of successes by arm |
| fires when | `effect ≤ −0.10` **and** `ci_high ≤ −0.10` (unchanged) | drop ≥ 0.50 **and** `p ≤ 0.05 / K` |
| multiplicity | one test | Bonferroni over the K tasks of the declared suite, fixed before any run (revision 3) |
| critical-task declaration | n/a | not in v1 (§2.2) |
| invalid runs | `invalid_policy: stop` (unchanged) | any invalid run on a task makes that task ineligible, and it is reported |
| non-blocking signal | none | eligible task with an observed drop ≥ 0.375 (3/8) that did not fire → WARNING |

### 2.1 Why gate 1 is not changed

`effect ≤ −0.10 and ci_high < 0` would have fired on Stage B (`ci_high` −0.08).
But on Stage A it sits exactly on the edge (`ci_high` = 0.00): an unchanged
candidate would have been one bootstrap draw from a false block. Loosening
gate 1 after seeing B is tuning to B. Gate 1 keeps its v0 meaning: confident
that the suite lost at least 10 points.

### 2.2 Why critical tasks are not declared in v1

Declaring critical tasks means giving them a separate share of α. That is a
second design decision and would need its own validation. v1 treats every
eligible task as equally important.

## 3. Statistical estimands and independence assumptions

The two gates answer different questions, so they infer about different
things from different units. That is not a contradiction.

### 3.1 Gate 1 — broad reliability

- **Estimand:** the average, over the task population, of each task's change
  in success probability: `mean_t (p_cand,t − p_base,t)`.
- **Independent unit:** the **task**. Tasks are treated as a sample from the
  population of tasks the user cares about.
- **Role of repeated runs:** they estimate each task's success rate. They are
  **not** independent evidence about the population: eight runs of one task
  are not eight tasks, which is why the bootstrap resamples tasks, not runs.
- **Assumption:** the tasks are exchangeable draws from that population. The
  claim extends only as far as the suite represents it.

### 3.2 Gate 2 — capability regression

- **Estimand:** for one specific task, conditional on that task and on the
  code version, the change in the agent's success probability:
  `p_base,t − p_cand,t`. No population claim is made.
- **Independent unit:** an **independently started run within that task**.
  For this question the runs are the sample: repeated draws of a stochastic
  agent on a fixed input.
- **Assumption:** within an arm, runs are independent Bernoulli draws with a
  common success probability. Concretely:
  - each run starts from a clean state (a fresh container, `--rm`, and a fresh
    agent process);
  - runs share no memory, history or files;
  - the only intended source of randomness is sampling. No temperature is set,
    so the provider default applies, which for Anthropic is 1.0.
- **Evidence the assumption is not vacuous:** within-task step counts vary
  widely in Stage A (django 44–102, seaborn 98–160). So runs are not
  replicas, and eight runs are not one observation copied eight times, which
  is the failure that would make Fisher badly overconfident.
- **Known threats**, and how the study handles them:
  - **Drift over time.** The arms run hours apart, and a provider-side change
    in that window would move every arm. The **null arm** is run after the
    baseline, the same way the candidate arms are, so drift shows up there as
    a false block (F1).
  - **Shared infrastructure state**, such as the Docker cache or host load.
    This affects duration more than outcome, and outcome effects are guarded
    by `invalid` scoring and the null arm.
  - **Heterogeneity within a run set**, for example after an API outage. This
    is not modelled. It is caught by invalid runs, and it is recorded if seen.

### 3.3 Why different units are consistent

Gate 1 asks about the suite and must not treat runs as independent. Gate 2
asks about one task, where the runs are exactly the independent replicates.
The same run is one measurement of a task mean for gate 1, and one Bernoulli
draw for gate 2. Each gate uses the unit its own question needs.

## 4. Gate 2 at 8 trials — exact properties

One-sided Fisher p-values:

| baseline | candidate 0/8 | 1/8 | 2/8 | 3/8 | 4/8 | 5/8 |
|---|---|---|---|---|---|---|
| 8/8 | 0.0001 | 0.0007 | 0.0035 | 0.0128 | 0.0385 | 0.1000 |
| 7/8 | 0.0007 | 0.0051 | 0.0203 | 0.0594 | 0.1410 | 0.2846 |

Highest candidate count that fires, after both conditions are applied:

| K (suite size) | α/K | from 8/8 | from 7/8 |
|---|---|---|---|
| 1 | 0.0500 | ≤ 4/8 | ≤ 2/8 |
| 2 | 0.0250 | ≤ 3/8 | ≤ 2/8 |
| 3 | 0.0167 | ≤ 3/8 | ≤ 1/8 |
| 4–7 | ≤ 0.0125 | **≤ 2/8** | **≤ 1/8** |

**What that means, stated plainly.** For K ≥ 4, which is the expected case,
the drop ≥ 0.50 condition is not what binds. Exact-test discreteness plus
Bonferroni binds first, and the smallest observed drop that fires is **0.75**
(8/8 → 2/8, or 7/8 → 1/8). The 0.50 threshold matters only when K ≤ 2. The
product claim is therefore "an observed collapse of about 75 points or more
on a task that reliably worked". It is **not** "any drop of 50 points or
more".

Power against true success probabilities, K = 7 (exact):

| true p_base → true p_cand | 0.00 | 0.10 | 0.25 | 0.40 | 0.50 |
|---|---|---|---|---|---|
| 1.00 | 1.00 | 0.96 | **0.68** | 0.32 | 0.15 |
| 0.95 | 0.94 | 0.87 | 0.55 | 0.24 | 0.11 |
| 0.90 | 0.81 | 0.73 | 0.43 | 0.18 | 0.08 |

The gate reliably catches a true collapse to about 10%. A true drop from 100%
to 25% is caught about two times in three.

False blocks, taken as the worst case over the true probability with the same
probability in both arms, and with eligibility applied:
- **per task:** 0.0017 for K ≥ 4, and 0.013 for K = 1;
- **family-wise** at K = 7: at most about 0.012, against a nominal 0.05.

The discrete test is conservative.

## 5. Verdict semantics, and what a developer sees

In order:

1. **INCOMPARABLE**: fingerprint mismatch, checked before any run (unchanged).
2. **REGRESSION**: gate 1 fired, or gate 2 fired on any task. Gate 2's
   evidence is specific to its task: it stands even when gate 1 is below
   minimum evidence, provided the task that fired had no invalid runs.
3. **INSUFFICIENT_EVIDENCE**: gate 1 is below minimum evidence or stopped on
   invalid runs, and gate 2 did not fire.
4. **PASS**, listing gate 2 warnings and any tasks it does not monitor.

The report has one block per gate:

```text
REGRESSION

Broad reliability: PASS
  92% -> 88%, broad regression not established

Capability regression: FAIL
  django__django-10097   baseline 8/8 -> candidate 2/8   p=0.0035 (limit 0.0071)
Not monitored (baseline below 7/8): mwaskom__seaborn-3069
```

## 6. Exploratory check against Stage A/B (not validation)

Stage A and B ran 5 trials per arm, so the 8-trial rule cannot be applied to
them directly. The revision-1 check used the equivalent 5-trial settings
(eligibility ≥ 4/5, α/K), and is kept only as a record of the design's
motivation:

| | gate 1 | gate 2 (5-trial version) | v1 verdict | v0 verdict |
|---|---|---|---|---|
| Stage A | PASS (−0.04, `ci_high` 0.00) | none fires. seaborn not monitored | PASS | PASS |
| Stage B | PASS (−0.40, `ci_high` −0.08) | **django 5/5 → 0/5, p = 0.004**. matplotlib 5/5 → 3/5 a warning. seaborn not monitored | **REGRESSION** | PASS |

## 7. The confirmatory study

**Tasks.** All seven SWE-bench Verified instances whose images are already
local and were not used in CI v0. The selection is mechanical (the full
remaining set), and every one comes from a different repository than the
CI v0 tasks:
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
in code, with tests, before step 1.

1. **Baseline:** `step_limit` 250, 7 × 8 = 56 runs.
2. **Declare from the baseline alone**, dated and committed before any
   candidate run:
   - the eligible set (K is the suite size, 7, already fixed by revision 3);
   - a projected cost check (step 5 of *Cost* below);
   - for each degraded arm and each task: *collapse predicted* if all eight
     baseline runs used more steps than the arm's limit; *unaffected
     predicted* if all eight used at most 0.75 × the limit; *no prediction*
     otherwise.
3. **Candidate arms**, each 56 runs against the same baseline:
   - **null:** unchanged. Tests specificity and time drift.
   - **severe:** `step_limit` 40. Tests gate 2. If step 2 predicts collapse on
     no eligible task, this arm is declared uninformative in advance and
     **not run**.
   - **broad:** `step_limit` 15. Tests gate 1.

**Exact run count.** At most **224** runs (4 × 56). It is **168** if the
severe arm is declared uninformative.

**Expected cost**, from measured CI v0 per-run costs:

| arm | runs | basis | expected |
|---|---|---|---|
| baseline | 56 | Stage A mean $0.261/run | $14.6 |
| null | 56 | same | $14.6 |
| severe (40) | 56 | Stage B mean $0.143/run; truncated runs $0.169 on average, $0.231 at most | $8.0 (at most $12.9 if every run truncates at the observed maximum) |
| broad (15) | 56 | ≤ 15/40 of a 40-step run, ≈ $0.063/run. This is linear scaling, and it overestimates because context grows | ≤ $3.5 |
| **total** | **224** | | **≈ $41** |

**Stop.** The study stops at **$60** of accumulated spend, which is about
1.5× the expectation. The fresh tasks' costs are unknown, so there is a
checkpoint too. After the baseline, its measured cost per run is projected
over the remaining arms. If the projection exceeds $60, no candidate arm
starts, and the study is re-planned under a new dated declaration.

**Wall clock.** Roughly 8 h for the baseline and null arms, 2.5 h for the
severe arm and 1.5 h for the broad arm. It may be split across sessions,
because every arm compares against the same frozen baseline.

**Known limit.** Both degradations come from one family, the step budget. A
pass validates v1 against regressions caused by the step budget on fresh
tasks, not against regressions in general. A second family, such as a tool or
prompt degradation, is the next study.

## 8. Proposed v1 decision contract (for the specification freeze)

```yaml
contract_version: surface-2
features:
  task_success:
    role: outcome
    evaluator: swebench_resolved
    gates:
      broad_reliability:            # unchanged from surface-1
        effect: risk_difference
        independent_unit: scenario
        regression_direction: decrease
        practical_threshold: 0.10
        uncertainty: paired_bootstrap   # over tasks, 95%, seed 0, 2000
        minimum_evidence: {scenarios: 5, trials_per_condition: 3}
        invalid_policy: stop
      capability_regression:
        effect: per_task_drop
        independent_unit: run_within_scenario
        assumes: independent_clean_runs   # section 3.2
        eligibility: {baseline_successes_min: 7, of: 8}
        practical_threshold: 0.50
        test: fisher_exact_one_sided
        alpha: 0.05
        multiplicity: bonferroni_over_suite   # revision 3
        minimum_evidence: {trials_per_condition: 8}
        invalid_policy: exclude_task
        warn_threshold: 0.375
aggregation: any
```

Freeze checklist before any code:
- the table above, including the α, eligibility and warning values;
- how K is computed: the declared suite size, fixed before any run
  (revision 3);
- the prediction rule in §7, step 2;
- the $60 stop and the checkpoint;
- the falsification criteria in §9.

## 9. Falsification criterion

v1 is **falsified** if any of the following happens in the confirmatory study:

- **F1** The null arm returns REGRESSION from either gate.
- **F2** The broad arm (`step_limit` 15) does not return REGRESSION.
- **F3** The severe arm is run and gate 2 fires on **none** of the eligible
  tasks predicted to collapse. Separately, if any such task is observed at or
  below its boundary in §4 and gate 2 does not fire, that is an
  implementation fault.
- **F4** Gate 2 fires on a task predicted unaffected, in any arm.

v1 is **confirmed for regressions caused by the step budget** if none of
F1–F4 occurs and every arm that was run produced its predicted verdict.
Anything else, such as predictions left open or an arm declared
uninformative, is reported as it happened and does not count as confirmation.

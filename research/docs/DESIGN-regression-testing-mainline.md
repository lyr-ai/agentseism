# AgentSeism main line — budget-aware stochastic regression testing

**Status:** Direction, decided 2026-09-20. Not a pre-registration. Nothing is
rented on it.

## 1. The reframe

The centre of the work moves from

> agent trajectories are stochastic; we study when a run is still recoverable

to

> **after an agent change, can existing CI decide at reasonable cost whether it
> actually got worse?**

Nothing is discarded. C2-H, Gate 9, the budget state machine and the
environment fingerprint all survive; they now serve a question a reader reaches
without first understanding fork roots, recoverability horizons or
serving-stack numerics.

**The claim, as it stands:**

> AgentSeism uses paired, budget-aware repeated evaluation to distinguish
> outcome regressions, inconclusive evidence, and incomparable execution
> environments after agent changes.

## 2. Mutations are the instrument, not a feature list

The six changes below are **controlled mutations / regression scenarios**. They
are how the method is measured, not things the product does. Writing them as
features would turn a method paper into a brochure.

Each is an ordinary change an agent engineer makes, and each has an expected
system output — which is what makes the evidence state machine *evaluable*
rather than merely *designed*:

| Scenario | System should output |
|---|---|
| A clear capability drop | `regression` |
| A small effect with thin evidence | `insufficient evidence` |
| A behaviour-preserving refactor | `pass / neutral` |
| A change that alters trajectories but not outcomes | outcome `pass` — **no false alarm** |
| A serving-stack change | `incomparable` |
| Budget exhausted before a decision | `budget-censored` |

Candidate mutations: max-step limit, tool timeout, error-recovery policy,
context pruning, retry policy, prompt scaffold edit, model revision, serving
configuration.

**Admissibility rule, to be pre-registered with the suite.** Every mutation
must be an *engineering change to the agent*, and the measured quantity a
*regression decision across revisions*. A mutation that reduces to "add noise
to a tool and watch success fall" is covered by existing robustness
benchmarking and collapses the framing; see the AgentNoiseBench comparison in
`docs/RELATED-WORK-MATRIX.md` §3.

## 3. Baselines it must beat

This is what makes it a method paper rather than an observation. The comparison
set is what engineers actually do:

1. a single run per side;
2. a fixed 5 runs per side;
3. mean final success rate only;
4. trajectory similarity;
5. AgentSeism's adaptive paired testing.

Metrics: detection rate, false-alarm rate on benign change, calls and dollars
to a decision, and **decision coverage** — how often any method reaches a
defensible verdict at all.

## 4. Why this survives a mediocre result

If adaptive allocation saves little, the failure is legible: variance too high,
task set too small, effect too weak, stopping rule too conservative, or the
mutation-to-outcome link unstable. Each points somewhere. Heterogeneous
recoverability across horizons does not.

## 5. Paper structure

1. **Problem** — a single agent CI result is not evidence.
2. **Method** — paired trials, adaptive stopping, evidence states, environment
   comparability.
3. **Mutation suite** — realistic changes and their expected effects.
4. **Evaluation** — detection, false alarms, compute and cost,
   insufficient-evidence behaviour.
5. **Diagnostic case study** — C2-H.
6. **Limitations** — one coding agent, synthetic mutations, no production
   deployment.

**C2-H is demoted to a secondary study.** If its result is strong it becomes
the diagnostic section; if it is weak or heterogeneous it goes to discussion or
appendix, stating plainly where trajectory diagnosis stops being useful. It no
longer carries the paper.

**Gate 9 becomes a motivating comparability case study.** Its `0/23` supports
*"when the execution environment changes, the system must not attribute the
difference to the agent"*. It does **not** support "all hardware changes cause
this", and must not be written that way.

## 6. Novelty is unverified, and stays unclaimed

Mutation testing is not new, and "we injected bugs into software" is not a
contribution. The possible contribution is the **combination**: stochastic
agent behaviour, paired outcome comparison, adaptive budget allocation,
explicit `incomparable` and `budget-censored` states, an outcome gate with
trajectory diagnosis, and mutation-based evaluation aimed at agent CI.

**No priority claim is made until a related-work search covers agent
evaluation, flaky-test literature, mutation testing and LLM-agent regression
CI.** That search is a prerequisite for the introduction, not a formality.

**Preliminary pass done, 2026-09-20 — see `docs/RELATED-WORK-MATRIX.md`.** It
does not kill the direction, but it narrows it: "agent testing" is not
claimable territory, and the paper question must be the specific one, *how
should CI decide whether a change has regressed a stochastic tool-using agent
under a limited evaluation budget?* The systematic four-bucket matrix is the
gate on starting the mutation suite.

## 7. What this costs, and what it means for renting

From the real donor wall times (median 475 s, mean 1050 s) at $3.29/h with
0.6 h setup, using a shared baseline arm:

| design | runs | mean | worst |
|---|---:|---:|---:|
| 6 mutations × 3 tasks × 3 trials | 63 | $29 | $62 |
| 6 × 5 × 3 | 105 | $48 | $103 |
| 6 × 5 × 5 | 175 | **$78** | **$170** |
| 8 × 5 × 5 | 225 | $100 | $218 |
| *C2-H, for comparison* | 91 | $41 | $89 |

Two consequences, and the second changes the next decision.

**Fixed-trial designs are the baseline the paper competes against**, so their
cost is a result, not an obstacle: "5 fixed trials per side costs $78 and a
worst case of $170" is precisely the number adaptive allocation must beat.

**The main line and C2-H do not both fit in one $100 budget.** At a credible
size the mutation suite alone is $78 mean, and C2-H is $41 mean. Renting now
for C2-H would spend most of a budget on what is now the *secondary* study,
before the primary one has a design.

## 8. Recommendation

**Do not rent for C2-H yet.** The C2-H apparatus is finished, audited and
`CONDITIONAL GO`; it keeps. What it no longer has is first claim on the budget.

Next, at zero compute cost:

1. the related-work search of §6, which decides whether the framing survives;
2. a mutation-suite design with its own pre-registration — expected effects
   fixed before running, or the suite proves nothing;
3. its cost model and adaptive-allocation rule, since the saving is the result;
4. **then** decide which experiment the first $100 buys.

The apparatus built for C2-H — budget state machine, evidence states, session
fingerprint, atomic artifacts, fail-closed resume — is what the main line needs
too. It was not built for the wrong experiment; it was built for the wrong
*ordering*.

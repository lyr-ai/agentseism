# Contribution matrix — what is left to claim

**Date:** 2026-09-20. Systematic pass, gathered in review.
**"Not found" means not found in this pass** over papers, public code and
mainstream eval products — not that nobody has done it.

> Every part has been built by someone. What was not found is a system that
> connects **feature contract → outcome-grounded regression → comparability
> gate → conditional trace RCA** with these decision semantics.

The direction survives. The contribution statement has to be exact: we did not
invent agent regression testing, feature scorecards, mutations or RCA.

---

## 1. Where AgentAssay reaches

Overlapping with us: baseline/candidate regression, repeated stochastic trials,
PASS/FAIL/INCONCLUSIVE, user-defined evaluators, prompt/tool/model/context
mutations, task success and cost and latency and trace features, SPRT with
confidence intervals and multiple-testing correction, a CI/CD gate, behavioural
fingerprinting, trace reuse.

Its fingerprint already covers tool-usage distribution, trace length, branch
and nesting depth, output tokens and complexity, action distribution, error and
recovery, latency and cost.

**So standard features, the scorecard and controlled perturbations are not, on
their own, a contribution.**

### Gap A — change is not separated from harm

AgentAssay calls it a behavioural regression when the pass rate holds and the
tool chain or another fingerprint feature moves. In its experiments the pass
rate stays at 100%, outcome tests are recorded at power 0, and the fingerprint
reaches about 0.86 by detecting token, step-structure and behavioural change.
The injected-regression experiments are not finished.

What that establishes is that **the fingerprint is sensitive to change.** It
does not establish that the detected change is harmful and should block a
release. That distance is where *gate on outcomes, diagnose with trajectories*
lives.

### Gap B — no `INCOMPARABLE`

It treats a model swap as a mutation and provider or model drift as a threat to
i.i.d., mitigated by shortening the window. There is no serving-stack
fingerprint, no compatibility check, no comparison-validity gate. Its decision
is deploy / block / manual — nowhere to say *these two batches should not be
compared*.

Gate 9 sits exactly in that gap: model, revision, vLLM and CUDA nominally
aligned, the hardware execution path changed, and every structured action
differed. That difference cannot be attributed to an agent revision.

## 2. What general eval products already cover

LangSmith, Braintrust, Phoenix, MLflow, Weave, DeepEval, Mastra, Inspect AI and
others provide datasets and test cases, custom scorers, side-by-side
baseline/candidate comparison, output and cost and latency metrics, trace and
span observability, CI evaluation, and navigation from a failure to its trace.

**Feature contract + scorecard + PR comparison is a mature product category and
is not a research contribution.**

What they give is building blocks. A user can implement an outcome-first policy
by hand; what is missing is a stated and validated method for deciding **when a
trace shift is a regression, when it is only diagnosis, and when the experiment
is not comparable at all.** That policy layer is the productisable part.

## 3. RCA is crowded, and getting more so

**SkillAdaptor** finds the first actionable fault step in a failed trajectory,
attributes it to a skill, and repairs it with an acceptance check — close to
"locate the first actionable stage after a confirmed failure", but in service
of automatic skill modification, and starting from an already-failed trajectory.

**OpenRCA 2.0** builds step-wise causal-propagation ground truth from known
fault injection, and argues that naming the root service is not enough: the
path from cause to symptom must be verified.

So "use traces for RCA" is not new, and "find the first anomalous node" cannot
be claimed lightly. If we do RCA it must be explicitly about a **regression
delta**:

> Which trace-stage change explains the **outcome difference between two
> otherwise comparable agent revisions**?

not

> Why did this agent fail?

## 4. The matrix

| Capability | Covered by existing work | Can AgentSeism still claim it |
|---|---:|---|
| Agent repeated evaluation | high | no |
| Statistical CI gate | high | no |
| Feature scorecard | high | no — a product feature |
| Controlled mutations | high | no |
| Adaptive sampling | high | no |
| Trace fingerprint / drift | high | no |
| General agent RCA | medium-high, growing fast | no |
| User-defined feature contract | medium-high | interface only |
| Outcome-first release policy | partly in practice, unvalidated | **researchable** |
| Harmless trace-shift false alarms | none found | **strong candidate** |
| Serving-stack comparability gate | none found for agent regression | **strongest candidate** |
| `INCOMPARABLE` as a first-class verdict | none found | **strong candidate** |
| Regression-conditioned differential RCA | adjacent, combination not seen | second-strongest |

---

## 5. The problem this creates for the next experiment

The three strongest candidates are comparability, `INCOMPARABLE`, and
harmless-shift false alarms. **Our evidence is thinnest exactly where the claim
is strongest.**

| Candidate | Evidence we hold | n |
|---|---|---|
| Serving-stack comparability gate | Gate 9 | **one stack pair, one task** |
| `INCOMPARABLE` verdict | the same Gate 9 | the same one |
| Harmless trace-shift false alarms | `h2_phase_a1` | six pairs, one task |

An earlier note said the harmless-shift counterexample was the weaker of the
two and should be strengthened first. On claim value that was the wrong
ordering: **comparability is the strongest candidate and rests on `n = 1`.**

And it is the more expensive to strengthen. A second harmless-shift task needs
one machine. A second comparability point needs **two different serving
stacks** — a second GPU type, or a deliberate driver or runtime change — which
is a different and larger purchase than the $8–16 slice, and larger than the
$20–30 pilot.

That tension should be settled before the pilot is designed, not after: the
pilot's shape depends on whether it is meant to strengthen the strongest claim
or the cheapest one. **It is not yet decided, and this document does not decide
it.**

## 6. The narrowed paper

The product may stay a full framework. **The paper may not be written as one.**

> ~~A feature-driven testing framework for stochastic agents.~~

That is absorbed on contact by AgentAssay and by the eval platforms. The
centre is not the features; it is the **classification of changes**:

> **Not Every Behavioral Change Is a Regression: Outcome Grounding and
> Comparability for Stochastic Agent CI**

| Observation | Correct verdict |
|---|---|
| outcome drops significantly, environments comparable | `REGRESSION` |
| trace changes significantly, outcome holds | `DIAGNOSTIC_CHANGE` / `PASS_WITH_CHANGE` |
| serving fingerprint incompatible | `INCOMPARABLE` |
| not enough data | `INSUFFICIENT_EVIDENCE` |

Everything else becomes apparatus, and says so: features measure change,
mutations produce known engineering changes, the user contract defines what
matters, RCA explains a confirmed regression. **None of them is the
contribution.**

The boundary to hold:

> AgentSeism is not a more complete AgentAssay. It addresses what existing
> regression frameworks do not answer *before* running a statistical test:
> **is this comparison valid, and is the detected behavioural change worth
> blocking a release for?**

## 7. What that framing demands of the experiment

If the four-way classification is the contribution, **the experiment has to
produce all four verdicts.** Two already exist in frozen data; two do not.

| Verdict | Evidence | Status |
|---|---|---|
| `DIAGNOSTIC_CHANGE` | `h2_phase_a1`, 6/6 pairs all resolved | **held** |
| `INCOMPARABLE` | Gate 9, 0/23 agent held fixed | **held** |
| `REGRESSION` | — | **needed** — a real one, from a registered mutation |
| `INSUFFICIENT_EVIDENCE` | — | **needed**, and it must be *earned* |

The last row is the one most easily faked. `INSUFFICIENT_EVIDENCE` is only
meaningful if it arises from a real effect too small to resolve at the trial
count — not from running two trials and declaring uncertainty. It has to be
distinguishable from `PASS`, which is the open item already recorded in
`FEATURE_TAXONOMY_AND_HYPOTHESES.md` §6, and it is now load-bearing rather than
housekeeping.

So the minimum experiment is not "one regression". It is **a mutation strong
enough to produce `REGRESSION` and one weak enough to produce
`INSUFFICIENT_EVIDENCE` at the registered trial count** — which means the
effect thresholds and trial allocation of Phase 3 have to be chosen so that
both outcomes are reachable. A design in which every mutation either clearly
regresses or clearly passes cannot demonstrate the classification it proposes.

## 8. The two experiments, and their cost asymmetry

The review names the two that matter, and they are the two strongest
candidates in §4:

1. **Harmless-shift** — a trace/fingerprint detector alarms on
   outcome-equivalent trajectories; an outcome-grounded policy does not block.
2. **Comparability** — a serving-stack change produces a large trajectory
   shift, so without a compatibility gate it is misattributed to the agent.

If both hold, the paper has its own question. If only the scorecard, mutations
and RCA can be shown, it is a product and not a distinct method paper.

**They do not cost the same** (§5). Harmless-shift needs one machine and a
second task. Comparability needs **two serving stacks** — a second GPU type, or
a deliberate driver or runtime change — which is a larger purchase than the
$8–16 slice or the $20–30 pilot.

Unresolved, and to be settled before the pilot is designed: whether the first
money strengthens the strongest claim (comparability, `n = 1`) or the cheapest
one (harmless-shift, `n = 6` pairs on one task).

## 9. Still open

- Which of §8's two the pilot strengthens.
- How `REGRESSION` and `INSUFFICIENT_EVIDENCE` are both made reachable (§7).
- The contract schema, still the next zero-cost step.

# AgentSeism — Writing & Product-Thinking TODO

**Status:** Working backlog  
**Purpose:** Use writing to sharpen the product, preserve lessons, and eventually communicate AgentSeism publicly.

This is not a content-marketing calendar.

The primary purpose of each piece is to force a clear answer to one product or methodological question.

For every article, answer before drafting:

```text
Question:
What do I currently believe?
What evidence do we have?
What would change my mind?
What does this imply for AgentSeism?
```

Do not turn hypotheses into established claims.

Where evidence is incomplete, leave the article as notes or a draft until the relevant experiment finishes.

---

# Priority 1 — Understand the product problem

## [ ] Why Agent CI Can't Be Treated Like Deterministic Tests

**Question**

What fundamentally changes when the system under test is stochastic?

**Current belief**

Traditional software CI assumes that the same code and input should produce a sufficiently deterministic result.

Agents produce distributions of outcomes.

A single observed PASS or FAIL therefore does not necessarily establish whether a code change improved or degraded the system.

**Evidence available**

- CI v0 Stage A.
- Identical baseline/candidate configuration produced different observed outcomes.
- Baseline success 0.92 vs unchanged candidate 0.88.
- AgentSeism correctly did not interpret the observed difference as an established regression.

**Product question**

Why does AgentSeism need to exist instead of simply adding agent evals to GitHub Actions?

**Write after**

Stage C null arm is complete.

---

## [ ] The Difference Between Regression and Noise in AI Agents

**Question**

When an agent's score decreases, when should a developer believe the PR caused the decrease?

**Current belief**

Observed change and established regression are different concepts.

A useful CI system must reason about:

- stochastic variation;
- practical effect size;
- uncertainty;
- evidence sufficiency.

**Evidence available**

Stage A:

```text
baseline  0.92
candidate 0.88
effect   -0.04
95% CI   [-0.12, 0.00]
verdict   PASS
```

**Product question**

What evidence should be required before AgentSeism blocks a merge?

---

# Priority 2 — Learn from the first method failure

## [ ] Our Agent Got 40% Worse — and Our CI Still Passed It

**Question**

How can a statistically implemented regression test produce a decision that is obviously wrong for the product?

**Current belief**

The statistics can be correct while the estimand is wrong.

**Evidence**

CI v0 Stage B:

```text
baseline  0.92
degraded  0.52
effect   -0.40
95% CI   [-0.72, -0.08]
verdict   PASS
```

The degradation was concentrated:

- some tasks were unaffected;
- one partially degraded;
- two collapsed.

The frozen population-level rule required the upper confidence bound to be at or below -0.10 and therefore did not fire.

**Key lesson**

Do not respond to a surprising result by immediately changing the threshold.

First ask whether the decision rule is estimating the product risk users actually care about.

**Product implication**

This failure motivated the separation between:

- broad population regression;
- catastrophic capability regression.

**Potential opening**

> The statistics weren't wrong. We were asking the wrong question.

---

## [ ] What Should "Regression" Mean for an AI Agent?

**Question**

What kinds of deterioration should block an agent PR?

**Current belief**

At least two distinct risks exist.

### Broad regression

Reliability decreases across the task population.

### Capability regression

A previously reliable capability approaches collapse.

These are different estimands and should not be forced into one statistic.

**Evidence**

Stage B exposed the distinction.

Stage C is the fresh confirmation of the dual-gate design.

**Product question**

Should AgentSeism ultimately expose different regression classes rather than one generic FAIL?

**Write after**

Stage C completes.

---

# Priority 3 — Explain the statistical foundation

## [ ] Why Running Your Agent More Times Is Not Enough

**Question**

Why isn't repeated evaluation alone sufficient?

**Current belief**

Repeated measurements do not automatically increase the number of independent experimental units.

For a population-level regression:

```text
task = experimental unit
runs = repeated measurements within task
```

Therefore:

```text
7 tasks × 8 runs
```

does not mean:

```text
n = 56 independent tasks
```

**Evidence**

Gate 1 design and Stage B sensitivity boundary.

**Product implication**

AgentSeism must understand the structure of the evidence, not merely count executions.

---

## [ ] The Hidden Multiple-Testing Problem in Agent Eval Suites

**Question**

What happens when a CI system independently monitors dozens or hundreds of agent capabilities?

**Current belief**

Naive per-task thresholds accumulate false-block probability as the suite grows.

Multiplicity control becomes a product requirement, not merely a statistical detail.

**Evidence**

Simple-rule challenge:

R3 false-block risk increases substantially as K grows.

The suite-K capability gate remains controlled.

**Important lesson**

The first Gate 2 design used only eligible tasks in K.

That caused the threshold to become more permissive when the agent was flaky.

The correction was:

> multiplicity is based on the predeclared suite, not the observed eligible subset.

**Product question**

How should AgentSeism scale from 7 capabilities to 50, 100, or 500?

---

## [ ] How Much Evidence Should It Take to Block an AI Agent PR?

**Question**

What balance should CI choose between false blocks and missed regressions?

**Current belief**

AgentSeism v1 deliberately favors high specificity.

A CI system that frequently blocks healthy PRs will eventually be ignored.

But excessive conservatism can miss moderate regressions.

**Evidence**

Operating-characteristics study:

- naive rules are more sensitive;
- they also false-block more frequently;
- v1 is conservative;
- moderate regressions remain difficult.

**Product question**

What operating point will real developers tolerate?

**Do not finalize until**

External-user evidence exists.

---

## [ ] Why We Let CI Say "I Don't Know"

**Question**

Should CI always return PASS or FAIL?

**Current belief**

No.

For stochastic systems:

```text
INSUFFICIENT_EVIDENCE
```

is a legitimate decision state.

It is different from:

```text
PASS
```

and:

```text
REGRESSION
```

**Evidence**

The contract and early end-to-end runs already exercise this state.

**Future question**

Can sequential sampling turn `INSUFFICIENT_EVIDENCE` into an actionable workflow:

```text
not enough evidence
        ↓
buy another sample
        ↓
update evidence
        ↓
stop when decision is defensible
```

---

# Priority 4 — Explain the larger methodology

## [ ] Treat Every Agent PR as an Experiment

**Question**

What is the simplest conceptual model for AgentSeism?

**Working thesis**

> Treat an agent PR as an experiment, not a deterministic test.

Map:

```text
main branch       → control
PR                → treatment
task              → experimental unit
agent runs        → repeated measurements
task success      → endpoint
candidate effect  → treatment effect
practical cutoff  → meaningful-effect threshold
uncertainty       → evidence strength
merge decision    → experiment-driven action
```

**Topics**

- control/treatment;
- estimand;
- experimental unit;
- practical significance;
- uncertainty;
- multiplicity;
- stopping rules;
- protocol deviations.

**Important caveat**

Agent CI is not a clinical trial.

Borrow experimental-design principles without pretending the domains are identical.

**Write after**

Stage C fresh confirmation.

---

## [ ] From Clinical Trials to Agent CI: What Transfers and What Doesn't

**Question**

Which ideas from biostatistics transfer naturally to stochastic software systems?

**Transfers**

- estimands;
- experimental units;
- repeated measurements;
- negative/positive controls;
- practical significance;
- uncertainty;
- multiplicity;
- power;
- pre-specification;
- protocol deviations;
- sequential evidence.

**Does not transfer directly**

- regulatory requirements;
- patient-level causal interpretation;
- clinical population assumptions;
- long trial timelines;
- identical loss functions.

**Product-thinking goal**

Clarify which statistical discipline helps agent CI and where software engineering requires a different approach.

---

## [ ] How Biostatistics Changed the Way I Build AI Systems

**Question**

What does my previous training contribute to AI engineering?

**Working thesis**

The important contribution is not knowing a particular statistical test.

It is asking:

```text
What exactly are we estimating?
What is the independent unit?
What effect actually matters?
What evidence is enough?
What would falsify the claim?
When should we stop collecting data?
```

**Purpose**

Personal reflection and technical identity.

Do not turn it into an AgentSeism advertisement.

---

# Priority 5 — Product economics

## [ ] The Real Cost of Reliable Agent Evals

**Question**

How expensive is trustworthy stochastic-agent CI?

**Evidence already available**

Record:

- API cost per agent run;
- baseline cost;
- candidate cost;
- serial wall-clock time;
- effect of prompt caching;
- infrastructure overhead.

**Important distinction**

Validation cost is not necessarily product cost.

Current fixed designs deliberately buy enough evidence to understand the method.

A production CI product should not blindly inherit the same sample size.

**Product question**

What cost per PR will developers actually tolerate?

---

## [ ] Can Agent CI Be Cheap Enough to Run on Every PR?

**Question**

Can rigorous statistical decisions be made within normal CI cost and latency constraints?

**Current status**

Open question.

**Potential mechanisms**

- cached baseline evidence;
- fewer initial runs;
- early stopping;
- selective resampling;
- task selection;
- parallel execution;
- cheaper models;
- self-hosted inference.

**Do not write as a results article until**

Adaptive/sequential evidence exists.

---

## [ ] From Fixed Sampling to Adaptive Agent CI

**Question**

Can AgentSeism spend evaluation budget only where uncertainty matters?

**Working idea**

```text
small initial sample
        ↓
evidence sufficient?
   ↙       ↓       ↘
safe    uncertain   harm
 ↓         ↓         ↓
PASS    sample more REGRESSION
```

Then distinguish:

```text
within-task uncertainty → more repetitions
between-task uncertainty → more tasks
```

**Current status**

Hypothesis only.

Do not claim product value until implemented and validated.

---

# Priority 6 — Building the product

## [ ] Building AgentSeism: The Experiments That Changed the Product

**Question**

How did the product definition evolve through falsification?

**Possible milestones**

- initial research direction;
- product-first decision;
- CI v0;
- synthetic specificity/sensitivity;
- Stage A real negative control;
- Stage B false negative;
- estimand redesign;
- operating-characteristics analysis;
- simple-baseline challenge;
- multiplicity correction;
- fresh Stage C confirmation.

**Writing principle**

Focus on decisions and surprises, not a chronological commit log.

---

## [ ] We Spent Too Much Time on GPU Infrastructure

**Question**

How does technically useful work become product distraction?

**Working lesson**

Infrastructure is justified only by the product uncertainty it unlocks.

**Topics**

- API cost motivated GPU work;
- deployment debugging became its own objective;
- product question remained unanswered;
- later the reason for GPU became clearer: reducing marginal cost of repeated validation.

**General lesson**

> Infrastructure gets a budget proportional to the product question it unlocks.

**Status**

Working lesson. Verify historical details before publishing.

---

# Priority 7 — Benchmarking and external evidence

## [ ] What Should an Agent CI Benchmark Actually Measure?

**Question**

What benchmark would fairly measure stochastic CI decision quality?

**Possible metrics**

- false-block rate;
- missed-regression rate;
- abstention rate;
- cost to decision;
- time to decision;
- performance by regression family.

**Possible regression families**

- unchanged/null;
- harmless change;
- execution-budget regression;
- prompt regression;
- tool/config regression;
- model regression;
- retrieval/memory regression.

**Important warning**

Do not design the benchmark around failure modes AgentSeism already handles well.

Benchmark taxonomy should wait for:

- multiple degradation families;
- fresh validation;
- preferably external-user evidence.

---

## [ ] Why More Agent Benchmarks Aren't Necessarily Better

**Question**

Is benchmark size the right measure of evaluation quality?

**Working thesis**

For a CI decision system, the relevant question is not how many benchmark tasks exist.

It is whether the evidence supports the correct engineering decision at acceptable cost.

**Potential contrast**

```text
agent benchmark:
How capable is the agent?

AgentSeism benchmark:
How reliably can the CI system determine whether a change made the agent worse?
```

---

# Priority 8 — General development methodology

## [ ] Falsification-First Development for AI Products

**Source**

`docs/EXPERIMENTAL_PRODUCT_DEVELOPMENT.md`

**Question**

How can a small team avoid spending weeks building the wrong AI system?

**Core loop**

```text
Problem
  ↓
Product Claim
  ↓
Cheapest Falsification
  ↓
Freeze
  ↓
Run
  ↓
Learn
  ↓
GO / REVISE / PIVOT / STOP
```

**AgentSeism examples**

Use real project lessons, but make the article useful outside AgentSeism.

**Write late**

The methodology is still developing.

---

# Writing order

Do not write all articles at once.

Recommended sequence after Stage C:

```text
1. Our Agent Got 40% Worse — and Our CI Still Passed It
2. Why Agent CI Can't Be Treated Like Deterministic Tests
3. What Should "Regression" Mean for an AI Agent?
4. Treat Every Agent PR as an Experiment
5. Why Running Your Agent More Times Is Not Enough
6. The Hidden Multiple-Testing Problem in Agent Eval Suites
7. Why We Let CI Say "I Don't Know"
8. How Much Evidence Should It Take to Block an AI Agent PR?
```

Then choose between:

```text
product economics
methodology
personal/biostatistics
benchmarking
```

based on what the next experiments teach us.

---

# Evidence rule for writing

Before publishing any technical claim, label its evidence internally:

```text
HYPOTHESIS
SYNTHETIC
EXPLORATORY REAL
CONFIRMATORY REAL
EXTERNAL USER
REPEATED EXTERNAL
```

Do not silently upgrade evidence.

Examples:

```text
Stage A/B:
real-system development evidence

Stage C:
fresh confirmatory evidence if completed under the frozen protocol

Adaptive sampling:
hypothesis until tested

External usefulness:
not established until someone outside the project uses it
```

---

# Blog entry template

For every new idea, add:

## Title

Working title.

## Question

What question does this article force us to answer?

## Current belief

What do we currently think?

## Evidence

What evidence actually supports that belief?

## Counterargument

What is the strongest reasonable objection?

## What would change my mind?

What future result would cause us to revise the belief?

## Product implication

If the belief is true, what should AgentSeism do differently?

## Status

```text
IDEA
NOTES
READY AFTER <experiment>
DRAFT
PUBLISHED
```

---

# Rule

Writing is part of product development when it forces clearer thinking.

It becomes a distraction when the goal changes from:

> **understand the product**

to:

> **produce content.**

When in doubt, run the experiment first.

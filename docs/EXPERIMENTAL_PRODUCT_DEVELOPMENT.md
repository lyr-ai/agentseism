# Experimental Product Development

**Status:** Working methodology  
**Version:** 0.1  
**Origin:** Lessons from building and validating AgentSeism  
**Purpose:** A reusable development method for future 0→1 AI/ML systems

---

# 1. Why this document exists

AI projects make it unusually easy to spend large amounts of time without reducing the most important uncertainty.

A project can accumulate:

- thousands of lines of code;
- benchmarks;
- infrastructure;
- GPU deployment;
- evaluation pipelines;
- papers;
- dashboards;
- sophisticated statistical analyses;

while the fundamental question remains unanswered:

> **Does this solve a problem that matters, and does the proposed method actually work?**

The goal of this methodology is to reduce that waste.

The central principle is:

> **Do not optimize how quickly we build. Optimize how quickly we learn whether the idea deserves to be built.**

A failed hypothesis discovered in two days is often a better outcome than a polished implementation discovered to be unnecessary after six weeks.

---

# 2. The core loop

Every 0→1 project should move through the following loop:

```text
Problem
   ↓
Product Claim
   ↓
Cheapest Falsification
   ↓
Freeze the Decision Rule
   ↓
Run
   ↓
Observe
   ↓
Interpret
   ↓
GO / REVISE / PIVOT / STOP
   ↓
Fresh Confirmation
   ↓
Productization
```

The important property of this loop is that **implementation follows evidence**.

Do not build the full product and then search for evidence that justifies it.

---

# 3. Step 1 — Define the problem

Before architecture, define the user problem.

Answer:

### User

Who experiences the problem?

### Situation

When does the problem occur?

### Pain

What decision, task, or workflow is currently difficult?

### Current workaround

How does the user solve it today?

### Cost of the problem

Why is the existing solution insufficient?

The problem statement should fit in one sentence:

> **[User] cannot reliably [decision/task] when [condition], because [specific limitation].**

Example:

> Agent developers cannot reliably determine whether a PR introduced a real behavioral regression because repeated executions of the same agent produce different outcomes.

Avoid beginning with a technology:

> “I want to build an agent evaluation framework.”

That describes an implementation, not a problem.

---

# 4. Step 2 — Define a falsifiable product claim

Convert the problem into a claim that can be wrong.

Bad:

> AgentSeism improves agent reliability.

Better:

> AgentSeism distinguishes stochastic variation from consequential PR regressions sufficiently well to support a CI merge decision.

Stronger:

> Under the same evaluation budget, AgentSeism produces fewer incorrect merge decisions than a simple repeated-evaluation baseline.

A useful product claim must specify enough structure that evidence can contradict it.

Ask:

> **What observation would make me stop believing this claim?**

If no possible result would change the team's belief, the claim is not falsifiable.

---

# 5. Step 3 — Define the estimand

Before choosing metrics or statistical tests, define exactly what effect matters.

Ask:

> **What quantity corresponds to the product decision?**

Examples:

- average reliability change across tasks;
- probability that a critical capability regresses;
- latency increase;
- cost increase;
- probability of policy violation;
- user conversion lift.

Different product risks may require different estimands.

Do not force multiple risks into one metric merely because one statistical test is convenient.

### Lesson

A large observed effect that does not trigger the decision rule may indicate:

1. insufficient evidence;
2. an overly conservative rule;
3. or the wrong estimand.

Investigate the estimand before changing thresholds.

---

# 6. Step 4 — Identify the experimental unit

Ask:

> **What is independently sampled?**

Repeated measurements are not automatically independent experimental units.

For example:

```text
7 tasks × 8 stochastic runs
```

does not necessarily mean:

```text
n = 56 independent tasks
```

The correct unit depends on the estimand.

A task-population estimand may use:

> task = independent unit

while a task-specific reliability estimand may use:

> independently initiated executions within that task = sampling units.

Always document:

- experimental unit;
- repeated-measurement structure;
- independence assumptions;
- known threats to independence.

Never allow a larger apparent sample size to create false certainty.

---

# 7. Step 5 — Define practical significance

Do not ask only:

> Is there a difference?

Ask:

> **How large must the difference be before a product decision should change?**

Predeclare a minimum practically meaningful effect.

Examples:

```text
reliability drop ≥ 10 percentage points
cost increase ≥ 25%
latency increase ≥ 20%
capability drop ≥ 50 percentage points
```

Statistical significance without practical significance should not automatically drive a product decision.

Likewise, a practically large observed effect without sufficient evidence should not automatically be presented as established.

---

# 8. Step 6 — Design the cheapest decisive experiment

Before building infrastructure, ask:

> **What is the cheapest experiment that could kill this idea?**

Optimize for information gained, not implementation completeness.

Prefer:

```text
one real user
one real system
one meaningful control
one falsifiable outcome
```

over:

```text
large framework
many integrations
large benchmark
dashboard
cloud deployment
paper
```

The first experiment should answer the highest-value unknown.

Examples:

- Can the method distinguish an unchanged system from a degraded one?
- Does a real user understand the report?
- Does the result change a real decision?
- Does the method outperform a simple baseline?
- Is the cost acceptable?

Do not test five secondary hypotheses while the primary product hypothesis remains unresolved.

---

# 9. Step 7 — Use negative and positive controls

Whenever possible, validate both specificity and sensitivity.

### Negative control

Nothing consequential changes.

Expected behavior:

> the system should not manufacture a signal.

### Positive control

Introduce a predeclared consequential change.

Expected behavior:

> the system should detect the intended effect if its sensitivity is sufficient.

Neither control alone is enough.

A detector that always returns PASS passes the negative control.

A detector that always returns FAIL passes the positive control.

The useful system must distinguish them.

---

# 10. Step 8 — Freeze before observing outcomes

Before the experiment begins, freeze the pieces that could otherwise be tuned to the result:

- task set;
- treatment/intervention;
- baseline;
- endpoint;
- estimand;
- thresholds;
- statistical rule;
- sample size;
- stopping rule;
- cost cap;
- exclusion/invalid-run rules.

Record a commit or manifest.

After outcomes are observed:

> **near misses are results, not invitations to move the threshold.**

If the design needs revision, record the current experiment honestly, create a new dated design, and confirm it on fresh data.

---

# 11. Step 9 — Separate failure from invalid measurement

A product failure and an experiment failure are different.

Examples of product/task failure:

- agent exhausts its valid execution budget;
- agent submits an incorrect result;
- expected capability does not complete.

Examples of invalid measurement:

- Docker failed;
- evaluator crashed;
- artifact is malformed;
- model provider failed;
- environment was incomparable.

Do not convert infrastructure failure into product failure.

Do not convert product failure into `invalid` merely because the evaluator finds it inconvenient to score.

This distinction must be explicit before the experiment.

---

# 12. Step 10 — Treat infrastructure as a means, not a milestone

Infrastructure work is justified only by the product uncertainty it unlocks.

Before starting substantial infrastructure work, ask:

> **If this infrastructure works perfectly, what product question will become answerable?**

If the answer is unclear, stop.

Set a time budget proportional to the uncertainty being removed.

A technically interesting problem is not automatically on the critical path.

### Rule

> **Infrastructure gets a budget proportional to the product question it unlocks.**

Avoid completion instinct:

> “It is almost working, so I should finish it.”

Replace it with:

> “Will finishing it materially change what I know about the product?”

---

# 13. Step 11 — Attack the method with the simplest baseline

Before claiming a sophisticated method adds value, compare it with the simplest credible alternative.

Examples:

- one-shot evaluation;
- repeated average;
- fixed threshold;
- simple per-task heuristic;
- existing open-source framework.

Do not use a deliberately weak baseline.

Ask:

> **If a 10-line heuristic performs just as well, why should the product contain 1,000 lines of statistical machinery?**

Complexity earns its place only by improving a product-relevant operating characteristic:

- fewer false alarms;
- fewer missed failures;
- lower cost;
- faster decisions;
- better scaling;
- better uncertainty handling.

---

# 14. Step 12 — Study operating characteristics before spending heavily

Before large confirmatory runs, characterize the decision rule offline where possible.

Measure:

- false-positive / false-block rate;
- sensitivity / power;
- minimum detectable effect;
- multiplicity behavior;
- effect of sample size;
- effect of number of tasks;
- abstention rate;
- expected cost.

Do not choose sample size merely because:

> “more samples should be safer.”

Look for structural boundaries.

Sometimes one additional observation changes the design qualitatively.

---

# 15. Step 13 — Separate method development from confirmation

Data used to design a method cannot also serve as clean confirmation of that method.

Use development data to:

- discover failure modes;
- revise estimands;
- select rules;
- understand operating characteristics.

Then freeze the revised method.

Confirm it on fresh data.

Label evidence explicitly:

```text
exploratory
development
confirmatory
external
```

Never silently upgrade exploratory evidence into confirmation.

---

# 16. Step 14 — Make the experiment capable of losing

A confirmatory experiment is useful only if failure is allowed.

Before running it, write:

### GO

What result supports continuation?

### REVISE

What result shows the problem is real but the method is inadequate?

### PIVOT

What result suggests a different product definition?

### STOP

What result means further investment is unjustified?

Once the experiment begins, do not rescue the method by changing the rules.

A project that cannot lose an experiment cannot learn from one.

---

# 17. Step 15 — Treat cost and time as product endpoints

For AI systems, inference cost and time-to-decision are not implementation details.

Record:

- number of model calls;
- monetary cost;
- wall-clock time;
- compute requirements;
- human intervention required.

A statistically excellent method that costs $50 and several hours per routine PR may not be a viable CI product.

Ask:

> **What will a user actually tolerate?**

Validation may deliberately use an expensive fixed design.

The final product should not automatically inherit that design.

---

# 18. Step 16 — Optimize information per dollar

Once the method works, optimize:

> **information gained per additional unit of cost.**

Instead of fixed brute-force sampling:

```text
all tasks × N repetitions
```

consider:

```text
small initial sample
        ↓
enough evidence?
  ↙      ↓      ↘
yes   uncertain   harm
 ↓       ↓         ↓
stop   sample     stop
       more
```

Then ask where uncertainty originates.

### Within-task uncertainty

Run that task again.

### Between-task uncertainty

Add or broaden tasks.

### Already decisive

Stop spending.

This leads naturally to sequential and adaptive experimentation.

---

# 19. Step 17 — Keep the user-facing product simpler than the methodology

Users should not need to understand:

- bootstrap;
- Fisher exact tests;
- Bonferroni corrections;
- power calculations;
- sequential boundaries.

The product should expose decisions such as:

```text
PASS
WARNING
REGRESSION
INSUFFICIENT EVIDENCE
INCOMPARABLE
```

and explain the relevant evidence.

Statistical rigor belongs inside the system.

The user should experience:

> **a CI decision they trust.**

---

# 20. Evidence ladder

Use the following hierarchy when deciding how strongly to believe something.

### Level 0 — Intuition

“This seems like a problem.”

### Level 1 — Synthetic evidence

The mechanism works under controlled conditions.

### Level 2 — Real-system observation

The phenomenon appears in a real system.

### Level 3 — Controlled real-system validation

Negative and positive controls behave as expected.

### Level 4 — Fresh confirmation

A frozen method survives new unseen data.

### Level 5 — External user evidence

Someone outside the project uses the system and finds it useful.

### Level 6 — Repeated product evidence

The method works across systems, changes, and users.

Do not speak as if Level 2 evidence were Level 5 evidence.

---

# 21. Decision log format

For every meaningful methodological change, record:

## Context

What were we trying to decide?

## Observation

What actually happened?

## Tempting interpretation

What conclusion would have been easy but premature?

## Decision

What did we change—or deliberately not change?

## General principle

What lesson may transfer to another project?

## Evidence level

`tentative / supported / confirmed`

This preserves why the system evolved, not merely what the final implementation looks like.

---

# 22. Example lessons from AgentSeism

These are working lessons, not universal truths.

### Lesson 1 — Observed change is not established regression

**Observation:** An unchanged candidate moved from 0.92 to 0.88.

**Decision:** Do not block based on raw score decrease.

**Principle:** In stochastic systems, observed differences require an evidence rule.

---

### Lesson 2 — A failed decision can reveal the wrong estimand

**Observation:** A deliberately degraded candidate moved from 0.92 to 0.52, yet the frozen population rule returned PASS.

**Temptation:** Lower the threshold until it fires.

**Decision:** Preserve the result and reconsider what risk the product needs to detect.

**Principle:** When a consequential real effect and the decision rule disagree, inspect the estimand before tuning thresholds.

---

### Lesson 3 — Different risks may require different gates

The first rule measured broad population degradation.

The real system exposed concentrated capability collapse.

**Principle:** Average degradation and catastrophic local failure are different product risks and may require different estimands.

---

### Lesson 4 — Sample size should follow operating characteristics

Increasing repetitions from five to eight was not justified by “more is better.”

Eight was the first design size that allowed one baseline failure while retaining capability eligibility.

**Principle:** Search for structural design boundaries before paying for more samples.

---

### Lesson 5 — Multiplicity rules must not become easier when data becomes noisier

Using only eligible tasks in the multiplicity denominator caused the gate to become more permissive on flaky agents.

**Decision:** Use the predeclared suite size.

**Principle:** Avoid decision rules whose error control becomes weaker because the observed data are noisier.

---

### Lesson 6 — Simple baselines should attack complex methods

A simple per-task rule nearly matched the sophisticated capability gate at small suite sizes.

The statistical gate's clearer advantage appeared as the suite scaled and false-block accumulation became important.

**Principle:** Complexity must demonstrate value against the strongest simple alternative.

---

### Lesson 7 — Infrastructure can consume the project

GPU deployment work consumed substantial time before the product question was sufficiently clear.

**Principle:** Infrastructure should be funded by a specific uncertainty it removes, not by the desire to finish technically interesting work.

---

### Lesson 8 — Cost is part of the hypothesis

Repeated agent execution may produce good statistics and still make a bad CI product.

**Principle:** Evaluate decision quality, false-block risk, cost, and time together.

---

# 23. Reusable new-project template

Every future project should begin with this document before substantial implementation.

## Problem

Who has what problem?

## User

Who experiences it?

## Current workaround

How is it solved today?

## Product claim

What exactly will the product do better?

## Cheapest credible baseline

What simple alternative must we beat?

## Estimand

What effect matters?

## Experimental unit

What is independently sampled?

## Practical threshold

How large must the effect be before we care?

## Cheapest falsification

What is the smallest experiment capable of killing the idea?

## Negative control

What should produce no signal?

## Positive control

What should produce a signal?

## GO

What evidence justifies continuing?

## REVISE

What evidence means the problem exists but the method is inadequate?

## PIVOT

What evidence changes the product definition?

## STOP

What evidence ends the project?

## Initial budget

Maximum dollars:

Maximum engineering time:

Maximum calendar time:

## Evidence level required before productization

What must be true before building substantial infrastructure or UI?

---

# 24. Meta-rule

The most important rule is:

> **Do not confuse progress in implementation with progress in knowledge.**

A week that deletes an incorrect hypothesis may be more productive than a week that adds 5,000 lines of code.

For 0→1 work, the scarce resource is not code.

It is:

> **time spent believing the wrong thing.**

The development process should minimize that time.

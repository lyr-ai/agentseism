# AgentSeism — V0 Design Doc

**Status:** Draft v0.1
**Date:** September 2026
**Scope:** LLM Agents
**Primary goal:** Research prototype
**Secondary goal:** Foundation for an open-source developer tool

## 1. One-line description

> **AgentSeism discovers where small variations are amplified inside LLM-agent executions and identifies the execution weak points most associated with downstream behavioral variation.**

The central question is not:

> Did my agent fail?

Nor:

> Are two outputs different?

It is:

> **Where did behavioral variation emerge inside the execution, how did it propagate, and which execution points matter most to the final outcome?**

---

# 2. Motivation

LLM agents are stochastic systems.

Two executions of the same agent can produce different intermediate decisions and different final outcomes even when given identical or semantically equivalent inputs.

Example:

```text
Same Agent
Same Task

Run 1
Input
  ↓
Evidence A
  ↓
Hypothesis X
  ↓
Tool 1
  ↓
Outcome X


Run 2
Input
  ↓
Evidence B
  ↓
Hypothesis Y
  ↓
Tool 2
  ↓
Outcome Y
```

Existing observability tools can show both traces.

Existing evaluation tools can determine whether `Outcome X` or `Outcome Y` passes an evaluator.

Robustness/metamorphic-testing tools can determine that the outputs changed.

But the engineering question remains:

> **Which internal variation was behaviorally consequential?**

A trace may contain many differences.

Most may not matter.

AgentSeism attempts to identify the small subset of execution differences that explain downstream behavioral variation.

---

# 3. V0 Research Hypothesis

Our initial hypothesis is:

> **Behavioral variation in LLM agents is not uniformly distributed across execution. A small subset of execution points disproportionately introduces or amplifies downstream outcome variation.**

If this hypothesis is false, the project should be reconsidered.

This is therefore the first thing V0 needs to establish.

---

# 4. Scope

V0 targets:

**LLM-based agents with multi-step observable executions.**

Examples include:

* research agents;
* RAG agents;
* diagnostic/RCA agents;
* tool-use agents;
* planning agents.

V0 does **not** target arbitrary stochastic systems.

In particular, V0 makes no claims about robotics or autonomous driving.

The abstractions may eventually generalize, but that is outside the current research scope.

---

# 5. Non-goals

V0 is **not**:

* a general agent evaluation framework;
* a correctness evaluator;
* a failure debugger;
* an observability platform;
* a tracing backend;
* a pytest replacement;
* an agent orchestration framework;
* a dashboard;
* an automatic repair system;
* a memory framework;
* a production SaaS product.

Most importantly:

> **AgentSeism does not determine whether an outcome is good or bad.**

Failure labels and correctness evaluators may be used as optional external signals.

---

# 6. Core Concepts

## 6.1 Task

A task represents one unit of work presented to an agent.

```python
@dataclass
class Task:
    id: str
    input: Any
    metadata: dict = field(default_factory=dict)
```

AgentSeism does not assume the input data type.

---

## 6.2 Run

A `Run` is one execution of an agent on a task.

```python
@dataclass
class Run:
    id: str
    task_id: str

    input: Any
    output: Any
    outcome: Any

    events: list["Event"]

    metadata: dict
```

Multiple runs may exist for the same task:

$$
R_{t,1}, R_{t,2}, ..., R_{t,n}
$$

---

# 7. Execution Trace

AgentSeism does **not** assume every agent execution has a different graph.

A run is represented as an ordered/causally related collection of observable events.

```python
@dataclass
class Event:
    id: str
    run_id: str

    event_type: str

    input: Any
    output: Any

    parent_ids: list[str]

    metadata: dict
```

Examples of `event_type` may include:

```text
model_call
tool_call
retrieval
decision
transform
memory_read
memory_write
```

These are execution primitives, not domain concepts.

An agent may have:

```text
Fixed execution

A → B → C → D
A → B → C → D
A → B → C → D
```

or dynamic execution:

```text
Run 1:
A → B → C → D

Run 2:
A → B → E → F → D
```

AgentSeism must support both eventually.

**V0 should start with relatively alignable traces.**

---

# 8. Outcome

The outcome is the behavior whose variation we care about.

The user provides an optional selector:

```python
def outcome(result):
    return result["answer"]
```

or simply:

```python
def outcome(result):
    return result
```

AgentSeism does not determine whether that outcome is correct.

---

# 9. Outcome Comparator

We need to determine whether two outcomes are behaviorally similar.

Interface:

```python
compare(a, b) -> float
```

where:

```text
1.0 = equivalent
0.0 = maximally different
```

V0 should support:

```text
exact equality
structured comparison
semantic text similarity
custom user comparator
```

Do not build a large evaluator library.

Existing evaluators can be integrated later.

---

# 10. Natural Variation

The first experiment requires **no perturbation at all**.

For the same:

```text
Agent
Task
Configuration
```

run:

$$
N
$$

executions.

Example:

```text
Task T

Run 01 → Outcome A
Run 02 → Outcome A
Run 03 → Outcome B
Run 04 → Outcome A
Run 05 → Outcome C
...
```

Calculate behavioral consistency:

$$
C_t =
\frac{2}{N(N-1)}
\sum_{i<j}
sim(Y_i,Y_j)
$$

and variation:

$$
V_t = 1-C_t
$$

This gives us a population of:

```text
stable tasks
moderately unstable tasks
highly unstable tasks
```

---

# 11. The Central Technical Problem: Run Alignment

Suppose two runs produce:

```text
Run A

E1 → E2 → E3 → E4 → Outcome A


Run B

E1' → E2' → E3' → E4' → Outcome B
```

AgentSeism must determine:

```text
E1 ↔ E1'
E2 ↔ E2'
E3 ↔ E3'
E4 ↔ E4'
```

For fixed workflows, this may be trivial.

For dynamic agents, alignment may use:

* event type;
* execution position;
* parent relationship;
* tool identity;
* instruction similarity;
* input similarity;
* output similarity.

V0 should **not attempt arbitrary graph alignment**.

Start with agents where event correspondence can be established reliably.

## 11.1 V0 alignment strategy: feature projection

Superseded in detail by [`DESIGN-FEATURE-PROJECTION.md`](DESIGN-FEATURE-PROJECTION.md)
(Design Draft v0.2), which replaces stage alignment with feature projection:

> V0 does not align semantic stages directly. It projects each raw execution
> into a set of comparable execution features, then attributes outcome variation
> to those features.

The consequences that matter for the rest of this document:

* raw event occurrence is not a cross-run identity, so attribution ranks
  declared **execution features**, not raw events;
* the raw trace is still recorded in full, for debugging and for the
  intervention work in V1;
* propagation is only scored when the adapter declares feature order; an
  unordered schema is scored `V × A` and says so;
* an observation that *is* the outcome is rejected from attribution by
  construction, and the exclusion is reported.

---

# 12. Event-Level Variation

Once events are aligned:

```text
              Run A              Run B

E1              ≈                  ≈

E2              ≈                  ≈

E3              X                  Y
                   ← divergence

E4              P                  Q

Outcome          A                  B
```

For each aligned event $e$, compute:

$$
D_e(R_i,R_j)
$$

representing local event variation.

An event can vary in:

* output semantics;
* structured content;
* selected tool;
* retrieved information;
* execution path.

V0 does not need a sophisticated taxonomy.

The important measurement is:

> **How different is this execution point across runs?**

---

# 13. Variation Propagation

A large local difference is not necessarily important.

For example:

```text
E2 → huge wording variation
          ↓
E3 → same decision
          ↓
Outcome → same
```

AgentSeism should treat this as low impact.

Compare with:

```text
E2 → small semantic difference
          ↓
E3 → different decision
          ↓
E4 → different path
          ↓
Outcome → different
```

This is potentially a weak point.

Therefore we need to measure:

> **Does variation at event E predict downstream variation?**

---

# 14. Weak Point

V0 defines a behavioral weak point as:

> **An execution point whose variation is strongly associated with downstream outcome variation across repeated executions.**

Initial score:

$$
W(e)
=
LocalVariation(e)
\times
OutcomeAssociation(e)
\times
Propagation(e)
$$

This is intentionally simple.

We should not invent a complicated method before establishing the phenomenon.

---

# 15. V0 Weak-Point Localization

The first localization algorithm should be deliberately simple.

**Terminology rule.** Nothing without an intervention is called attribution in
this project. V0 *localizes*: it produces candidate weak points. Causal
attribution is reserved for the intervention-based work in
[`DESIGN-INTERVENTION.md`](DESIGN-INTERVENTION.md).

For every aligned event:

### Step 1 — Measure local variation

$$
D_e
$$

### Step 2 — Measure downstream persistence

How many downstream aligned events continue to diverge?

### Step 3 — Measure outcome association

Across many runs:

> When this event enters behavioral mode A versus B, how strongly does that predict outcome mode A versus B?

### Step 4 — Rank

Return:

```text
Weak Point Ranking

Event                  Score

E3                     0.81
E7                     0.46
E2                     0.17
E9                     0.03
```

This is **association-based localization**, not causal attribution.

The distinction must be explicit in the paper, and in every user-facing string
the tool prints.

---

# 16. Controlled Perturbation

Only after natural variation is established should AgentSeism introduce controlled perturbations.

Conceptually:

$$
x' = T(x)
$$

Potential early transformations:

```text
paraphrase
context ordering
```

Do not implement a large perturbation catalog.

Controlled perturbations let us ask:

> Where does a known small input variation become amplified inside execution?

Example:

```text
Original input
      │
      ▼
     E1
      │
      ▼
     E2
      │
      ▼
     E3
      │
      ▼
 Outcome A


Semantic-equivalent input
      │
      ▼
     E1' ≈ E1
      │
      ▼
     E2' ≈ E2
      │
      ▼
     E3' ≠ E3      ← amplification
      │
      ▼
 Outcome B
```

This gives AgentSeism a much cleaner experimental setting.

---

# 17. Ground-Truth Localization

This is probably the most important experiment for the eventual paper.

We deliberately inject known variation into one execution point.

Example:

```text
E1
 ↓
E2
 ↓
E3 ← controlled intervention
 ↓
E4
 ↓
Outcome
```

AgentSeism does not receive the intervention label.

Then ask:

> Does the weak-point ranking recover E3?

Metrics:

$$
Attribution@1
$$

$$
Attribution@3
$$

This gives us objective attribution ground truth.

---

# 18. Baselines

At minimum compare against:

### Random

Random execution point.

### First divergence

Return the earliest event that differs.

### Largest local diff

Return the event with maximum:

$$
D_e
$$

### Correlation-only

Rank event variation by correlation with outcome variation.

### LLM debugger

Provide traces to a capable LLM and ask:

> Which execution point most likely explains the outcome difference?

This is an especially important baseline.

If a generic LLM already solves the problem just as well, AgentSeism needs a stronger contribution.

---

# 19. User-Facing Output

Even though V0 is research-first, output should already resemble the eventual product.

```text
AgentSeism
══════════════════════════════════════

Agent: research-agent-v2

Tasks                 100
Executions           1000

Behavioral consistency
                       78%

High-variation tasks
                        21


Top Behavioral Weak Points
──────────────────────────────────────

1. Event group: evidence selection

   Local variation           0.34
   Downstream propagation    0.81
   Outcome association       0.76

   Weak-point score          0.79


2. Event group: retrieval selection

   Local variation           0.27
   Downstream propagation    0.52
   Outcome association       0.48

   Weak-point score          0.44


3. Event group: final generation

   Local variation           0.72
   Downstream propagation    0.04
   Outcome association       0.03

   Weak-point score          0.02

   Low behavioral impact.
```

This demonstrates something important:

> **High variation ≠ high weakness.**

---

# 20. V0 Architecture

Keep it small.

```text
                   Public LLM Agent
                          │
                          ▼
                ┌──────────────────┐
                │ Experiment Runner │
                └────────┬─────────┘
                         │
                    repeated runs
                         │
                         ▼
                ┌──────────────────┐
                │ Trace Collector   │
                └────────┬─────────┘
                         │
                         ▼
                ┌──────────────────┐
                │ Outcome Analyzer  │
                └────────┬─────────┘
                         │
                         ▼
                ┌──────────────────┐
                │ Run Aligner       │
                └────────┬─────────┘
                         │
                         ▼
                ┌──────────────────┐
                │ Variation Engine  │
                └────────┬─────────┘
                         │
                         ▼
                ┌──────────────────┐
                │ Attribution       │
                │ Ranker            │
                └────────┬─────────┘
                         │
                         ▼
                  Weak-Point Report
```

No server.

No database beyond local experiment artifacts.

No UI.

No SaaS.

---

# 21. Repository Structure

I would start with:

```text
agentseism/
│
├── src/agentseism/
│   ├── runner/
│   ├── trace/
│   ├── alignment/
│   ├── variation/
│   ├── attribution/
│   └── metrics/
│
├── agents/
│   └── public agent adapters
│
├── benchmarks/
│
├── experiments/
│   ├── natural_variation/
│   ├── perturbation/
│   ├── attribution/
│   └── mitigation/
│
├── results/
│
├── paper/
│   ├── claims.md
│   ├── experiments.md
│   └── figures/
│
├── DESIGN.md
└── README.md
```

The package lives under `src/` to match the packaging convention used across the
sibling RLRA repositories; the module decomposition is exactly as above.

---

# 22. Research Questions

The paper should initially revolve around four questions.

### RQ1 — Prevalence

> How much execution-level behavioral variation exists across repeated LLM-agent executions?

### RQ2 — Concentration

> Is consequential variation concentrated around a small subset of execution points?

This is probably the **most important hypothesis**.

### RQ3 — Attribution

> Can AgentSeism identify execution weak points that explain downstream behavioral variation?

### RQ4 — Actionability

> Does mitigating highly ranked weak points improve robustness on unseen executions without degrading task quality?

---

# 23. Paper Claims We Want to Earn

Do **not** write these as facts yet.

Treat them as hypotheses requiring evidence.

### Hypothesis A

LLM-agent behavioral variation is substantial even when conventional task quality remains acceptable.

### Hypothesis B

Consequential variation is concentrated rather than uniformly distributed across execution.

### Hypothesis C

Execution-level variation analysis can identify consequential weak points better than simple trace-diff baselines.

### Hypothesis D

Weak-point-guided interventions improve robustness on held-out tasks.

Every major piece of code should support testing one of these hypotheses.

---

# 24. V0 Success Criteria

I would make the go/no-go criteria unusually explicit.

AgentSeism V0 succeeds if we can show:

**1. Real phenomenon**

At least two substantially different public LLM agents exhibit measurable behavioral variation.

**2. Structure**

Variation is meaningfully concentrated at particular execution points.

**3. Attribution signal**

Our weak-point ranking beats trivial baselines such as first-divergence and largest-diff on controlled experiments.

If #1 or #2 fails:

> **Stop and reconsider the thesis.**

Do not build a product around a phenomenon that isn't there.

---

# 25. Six-Week Plan

### Week 1 — One agent

Pick one public multi-step agent.

Build:

```text
runner
trace capture
outcome extraction
experiment persistence
```

Run:

$$
50\ tasks \times 10\ trials
$$

First artifact:

**Figure 1 — Distribution of run-to-run behavioral variation.**

---

### Week 2 — Generality

Add a second, structurally different agent.

Repeat the experiment.

Answer RQ1.

If there is little meaningful variation, stop.

---

### Week 3 — Execution analysis

Implement alignment and event-level variation.

Produce something like:

**Figure 2 — Where execution variation occurs.**

Ask whether variation is concentrated.

---

### Week 4 — Controlled perturbation

Add one or two controlled perturbations.

Measure where small variations become amplified.

**Figure 3 — Variation propagation through agent execution.**

---

### Week 5 — Attribution

Implement:

```text
random
first-divergence
largest-diff
correlation
AgentSeism
LLM debugger
```

Inject known weak points.

Produce:

**Table 1 — Attribution@1 / Attribution@3.**

This is the first serious paper milestone.

---

### Week 6 — Actionability

Take several detected weak points.

Apply manual mitigation.

Run held-out tasks.

Measure:

```text
behavioral variation
task quality
cost
latency
```

Produce:

**Figure 4 — Robustness before and after weak-point-guided mitigation.**

Then make the real decision:

> **Is there a paper here?**

---

# 26. What We Deliberately Postpone

Only after the research thesis works:

```text
automatic perturbation discovery
automatic mitigation
pytest integration
CI integration
beautiful CLI
HTML reports
LangSmith adapters
OpenTelemetry adapters
cloud execution
team features
telemetry
```

Those are all downstream of the same bet: that consequential variation is
concentrated and attributable. Each item is a product investment that only pays
off once RQ1–RQ3 have been answered affirmatively. Building any of them earlier
buys convenience at the cost of the thing that actually decides the project —
evidence.

The ordering rule for the repository is therefore:

> **No feature enters V0 unless it is required by one of the six weekly
> deliverables above.**

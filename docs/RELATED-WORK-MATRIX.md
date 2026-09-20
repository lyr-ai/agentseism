# Related work — the matrix that gates the mutation suite

**Status:** preliminary. **Verdict: framing survives, narrowly.**
**Date:** 2026-09-20

Entries below were gathered in review and are **not independently verified
here**. Each needs checking against its source before it reaches an
introduction — the same rule the Phase 2 bibliography followed.

---

## 1. Preliminary verdict

> **Framing survives, but only in its narrow form: budget-aware statistical
> regression testing for stochastic tool-using agents.**

The safe paper question:

> **How should CI decide whether a change has regressed a stochastic
> tool-using agent under a limited evaluation budget?**

Not:

> We propose a new agent evaluation framework.

The first is specific and checkable and sidesteps a head-on overlap with
general eval platforms and robustness benchmarks. The second invites exactly
that overlap and loses.

**"Agent testing" is not a claimable territory.** Adjacent work already covers
much of it:

| Work | Covers | Why it is not this |
|---|---|---|
| ToolFuzz | generating inputs to find tool-documentation defects | tool-interface testing, not a pre-merge stochastic regression decision |
| AgentNoiseBench | injecting noise into user input and tool environments | robustness benchmarking, not whether a candidate change may merge |
| Multi-Mission Tool Bench | tool-agent robustness under dynamic, multi-task conditions | not paired regression testing across software revisions |
| Flaky-test research | identifying and repairing non-deterministic tests | the object is whether *the test* is flaky, not whether a stochastic agent regressed between revisions |
| Agent-eval practice (offline vs online; comparing prompts, models, architectures) | comparing versions with evals | **so "use evals to compare versions" is not a contribution** |
| Vendor agent-eval guidance | task design, graders, evaluation workflow | not statistical decision-making under a budget |

## 2. The gap that may remain

No single work found so far combines all six:

1. paired stochastic comparison of baseline against candidate;
2. a controlled mutation suite aimed at agent implementation and configuration
   changes;
3. sequential / adaptive sampling that lowers cost at fixed decision quality;
4. explicit `regression / neutral / insufficient evidence / incomparable /
   budget-censored` states;
5. refusing the comparison when the serving-stack fingerprint changes;
6. outcomes gating the merge, trajectories used only for diagnosis.

**The combination is the candidate contribution. No component is claimed as
new**, and nothing is claimed at all until §4 is complete.

## 3. AgentNoiseBench — the work to differentiate actively

Closest to our mutations, and different in what it intervenes on:

| | AgentNoiseBench | AgentSeism |
|---|---|---|
| Changes what | noise in user input and the tool environment | agent code, configuration, prompt, runtime |
| Goal | robustness benchmarking | PR regression decision |
| Compares | models under noise | baseline revision vs candidate revision |
| Resource strategy | benchmark at scale | budget-aware sequential sampling |
| Output | performance degradation | a CI decision and an evidence state |
| Environment change | a test factor | something that can **invalidate** the comparison |

**A design constraint this puts on the mutation suite, not just on the
writing.** If our mutations end up as "add noise to a tool and watch success
fall", the work is covered by AgentNoiseBench and the framing collapses. Every
mutation must be an **engineering change to the agent** — a step limit, a
timeout, an error-recovery policy, a pruning rule, a prompt edit, a runtime
setting — and the measured thing must be a **statistical regression decision
across revisions**, not a degradation curve. This belongs in the mutation
suite's pre-registration as an admissibility rule for candidate mutations.

## 4. The systematic pass, in four buckets

Not yet done. Five fields per paper, nothing else:

```
system under test
intervention / change
decision target
treatment of stochasticity
cost / adaptive mechanism
```

| Bucket | |
|---|---|
| A | agent evaluation and experiment-comparison platforms |
| B | agent robustness, fuzzing, perturbation benchmarks |
| C | flaky / regression / mutation testing |
| D | sequential testing, adaptive experiment allocation |

**The gate.** Build the contribution matrix, then look at the last two columns
— **CI decision target** and **budget-adaptive repeated evaluation**. Only if
both remain clearly empty does the mutation-suite pre-registration begin. If
either is occupied, the framing narrows again or changes, and it is cheaper to
learn that now than after a $100 run.

## 5. Order of work

```
systematic related-work matrix (§4)
      ↓  gate: last two columns empty?
freeze the mutation suite, with §3's admissibility rule
      ↓
cost model and the adaptive-allocation baseline
      ↓
decide what the first $100 buys
```

**C2-H stays sealed. No machine is rented.** Its apparatus is finished,
audited and `CONDITIONAL GO`; it has lost first claim on the budget, not its
validity.

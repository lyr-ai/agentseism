# Two counterexamples from frozen data, at zero compute

**Date:** 2026-09-20. No machine rented, no model called, no container run.
Both results are recomputed from artifacts already committed.

They test the two questions the AgentAssay audit found unhandled
(`docs/AGENTASSAY-AUDIT.md` §2, items 7 and 8):

1. does a trace-level detector report harmless variation as regression?
2. does a missing comparability gate attribute a stack change to the agent?

---

## 1. A trace-only detector on four runs that all passed

`data/runs/h2_phase_a1`, one task, one model, temperature 0, five independent
runs. **Four resolved the SWE-bench issue; the fifth did not.** The four
correct runs:

```
run    steps  edits  final B  tools  wall s
r0        31      3      843      5     971
r1        41      5     1229      7    3107
r2        33      5      978      5     475
r3        47      5     1939      6     437
```

Six correct/correct pairs. **Every pair is, at the outcome level, a
non-regression**: both sides solved the task. Applying distribution-shift
checks of the kind a behavioural fingerprint uses:

| Signal | Fires on | False-positive rate |
|---|---:|---:|
| trace length shift > 20% | 3 / 6 | 50% |
| source edits shift > 20% | 3 / 6 | 50% |
| final patch size shift > 20% | 5 / 6 | 83% |
| tool mix differs at all | 6 / 6 | **100%** |
| wall clock shift > 50% | 5 / 6 | 83% |
| **any of length, tool mix, patch size** | **6 / 6** | **100%** |

**A composite trace detector fires on every pair of runs that were all
correct.** Ground truth: 0 of 6 is a regression.

This is not an argument that fingerprints are useless. It is that a fingerprint
is a **change** detector, and on this workload change is the baseline
condition: the same agent, unmodified, produces a different trace every time.
Without an outcome gate in front of it, sensitivity converts directly into
false alarms.

## 2. A stack change, with the agent held fixed

Gate 9, `data/runs/gate9`. Same model id, same revision `e89b16eb`, same vLLM
0.28.0, same CUDA 13.0, same weights, same prompt, same scaffold. **The agent
did not change.** Only the serving path moved: A100-SXM4-80GB → H100 PCIe,
driver 580.126.16 → 580.105.08.

```
raw response identical    0 / 23
structured action equal   0 / 23
```

What a trace detector without a comparability gate would see:

| Signal | Roots |
|---|---:|
| response length shift > 20% | 13 / 23 |
| first tool differs | 6 / 23 |
| exact command differs | 17 / 23 |
| **some behavioural change** | **23 / 23** |

**It reports a behavioural change on every root, and attributes to the agent a
difference the agent did not make.**

A system whose states are deploy / block / manual has nowhere to put this. The
honest answer is not "regression" and not "pass": it is **incomparable**.

### The scope, kept narrow

This is **one** stack change on **one** workload. It does not show that every
hardware change breaks comparability, and it does not isolate a cause — GPU,
driver and kernel path moved together, and `temperature 0` is not token-level
determinism across execution stacks. What it shows is sufficient for the
design claim and no more:

> A serving-stack change is not safely treated as an ordinary candidate
> mutation. Sometimes it invalidates the comparison instead of constituting
> one.

---

## 3. The separation rule these two support

```
gate on outcomes
diagnose with trajectories
refuse the comparison across serving fingerprints
```

| Situation | Verdict |
|---|---|
| outcome regression, environments comparable | `regression` |
| outcome held, trajectory shifted | `diagnostic change` — does not block a merge |
| serving fingerprint changed | `incomparable` |
| evidence thin | `insufficient evidence` |

§1 is the evidence for the second row; §2 is the evidence for the third.
Neither row exists in the prior art audited, and both are cheap to state and
expensive to discover after the fact.

## 4. What this does and does not license

**Does:** a narrow paper or report on comparability and outcome-gating, with
these two counterexamples as its empirical core, and a minimal new experiment
designed around whichever is weaker.

**Does not:** reviving budget-aware stochastic regression testing, the mutation
suite, adaptive stopping or three-valued verdicts as contributions. Those are
prior art. AgentAssay's own experimental gaps are **not** a reason to reclaim
them — a weakness in someone else's evidence does not transfer a claim.

## 5. Limits of these two, stated before anyone asks

- **One task.** Both counterexamples are `pytest-dev__pytest-10051`. The
  false-positive rate in §1 is a property of six pairs on one workload, not an
  estimate of anything wider.
- **Thresholds are illustrative.** 20% and 50% are stand-ins for a fingerprint's
  decision rule, not a reconstruction of any particular one. The result that
  survives threshold choice is the tool-mix row, which differs on every pair by
  any rule that looks at tool mix at all.
- **§2 is a single stack pair**, and the agent-fixed condition is what makes it
  informative — not the size of the difference.
- Neither is a pre-registered experiment. They are counterexamples computed
  from frozen data, and they are strong enough to *motivate* a narrow design,
  not to conclude one.

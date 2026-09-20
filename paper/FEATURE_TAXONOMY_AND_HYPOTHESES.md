# Feature taxonomy and mutation-to-feature hypotheses

**Status:** frozen taxonomy, hypotheses registered. **Not yet a full
pre-registration** — the minimum practical effects and trial counts in §6 are
proposed, not fixed, and must be settled before any run.
**Date:** 2026-09-20. No machine rented.

## 1. Two layers, kept apart

| Layer | Decides | Who owns it |
|---|---|---|
| **User contract** | which feature changes count as a business regression | the team |
| **Standard features** | what AgentSeism measures, on every agent | the tool |

The paper studies the second. It may not, however, claim merely that these
features detect change — that is close to what the prior art already shows. The
question is:

> **Which agent features separate harmful regression from harmless trajectory
> variation and from an incomparable execution environment?**

Positioning:

> AgentSeism provides a standard, outcome-grounded feature scorecard for
> stochastic agent regression testing, while user contracts specify which
> feature changes matter for a release decision.

## 2. The standard features

Six, each with a statistical unit rather than a vibe.

| Feature | Definition | Statistic | Used for |
|---|---|---|---|
| Task success | did the task complete | rate difference, risk ratio, CI | release gate |
| Recovery success | after an error, did it recover **and** complete | conditional rate | error-recovery capability |
| Progress efficiency | steps / tool calls to completion | median and quantile difference | degraded-but-still-passing |
| Tool reliability | tool-call success, timeout, malformed rate | per-event rates | RCA |
| Cost to success | tokens or dollars **per resolved task** | ratio, bootstrap CI | cost regression |
| Latency to success | wall clock **per resolved task** | median, p95, survival | performance regression |

### Trace features are diagnostic, never a gate

Tool sequence, trajectory length, branch count, state hash are kept — as
**diagnostic** features. They do not independently decide a regression.

This is not caution, it is our own measurement: on four runs that all resolved
the issue, a composite trace detector fires on **6 of 6** pairs
(`paper/COMPARABILITY_COUNTEREXAMPLES.md` §1). Letting a trace feature gate a
merge reinstates exactly that false-positive rate.

## 3. The three the paper is built on

Under a constrained budget, three:

1. **Outcome** — task success.
2. **Recovery** — failure-conditioned recovery.
3. **Efficiency** — steps and cost **conditioned on success**.

*Did it work · could it save itself · did the cost of working get worse.*

**`conditioned on success` is load-bearing.** An agent that fails early looks
cheap and short. Unconditioned efficiency would score it as an improvement. Any
efficiency comparison is computed over resolved runs only, and the resolved
count is reported beside it — a mutation that halves success and halves cost
has not become efficient.

## 4. The mutation matrix

One public, executable, long-horizon coding agent. Four engineering mutations.

| Mutation | Primary feature (registered) | Secondary | Negative control — must **not** move |
|---|---|---|---|
| lower max steps | task success | truncated-run rate | tool reliability — tool calls should still succeed at the same rate; the agent runs out of budget, it does not lose the ability to call tools |
| shorten tool timeout | tool reliability | recovery, task success | malformed-call rate — a timeout is not a format error, and if this moves the mutation is not as targeted as claimed |
| remove the malformed-call recovery hint | recovery success | task success | tool reliability — tools work exactly as before; only the agent's handling of a bad call changes |
| prune context earlier | task success | progress efficiency | tool reliability — pruning changes what the agent remembers, not whether a call executes |

Each mutation carries, registered before running: the primary feature, a
minimum practical effect, a negative-control feature, baseline/candidate
repeated runs, scenario-level paired analysis, and a
`PASS` / `REGRESSION` / `INSUFFICIENT` verdict.

**A moving negative control is a finding, not a nuisance.** It says either the
mutation is less targeted than the hypothesis claims, or the measurement is too
noisy to attribute anything. Both are reportable, and both are reasons not to
read the primary result as clean.

### The serving stack is not in this table

A fingerprint change goes to the comparability gate **before** any feature is
estimated:

```
fingerprint changed → INCOMPARABLE
```

It is not a mutation whose effect on features is measured. Gate 9 is why: with
the agent held fixed and only the serving path moved, 0 of 23 fork roots
matched (`COMPARABILITY_COUNTEREXAMPLES.md` §2).

## 5. Research questions

**RQ1.** Do different engineering mutations produce distinguishable statistical
signatures on the registered features?

**RQ2.** Do outcome-first features avoid the false alarms a trace-only detector
raises on harmless trajectory variation?
→ *the sharpest, clearest separation from the prior art.*

**RQ3.** Do feature-localized signals detect a harmful regression earlier, or
with fewer trials, than task success alone?

**RQ4.** When the serving fingerprint is incompatible, does the comparability
gate prevent misattribution to the agent revision?

### RQ3 carries a trap, and it is registered here

More features means more chances to fire. "Detected earlier" and "looked in
more places" produce the same table if nothing guards them. So RQ3 is
registered with both halves:

- **detection**: trials to a correct `REGRESSION` on a mutation whose primary
  feature is registered in advance;
- **false alarm**: the rate at which any feature fires on the negative controls
  and on the benign-variation condition.

A multiplicity correction across the feature set is fixed before running, and
RQ3 is answered by the pair. **A gain in detection paid for with an equal gain
in false alarms is not a gain**, and the design must be able to say so.

## 6. Still to fix before this is a pre-registration

- minimum practical effect per mutation, per primary feature;
- trials per arm, and the multiplicity correction of §5;
- the agent, the task set, and the frozen image;
- the exact estimator for each statistic — rate difference, bootstrap CI,
  survival;
- how `INSUFFICIENT` is separated from `PASS`: a null result and an underpowered
  one are different findings and must not share a cell.

## 7. Reporting

A scorecard. No composite score in the first version.

| Feature | Baseline | Candidate | Effect | Uncertainty | Verdict |
|---|---:|---:|---:|---:|---|
| Task success | 0.80 | 0.76 | −4 pp | CI crosses 0 | Insufficient |
| Recovery | 0.72 | 0.41 | −31 pp | CI excludes threshold | **Regression** |
| Cost / success | $0.42 | $0.55 | +31% | bootstrap CI | Warning |

A single number needs weights, and weights let a severe recovery regression be
averaged away by three healthy metrics. A release policy can be configured
later; the underlying statistics stay visible beneath it and are never replaced
by it.

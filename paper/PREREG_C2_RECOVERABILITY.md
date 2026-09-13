# Pre-registration — C2, recoverability as a function of horizon

Written 2026-09-12, **before any continuation in this experiment has been run**
and before any of its outcomes exist. The archives it depends on are complete
and verified; nothing downstream of them has been observed.

## Why this and not a predictor confirmation

C1 looked for an early signal that a run would fail and did not find one. Its
candidate — cumulative source edits at step 14 — measures `d = 0.23` in the very
data that suggested it, because at step 14 nineteen of twenty runs are still
holding the same 438-byte state. Separation reaches a medium effect only around
**h ≈ 24** and a large one around **h ≈ 28**, which on a median run of 32–33
steps is three quarters of the way through.

So the bottleneck moved. It is no longer *can failure be predicted* but:

> **By the time failure becomes visible, is the run still recoverable?**

```text
steering window  =  predictable  ∩  still recoverable
```

C1 located the left edge, late. C2 measures whether there is any width.

## The quantity

For a trajectory `T` and horizon `h`, fork from `T`'s state at absolute step `h`
and re-sample the future with **no steering and no prompt change** — the same
agent, the same model, the same configuration, continuing from the restored
state and context.

```text
Recoverability(T, h)  =  P(SWE-bench resolved | fork from T at h)
```

First version deliberately has **no intervention arm**. Whether re-sampling from
a bad state can succeed at all has to be known before asking whether a nudge
improves it.

## Design

### Arms

| arm | trajectories | why |
|---|---|---|
| **FAIL** | `r4`, `A_3`, `A_6`, `B_0` — every failing run that exists | the estimand |
| **PASS control** | `r0`, `r1`, `r2`, `r3` — the four passing A1 runs | the comparison that makes the FAIL numbers mean anything |

Without the control, `Recoverability(FAIL, 24) = 0.50` is uninterpretable: it
cannot distinguish *this trajectory has gone wrong* from *this task is 50% from
step 24 for anyone*. The signal is the **gap between the arms and how it widens
with h**, not the level of either.

The PASS arm is a **negative control and is deliberately smaller**. It is sized
to detect an obvious regression or a non-specific effect, not to estimate its
own curve precisely. If it shows something unexpected, it gets extended — that
decision is itself a later amendment, not a judgement call made at analysis time.

### Horizons

```text
h ∈ {16, 24, 28}   absolute agent step
```

16 is before C1's separation, 24 is where it reaches a medium effect, 28 where
it reaches a large one. **20 is dropped**: the effect table shows it carrying no
information between 16 and 24, and it costs a quarter of the batch.

### Sample

```text
FAIL          4 trajectories × 3 horizons × 4 continuations  =  48
PASS control  4 trajectories × 3 horizons × 2 continuations  =  24
                                                       total =  72
```

16 continuations per horizon in the FAIL arm, 8 in the control. Estimated 8 GPU
hours, roughly $16.

### Frozen configuration

Identical to Phase B: `Qwen/Qwen3.6-27B-FP8` at revision
`e89b16ebf1988b3d6befa7de50abc2d76f26eb09`, `max_model_len` 131072, streaming,
temperature 0, `coding/1`, the fork machinery in `agents/coding/`, and SWE-bench
5.0.2 against `SWE-bench/SWE-bench_Verified` for labelling. Continuation step
budget is `250 − h`, identical across arms and horizons.

## The baseline, fixed now

The unconditional success rate on this task is **16/20 = 0.80**. Every number
below is read against it, and the reading is fixed before the data exists:

```text
Recoverability(h) ≈ 0.80    the trajectory has not gone wrong yet at h
Recoverability(h) ≈ 0.40    half the chance is gone, half remains
Recoverability(h) ≈ 0.05    effectively decided
```

Without this written down, 0.60 supports both "still recoverable" and "already
lost", chosen after the fact.

## What supports and what refutes

**A steering window exists** if the FAIL arm retains substantial recoverability
where C1 says failure becomes visible — concretely, `Recoverability(FAIL, 24)`
comfortably above 0.2 while the gap to the control is already open.

**There is no window on this task** if `Recoverability(FAIL, 24)` is near zero.
Then AgentSeism here is late-stage failure *detection*, not a control system,
and the honest response is a different task or a different intervention point —
not a better feature on this one.

**The measurement failed rather than the hypothesis** if the two arms are
indistinguishable at every horizon, including 28. That would mean forking and
re-sampling does not preserve whatever distinguishes these trajectories, and the
apparatus — not the task — is what needs revisiting.

## Fixed in advance

- 72 continuations, whatever the counts look like at 36. No interim analysis.
- No horizon, arm or trajectory is added, dropped or resized after seeing an
  outcome. Extending the PASS control requires a dated amendment.
- No steering, no prompt modification, no change to the agent in this
  experiment. The moment one is added it is C3 and needs its own registration.
- A continuation that fails for infrastructure reasons is rerun and both
  attempts recorded; transport retries are marked per step as in Phase B.
- Every horizon result is reported with survivors, distinct-history count and
  effect size, per `INVARIANTS.md`.

## What C3 would be, and why it is not this

If a window exists, the next experiment adds an intervention arm at the horizon
where it is widest, and asks the question this design is built to make
answerable:

> **Does steering selectively improve trajectories heading toward failure,
> without degrading trajectories already heading toward success?**

That question needs both arms, which is why the control is being paid for now
rather than added once the FAIL numbers are known. A control chosen after seeing
the treatment is a control that has already lost most of its power to explain.

---

## Amendment C2.1, 2026-09-12 — stratify on whether the fork is already final

**No continuation has been run and no outcome exists.** This follows from the
archives alone, which were complete before the registration was written; it was
missed then and is visible in the execution plan now.

At the registered horizons, many forks land on a state the source trajectory
never left again:

```text
arm   run   h=16        h=24        h=28
FAIL  A_3   e3b0c442    2db5d1e2    = final
FAIL  A_6   400ed404    e3b0c442    e6d78116
FAIL  B_0   400ed404    e3b0c442    = final
FAIL  r4    400ed404    = final     = final
PASS  r0    400ed404    = final     = final
PASS  r1    400ed404    32296bfc    = final
PASS  r2    07dae37d    e3b0c442    = final
PASS  r3    400ed404    e3b0c442    db04bbf1
```

Five of eight at h = 28; two at h = 24.

### Why it matters

Where the fork is already on the final state, the remaining steps of the source
run were verification and submission, not editing. `Recoverability` there is not
measuring *can this run still be saved* but **will re-sampling overturn a patch
that is already written**.

A gap between the arms at h = 28 is then partly mechanical: the passing sources
have a correct answer in place and the failing ones an incorrect one, and
re-sampling mostly submits what it finds. That gap would look like a strong
result and would mostly be a restatement of the labels.

### What changes, and what does not

The plan does not change. Horizons, trajectories, replication and budgets stay
exactly as registered — this is visible in the inputs, and redesigning around it
after the fact would be worse than reporting it.

What is added is a **stratification variable, declared now**:

```text
at_source_final  =  the fork state equals the source trajectory's final state
```

Recorded per spec in `plan.json`, and the analysis reports:

1. `Recoverability(arm, h)` over all specs, as registered;
2. the same **restricted to `at_source_final = False`** — forks taken while the
   source was still editing, which is the question the experiment was meant to
   ask;
3. the count in each stratum at each horizon, since (2) is thin at h = 28.

If (1) and (2) disagree, **(2) is the one that speaks to recoverability** and
(1) is reported as what it is: a measurement dominated by whether the answer was
already written.

### The honest limit

At h = 28, stratum (2) has three of eight trajectories. That is not enough to
carry a conclusion on its own, and saying so now is cheaper than discovering it
while looking at the result.

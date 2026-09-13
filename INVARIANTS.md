# Instrumentation invariants

Three rules, each written after an analysis in this repository reported
something that was not true. They are invariants rather than debugging notes
because all three are the same mistake:

> **Never let a convenient representation substitute for the quantity or
> identity actually being measured.**

---

## 1. Report magnitude, not just direction

Any comparison outputs **effect size and sample counts**, never only `+`/`−` or
a significance verdict.

**What it cost.** A horizon table printed the sign of the difference at each
step. A column of minus signs read as separation, and a confirmatory
pre-registration was nearly written around it. The magnitude was 3.12 against
3.00, `d = 0.23`, with nineteen of twenty runs sitting on the identical state.

Every horizon row now carries:

```text
n_pass_alive          survivors, because late rows are survivorship
n_fail_alive
n_independent         distinct histories, because forks share prefixes
mean_pass  mean_fail
effect_size
```

---

## 2. Preserve absolute execution coordinates

A continuation's local step number may be *displayed*. Every **join or
alignment** uses absolute step or event identity.

**What it cost.** Continuation step 1 was aligned with fresh-run step 1. A
continuation's first step is absolutely step 9 or 11 — it inherited everything
before that — so for fifteen of twenty runs the comparison put a trajectory with
two edits behind it against one with none. Correcting it moved the apparent
signal from step 5 to step 13.

`continuation step 1 == original step 1` is never the default.

---

## 3. Resolve events by identity, never arithmetic position

Finding "the message for step *k*" walks an explicit step-to-event mapping. It
never computes `2k + 1`.

**What it cost.** Message positions were computed as `prefix + 2 * (step − 1)`.
Format errors, retries and system turns add messages without advancing the
environment's step counter, so the mapping slipped the moment one occurred.

**The crash was the lucky outcome.** An even number of interleaved non-step
messages would have aligned silently to the wrong turn and produced an archive
that looked correct and forked from the wrong place. `tests/test_trajectory_mapping.py`
inserts one and then two such messages and asserts the mapping still resolves
the same agent step.

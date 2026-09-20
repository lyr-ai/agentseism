# Pre-registration — C2-H, stack-relative recoverability

**Written 2026-09-20, before any donor exists and before any machine is rented.**
No C2-H trajectory, donor, label or continuation has been generated.

**This is a new experiment, not a C2 continuation.** Its results may not be
pooled with, or compared against, the A100 data as though the serving stack were
held constant. The name marks that: C2-H, not C2.

---

## 1. Why this exists rather than C2

C2 forks from trajectories produced on an A100-SXM4-80GB. Gate 9
(`PREREG_C2_RECOVERABILITY.md` amendments C2.3, C2.3.1) tested whether an H100
PCIe host could continue them and found **0 of 23** archived-comparable fork
roots reproducing the donor's structured action. C2 is therefore **BLOCKED —
donor serving-stack incompatibility**, and stays frozen.

C2-H removes the splice instead of bridging it:

```
one host · one serving process · one dependency lock
        ↓  generate donors here
        ↓  label, freeze donors and fork roots
        ↓  run continuations in the same process, immediately
```

Donors and continuations then share a serving stack by construction, so no
cross-stack compatibility claim is made and no Gate 9 is required.

**Everything runs on one instance, in one session.** Donors are not saved and
continued later on another machine. That is the entire point of the design; a
run split across instances is not C2-H.

---

## 2. Estimand

> The probability that a trajectory reaches a correct outcome when re-sampled
> from horizon `h`, **within one frozen serving stack**.

This is **stack-relative recoverability**. The qualifier is in the estimand, not
in the limitations, because Gate 9 is direct evidence that it does not travel:
it does not extrapolate to another GPU, another serving stack, another driver,
or to the original A100 data.

---

## 3. Design — the 72 specs, in full

The complete cartesian product, fixed here:

```
FAIL arm   4 donors × 3 horizons {16, 24, 28} × 4 replicates  = 48
PASS arm   4 donors × 3 horizons {16, 24, 28} × 2 replicates  = 24
                                                         total  72
```

Every cell is run. There is no sampling within it.

### 3.1 The 36-spec subset, defined now

A nested subset is defined **in advance** so that it can never be produced by
dropping cells after the fact:

```
FAIL replicates 0–1   4 × 3 × 2 = 24
PASS replicate  0     4 × 3 × 1 = 12
                              total 36
```

It is **descriptive only**. It is not a reduced C2-H, it may not be reported as
one, and a run that completes only these 36 is **budget-censored** (§6.4) — not
a smaller experiment that succeeded.

---

## 4. Donor acquisition

1. Generate donors in a **fixed seed order**, recorded before the first one runs.
2. Label each immediately with the frozen correctness checker.
3. Stop once **4 FAIL and 4 PASS** are held.
4. **Hard cap: 30 donors.**
5. If 30 are reached without 4 FAIL, the experiment stops and reports that;
   **no continuations run** (§6.3).
6. Use the **earliest** qualifying donors in seed order. Never selected by
   trajectory length, error type, final-state size, or how recoverable a
   trajectory looks — those are the quantity under study.

The rule is fixed before any label exists and selection depends only on arrival
order, so the adaptive stop is not post-hoc selection.

**Expected donors** under a plug-in rate of `p = 0.20` (observed 4 of 20
labelled runs) is ≈19. That is a *plausible-rate* figure, not a guarantee: the
Wilson interval on 4/20 is [0.081, 0.416], and at the low end the cap is reached
without 4 FAIL about 78% of the time. Donor yield is the dominant risk in this
design and §6.3 is its stop.

---

## 4a. Terminology — `acquisition_index` is not a sampling seed

Clarification of an existing term, committed **before execution**. No design
value changes; `protocol_hash` was unmoved at `30e43200e97e148b` when this was
written, and later moved to `1fda86fedc297132` for the separate reason recorded
in §4b. **The current registered hash is `1fda86fedc297132`.**

> **`acquisition_index`** denotes the donor's position in the pre-registered
> acquisition order of §4. **It is not an inference sampling seed.** Sampling
> remains frozen at `temperature = 0, seed = None`; stochastic variation is the
> object being measured, not something this experiment pins down.

The field was originally written `donor_seed`, which invited exactly the wrong
reading — that donors are reproducible draws. They are not, and an artifact
that says `seed` would carry the ambiguity for as long as the artifact exists.
It is renamed rather than annotated. The rename is free: field names are not
inputs to `protocol_hash`, and no manifest had been frozen.

---

## 4b. Task and image, registered

```
task   pytest-dev__pytest-10051
image  swebench/sweb.eval.x86_64.pytest-dev_1776_pytest-10051:latest
```

The same task C2's donors used. Changing it would invalidate the 4-of-20 donor
yield, the cost model and the whole feasibility analysis — it would be a
different experiment, not a cheaper one — so the image is pinned in
`c2h_protocol.py` and is **not a command-line option**.

A tag can move. The resolved **digest** is read at first deployment and enters
the session fingerprint, so a silently re-pushed image cannot pass as the same
one.

**`protocol_hash` moved from `30e43200e97e148b` to `1fda86fedc297132`** when
task and image were added to its inputs. They are registered values and belong
there. The change was made before any donor existed and before any manifest was
frozen, so nothing already recorded is disturbed.

---

## 5. Held fixed from C2

Horizons **16 / 24 / 28**, to stay commensurable with the original question. A
donor that does not reach a horizon is **ineligible at that horizon by this
rule** — never substituted with a nearby checkpoint, and the ineligibility is
reported.

**Concurrency = 1.** Batched decoding changes vLLM's continuous-batching
behaviour and the numerical execution path, so it is a **serving condition**,
not a speed knob. Gate 9 is the standing evidence that execution-path changes
are not free. It is not adopted to save wall clock.

Model, revision, `max_model_len`, serving flags, scaffold, prompt and the
dependency lock are pinned to `inference/configs/model_h2.yaml` and
`inference/requirements-vllm.lock.txt`, and the resolved stack is recorded
before the first donor.

---

## 6. Stopping rules

All four are fixed here and none is subject to judgement during the run.

### 6.1 Cost forecast is re-estimated at fixed points only

Never continuously, and never on a hunch that it "looks expensive". Exactly
three checkpoints:

- after setup completes;
- after donor acquisition ends;
- before each continuation **block** begins.

**A block that has started runs to completion.** Estimates are not revisited
inside one.

A *block* is one (arm, horizon) group of replicates: eight blocks of 4 for FAIL
at three horizons is 12 blocks, four of 2 for PASS is 12 blocks — 24 blocks
total, each 4 or 2 continuations.

### 6.2 Budget, with a buffer for billing lag

The hard rule is **cumulative Lambda spend**, read from the billing page, and it
includes start-up, model download and tear-down — not just the wall clock of a
script.

| threshold | action |
|---:|---|
| **$85** | start no new block |
| **$90** | stop after the current stage, retrieve artifacts, terminate |
| **$100** | absolute ceiling |

Billing can lag, so $100 is never the trigger to begin stopping. The budget is
**not raised mid-run**; doing so prices the experiment on how it happens to be
going.

### 6.3 Donor-yield feasibility stop

Cap of 30 reached without 4 FAIL → stop, run no continuations, and report a
**donor-yield feasibility stop**. This is not a recoverability result and gives
no recoverability verdict.

### 6.4 Budget-censored feasibility run

Budget thresholds stop the run before all 72 specs complete → report a
**budget-censored feasibility run**, stating exactly which cells ran. This is
not a recoverability result and gives no recoverability verdict, whether or not
the completed cells happen to coincide with the §3.1 subset.

### 6.5 Integrity stop

Any environment or serving integrity check failing → stop. Whatever completed is
a feasibility artifact. **No top-up to finish.**

---

## 7. Cost model, as registered

At `R = $3.29/h`, with 0.6 h measured setup, from `docs/DESIGN-c2h-feasibility.md`:

| case | 72 continuations |
|---|---:|
| Expected / planning | 10.5 h — $34.61 |
| Observed-conservative | 26.2 h — $86.06 |
| Structural ceiling | 95.9 h — $315.50 |

**The per-horizon donor tail times are a planning anchor and are never an upper
bound on a single continuation.** A continuation re-samples rather than
replaying, and its budget is `250 − h` steps — 234 at `h = 16`, roughly 1.0 h at
the median 14.8 s/step. Some re-sampled trajectories will run far longer than
the donor tail they started from. The structural ceiling is 3× the budget, which
is precisely why §6.2 is a spend stop and not a step or time budget.

---

## 8. Analysis

Recovery rate by horizon, per arm, over the 72 specs. The pre-registered
contrast is the FAIL arm across horizons; the PASS arm is a control for whether
re-sampling degrades trajectories that were already succeeding.

Reported alongside, not instead: the donor count actually consumed, the
ineligible (donor, horizon) cells from §5, and the realised cost against §7.

---

## 9. What this cannot claim

- Not a C2 result, and not poolable with the A100 data.
- Not a statement about recoverability on any other serving stack.
- Not a hardware claim. Nothing here isolates a GPU, driver or kernel effect.
- Not a recoverability verdict at all if §6.3 or §6.4 fires.

# C2-H — feasibility and cost ceiling

**Status:** Feasibility design. **Not a pre-registration, and not a C2
continuation.** No machine is rented on the strength of this document; its
purpose is to decide whether a self-contained recoverability experiment fits a
$50–100 budget before anything is booked.

---

## 1. Where C2 stands

```
C2 status       BLOCKED — donor serving-stack incompatibility
                not "failed", and not "inconclusive"
72 specs        frozen, unrun
protocol hash   0fafa0a2534272a6   unchanged throughout
artifacts       data/runs/gate9/ — frozen at cae5b78, pushed
host            Lambda H100 PCIe — TERMINATED 2026-09-20
```

The finding that blocks it is a real infrastructure result, not an absence of
one:

> 23 of 23 archived-comparable fork roots produced a different structured
> action on the H100 stack, so the original A100 trajectories cannot be treated
> as interchangeable prefixes for the same agent on an H100.

Scope, held where the evidence is: this says the **host** does not meet donor
compatibility. It does not isolate a hardware cause — GPU kernels, driver
(580.126.16 → 580.105.08) and several dependency versions moved together, and
`temperature 0` is not token-level determinism across execution stacks, which is
this project's own premise. `A_6 h=16` remains `compatibility_unknown`, so the
phrase *"all fork roots"* stays unusable.

**Cost of the attempt:** to be filled from the Lambda Usage page — instance
`209.20.157.217`, first contact 2026-09-20 01:52 UTC, terminated shortly after
03:20 UTC, so on the order of 1.5 h plus whatever preceded first contact.

---

## 2. Why "find another A100" is not the fix

Matching the GPU model is the *easiest* part of the match and does not by itself
predict a Gate 9 pass. Reproducing the donor stack means reproducing all of:

```
GPU            NVIDIA A100-SXM4-80GB     (SXM4, not PCIe)
driver         580.126.16
CUDA           13.0
vLLM           0.28.0
model          Qwen/Qwen3.6-27B-FP8 @ e89b16ebf1988b3d6befa7de50abc2d76f26eb09
serving flags  max_model_len 131072, prefix caching, max_num_seqs 4,
               enable_auto_tool_choice, tool_call_parser qwen3_coder,
               reasoning_parser qwen3
deps           the full resolved set — see inference/requirements-vllm.lock.txt
scaffold       mini-swe-agent 2.4.6, prompt unchanged, MSWEA_COST_TRACKING=ignore_errors
```

Gate 9 would still have to pass, and a pass is not guaranteed by an exact model
match either — 23/23 differed on a host that already matched vLLM, CUDA, weights
and revision. **The GCP A100 quota request stays open, but no schedule depends
on it.**

---

## 3. The self-contained alternative

```
one host, one serving process, one dependency stack
        ↓
generate donor trajectories here
        ↓
freeze donors and fork roots
        ↓
run continuations immediately, same process
```

Donors and continuations then come from the same serving stack, and the
A100→H100 splice disappears. Gate 9 becomes unnecessary because there is no
cross-stack claim to check.

**This is a new pre-registered experiment.** It may not be called a C2
continuation, and its results may not be pooled with, or compared against, the
A100 data as though the stack were held constant.

---

## 4. Feasibility, with the project's own numbers

### 4.1 How many donors — the binding constraint

Observed failure rate is **4 of 20** labelled runs (`paper/experiments.md`
line 1546); the independent batch `r0`–`r4` was 1 of 5.

**`p` is not known.** Four events out of twenty give a Wilson 95% interval of
**[0.081, 0.416]**. Every probability below is a *plug-in* estimate computed as
though `p = 0.20` were the truth, and none of them is a guarantee. How much that
matters:

| donors N | P(≥4 FAIL) at p=0.081 | at p=0.20 | at p=0.416 |
|---:|---:|---:|---:|
| 20 | 0.07 | 0.59 | 0.99 |
| 25 | 0.14 | 0.77 | 1.00 |
| 30 | **0.22** | 0.88 | 1.00 |

At the low end of the interval even 30 donors yield four failures only ~22% of
the time. **Donor yield, not wall clock, is the dominant risk in this design.**

With that caveat attached, the plug-in table:

| donors N | P(≥4 FAIL) | P(≥3) | P(≥2) | E[FAIL] |
|---:|---:|---:|---:|---:|
| 15 | 0.35 | 0.60 | 0.83 | 3.0 |
| 20 | **0.59** | 0.79 | 0.93 | 4.0 |
| 25 | 0.77 | 0.90 | 0.97 | 5.0 |
| 30 | **0.88** | 0.96 | 0.99 | 6.0 |
| 40 | 0.97 | 0.99 | 1.00 | 8.0 |

**20 donors is a coin flip under the plug-in**, and worse than that if the true
rate sits below 0.20. Matching C2's four-FAIL arm needs ~30 at `p = 0.20` — and
no fixed N is safe across the interval.

### 4.2 Wall clock, from observed donor runs

Observed on A100: `1185, 543, 397, 1347, 213` s — mean 737 s, max 1347 s.

| stage | mean | worst |
|---|---:|---:|
| 20 donors | 4.1 h | 7.5 h |
| 30 donors | 6.1 h | 11.2 h |
| 72 continuations | 14.7 h | 26.9 h |
| 48 continuations | 9.8 h | 18.0 h |
| 36 continuations | 7.4 h | 13.5 h |

Continuations carry a donor prefix, so these are optimistic: context is larger
from step one. Prefix caching pulls the other way — every continuation in an arm
shares its donor prefix, so after the first it is a cache hit.

### 4.3 Budget — conditionally feasible, not yet budget-safe

At the observed Lambda rate `R = $3.29/h`, plus ~1 h of setup and download:

| design | mean | worst |
|---|---:|---:|
| 30 donors + 72 continuations | 21.9 h = **$71.99** | 39.1 h = **$128.64** |
| 30 donors + 36 continuations | 14.5 h = $47.74 | — |
| sequential donors + 72 continuations | 19.8 h = $65.26 | bounded by the cap |
| sequential donors + 36 continuations | 12.5 h = $41.01 | bounded by the cap |

**The mean fits $50–100. The worst case does not.** That is a budget-safety
problem, not an infeasibility: the correct description is **conditionally
feasible, not yet budget-safe**. Reading a worst-case overrun as "cannot be
done" would be the wrong inference, and the earlier revision of this document
made it.

What is *not* yet resolved is the interaction between the two risks: the
donor-yield uncertainty of §4.1 and the wall-clock spread. A full cost model has
to price the continuation stage and the failure-stop rule together before a
machine is booked again.

### 4.3.1 Sequential donor acquisition

A fixed batch of 30 is not the most efficient way to reach four FAIL donors.
Pre-registered sequential acquisition:

1. generate donors in a fixed seed order;
2. label each immediately with the frozen checker;
3. stop once 4 FAIL and the required PASS count are in hand;
4. hard cap of 30 donors;
5. if 30 are reached without 4 FAIL, **the experiment stops and reports that**;
   no continuations run;
6. use the **earliest** 4 FAIL and the earliest qualifying PASS — never selected
   by trajectory length, error type, or how recoverable they look.

The rule is fixed before any label exists, so adaptive stopping here is not
post-hoc selection: nothing about *which* trajectories are used depends on
anything but arrival order.

Expected donors, and the risk of hitting the cap:

| | E[donors] | P(cap 30 hit without 4 FAIL) |
|---|---:|---:|
| p = 0.081 (CI low) | 28.4 | **0.78** |
| p = 0.20 (plug-in) | 19.1 | 0.12 |
| p = 0.416 (CI high) | 9.6 | 0.00 |

At the plug-in rate this saves ~2 h against a fixed 30 (~$6.60) and, more
usefully, stops generating trajectories that will never be used. At the low end
of the interval it mostly buys an early, honest stop instead of a full-price
null.

### 4.4 The levers, and what each costs

| Lever | Saving | What it costs |
|---|---|---|
| 3 horizons → 2 | ~⅓ of continuations | Loses one point on the recoverability curve; h≈24 and h≈28 are where C1 found separation, so 16 is the candidate to drop |
| FAIL replicates 4 → 3 | ~⅛ | Widens the interval on the arm that matters most |
| PASS replicates 2 → 1 | ~⅛ | The control arm loses its within-donor variance estimate |
| Donors 30 → 20 | ~2 h | Drops P(≥4 FAIL) to 0.59 — **not recommended**; this is the constraint, not the slack |
| Concurrency 1 → 4 | up to ~4× | Donors and continuations must then *both* run concurrently, so it is a registered serving condition, not a scheduling trick |

Concurrency is the only lever that buys time without buying uncertainty, and it
is the one that most needs to be fixed in advance rather than adjusted mid-run.

---

## 5. Recommended answers for a C2-H pre-registration

Recommendations, not registrations. They become binding only when written into a
dated pre-registration before any donor is generated.

**1. Estimand.** The probability of recovery from a given horizon **within one
frozen serving stack**. This is explicitly *stack-relative recoverability*: it
does not extrapolate to another GPU, another serving stack, or the original A100
data. Gate 9 is the reason that qualifier has to be in the estimand rather than
in the limitations.

**2. Donor generation.** Fixed seed order, sequential; stop once the registered
FAIL and PASS counts are reached; hard cap 30. See §4.3.1.

**3. Donor selection.** The frozen checker labels first; a mechanical
"earliest qualifying" rule then selects. **Never** by trajectory length, error
type, or how recoverable a trajectory looks — those are the quantity under
study.

**4. Horizons.** Keep 16 / 24 / 28, to stay commensurable with the original
question. A donor that does not reach a horizon is **ineligible at that horizon
by a pre-registered rule** — never substituted with a nearby checkpoint.

**5. Concurrency.** `concurrency = 1` for the first C2-H. Batched decoding
changes vLLM's continuous-batching behaviour and the numerical execution path,
which makes it a **serving condition**, not a speed knob. Gate 9 is the standing
evidence that execution-path changes are not free. Do not adopt it to save wall
clock.

**6. Budget and stopping.** Hard ceiling of **$100 or 30 instance-hours,
whichever comes first**. If the donor stage reaches its cap without the
registered FAIL count, the experiment stops and reports that; continuations do
not run. The budget is not raised mid-run to finish — doing so would price the
experiment on how it happens to be going.

## 6. Recommendation

**Conditionally feasible, not yet budget-safe.** Not "cannot be done".

- The mean case fits: 30 donors + 72 continuations is ~$72 at $3.29/h;
  sequential acquisition brings it to ~$65.
- The worst case does not: ~$129, with no margin for a restart.
- The dominant risk is **donor yield**, not wall clock. `p` is 4/20 with a 95%
  interval of [0.081, 0.416], and at the low end even 30 donors reach four
  failures ~22% of the time.

Before renting again, complete a full cost model covering the continuation stage
and the failure-stop rule together, and set the hard stop in advance. Nothing in
§5 costs compute to answer.

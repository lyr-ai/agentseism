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
line 1546); the independent batch `r0`–`r4` was 1 of 5. Taking `p = 0.20`:

| donors N | P(≥4 FAIL) | P(≥3) | P(≥2) | E[FAIL] |
|---:|---:|---:|---:|---:|
| 15 | 0.35 | 0.60 | 0.83 | 3.0 |
| 20 | **0.59** | 0.79 | 0.93 | 4.0 |
| 25 | 0.77 | 0.90 | 0.97 | 5.0 |
| 30 | **0.88** | 0.96 | 0.99 | 6.0 |
| 40 | 0.97 | 0.99 | 1.00 | 8.0 |

**20 donors is a coin flip**, not a plan: it yields four FAIL donors 59% of the
time. Matching C2's four-FAIL arm with reasonable confidence needs ~30.

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

### 4.3 The verdict on budget

With hourly rate `R` and ~1 h of setup and model download:

```
30 donors + 72 continuations   mean  ≈ 21.8 h · R     worst ≈ 39.1 h · R
30 donors + 36 continuations   mean  ≈ 14.5 h · R     worst ≈ 25.7 h · R
20 donors + 36 continuations   mean  ≈ 12.5 h · R     worst ≈ 22.0 h · R
```

**The original 72-spec shape does not fit $50–100 at adequate donor power.** At
any plausible H100 rate, 30 donors plus 72 continuations consumes the whole
budget at the mean and overruns it badly at the worst case, with no margin for a
restart.

A reduced shape fits. It must be **registered as its own design**, with its
power stated — not inherited from C2 by dropping rows.

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

## 5. What a C2-H pre-registration must settle first

Open questions. None is answered here, and answering them is the next
deliverable if this proceeds.

1. **Donor selection without seeing outcomes.** Arms are defined by correctness,
   which is an outcome, so the rule cannot avoid labelling. It can avoid
   *choosing*: generate N donors, label all N by the frozen checker, then apply a
   mechanical selection fixed in advance (for example, every FAIL donor up to k,
   and PASS donors by ascending run index). The rule is written before the labels
   exist; the selection is then arithmetic.
2. **N.** §4.1 says ~30 for a four-FAIL arm at 88%. Fewer FAIL donors is a
   different experiment and must say so.
3. **Arm formation** when FAIL donors exceed or fall short of k.
4. **Horizons.** Keep 16/24/28, or drop 16 and state why before running.
5. **Total calls, H100 hours, hard budget**, and the point at which the run stops
   regardless of progress.
6. **The stop rule for too few failures.** If the donor batch yields fewer than
   the registered minimum FAIL trajectories, the experiment stops and reports
   that, rather than lowering the arm size or generating donors until enough fail
   — which would be optional stopping on the quantity the experiment is about.

---

## 6. Recommendation

Do not rent anything yet. Answer §5 first, at zero compute cost. The budget
question is already answered: **the C2 shape as frozen does not fit, and a
shape that does fit is a different experiment that has to be registered as
one.**

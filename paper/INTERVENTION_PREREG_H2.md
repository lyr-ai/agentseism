# Pre-registration — H2, what survives reconvergence

Written 2026-09-07, before any run of this experiment. This is the first
AgentSeism experiment that intervenes rather than observes.

Frozen inputs: `mini-swe-agent` 2.4.6, `Qwen/Qwen3.6-27B-FP8` at revision
`e89b16ebf1988b3d6befa7de50abc2d76f26eb09` served by vLLM 0.28.0, temperature 0,
`coding/1` features. One change from the primary experiment: **`max_model_len`
32768 -> 131072**. The reason exists independently of any outcome and was
recorded before this design: the primary batch lost 4 of 30 runs to
`ContextWindowExceeded`, including all three runs of `mwaskom__seaborn-3069`,
which is censoring correlated with trajectory length.

## Provenance, and what may not be reused

The primary 30-run experiment is **hypothesis-generating for H2 and supplies no
confirmatory data**. It contributed exactly two things: the observation that a
`D=1, R=1, F=0` topology exists, and the choice of task domain. Its trajectories
are not analysed again here, and no continuation is forked from them.

The observation, stated so that it can be checked against later:

> On `pytest-dev__pytest-10051`, all three runs independently reached the
> identical non-empty tracked source state `400ed404…` (438 bytes, one file,
> `src/_pytest/logging.py`) — the same one-line change,
> `self.records = []` -> `self.records.clear()`. All three then ran the existing
> `testing/logging/` suite, reverted with `git checkout`, and wrote three
> different final fixes: `5c9780ad…`, `0311c057…`, `b387c8a3…`.

Reconvergence there is not a chance meeting. It is a shared attractor — the
obvious hypothesis — followed by a shared refutation and divergent repair. That
mechanism is what H2 is about, and it is why the experiment is worth its GPU
cost even though the primary batch already showed the topology exists.

## What is controlled and what is not

At `400ed404…` the three runs held **different** workspaces: `test_repro.py`
(`bad66426…`), `reproduce_issue.py` (`777d3b59…`), `repro.py` (`dde103ca…`).
The tracked source was identical; nothing else was.

So `do(S_t = S), vary(H_t)` with `H` meaning *message log only* is not
available. Transplanting run B's messages into run A's container puts the agent
in a context its own history contradicts — it would `cat reproduce_issue.py` and
be told the file does not exist — which is off-distribution behaviour, not a
controlled contrast.

The intervention is therefore defined as:

> **Controlled:** the tracked source state `S` (`git diff HEAD`, byte-identical).
> **Manipulated:** the *carried context* — the agent's message log together with
> the untracked files that agent itself created. These travel as one bundle.

The claim H2 can support is correspondingly scoped: *repository-source
convergence does not imply agent-state convergence*, where agent state includes
the scratch files the agent left behind. That is the honest granularity and it
is stated here rather than discovered later.

## Hypotheses

**H2a — refutation is state-carried.** A continuation from `S` with no prior
history abandons `S` (leaves that tracked state and does not return to it) at
approximately the rate donor-history continuations do. The evidence that refutes
the naive fix lives in the repository's own test suite, not in the transcript.

**H2b — repair is history-carried.** Among continuations that abandon `S`, the
final tracked source state depends on which donor history is attached:
continuations carrying donor A's context reach A's final state more often than
continuations carrying donor B's context do.

H2a and H2b are separate and either can fail alone. The interesting joint
outcome — refutation state-carried, repair history-carried — would mean the
model's *conclusions* about the repository are recoverable from the repository
while its *commitments* are not.

**The null is publishable.** If all three arms produce the same distribution of
final states, re-divergence is resampling noise at a branch point rather than
path dependence, and the topology found in the primary experiment is a fact
about the task's solution landscape alone. Both directions are written up.

## Design

### Phase A — donor generation (fresh data)

`pytest-dev__pytest-10051`, **5 independent runs**, `max_model_len` 131072,
otherwise the frozen configuration. These are new runs; the exploratory three
are not donors.

**Fork point rule, fixed now:** the tracked source state `S` that (i) is
non-empty, (ii) is held at some step by the largest number of runs, and (iii)
among ties, is reached at the smallest maximum step index across those runs.
Donors A and B are the two runs holding `S` with the **smallest** and
**largest** step index at which they first reach it — chosen by step index, a
quantity fixed before their outcomes are consulted, so that the pair is not
selected on how differently they ended.

**If Phase A yields no state held by ≥2 runs, the experiment does not proceed on
this task.** The fallback order is fixed now, by reconvergence observed in the
exploratory batch: `pallets__flask-5014`, then `sphinx-doc__sphinx-10323`, then
`astropy__astropy-12907`. At most one fallback is attempted. If that also
yields no fork point, the result is reported as "H2 not testable in this
representation" and no further task is tried.

### Phase B — the intervention

From the single fork point `S`, three arms, **8 continuations each, 24 total**:

| arm | tracked source | message log | untracked files |
|---|---|---|---|
| **A** | `S` | donor A's prefix, up to and including the step that produced `S` | donor A's |
| **B** | `S` | donor B's prefix, likewise | donor B's |
| **fresh** | `S` | system + instance templates only | none |

The fresh arm receives the unmodified system and instance prompt, with no
narration of what was already done. It is a genuinely minimal-history condition,
not an equalised one, and the asymmetry is intended: it is what "the repository
without the transcript" means.

### Budget equalisation

Donor prefixes differ in length, so continuations would otherwise differ in
remaining budget. Every continuation in every arm is given the **same** step
allowance and the same wall-clock allowance, set to
`250 − max(len(prefix_A), len(prefix_B))`. Remaining context tokens cannot be
equalised — a longer prefix consumes more — and the prefix token counts of A, B
and fresh are recorded and reported so the residual asymmetry is visible. At
131072 this is not expected to bind; if any continuation exits
`ContextWindowExceeded` the arm's censoring rate is reported and that arm's
comparisons are flagged.

## Exact fork mechanism

1. **Archive (Phase A instrumentation).** The probe additionally stores, per
   step, the **content** of `git diff HEAD` and a tar of the untracked files it
   already enumerates. The primary experiment stored only their hashes, which is
   why a fork from its trajectories is impossible. This is an archival channel:
   **no stored content enters any feature, comparator, or classification**, and
   `coding/1` is unchanged as a representation.
2. **Container.** Start the SWE-bench Verified image for the instance at its
   pinned base commit. `git apply` the archived tracked diff for `S`; verify by
   recomputing `tracked_diff_hash` and requiring byte equality with `S`. Unpack
   the arm's untracked archive (empty for the fresh arm); verify
   `workspace_diff_hash` equals the donor's value at that step. **A container
   that fails either check is discarded and rebuilt, not used.**
3. **Messages.** A `ForkAgent(DefaultAgent)` overriding `run()` to seed
   `self.messages` with the donor prefix verbatim instead of the two-message
   system+instance seed, then entering the unmodified loop. No message is
   rewritten, summarised, or annotated; the agent is not told it was forked.
4. **Independence.** Each continuation is a separate container and a separate
   model session. Stochasticity comes from the serving stack under temperature 0
   (batching-dependent kernel nondeterminism), the same source as in the primary
   experiment.

### Validity gate (manipulation check)

At temperature 0 a faithful fork should partly reproduce the donor's own
continuation. **Gate:** at least one of the 8 arm-A continuations reproduces
donor A's next 3 command signatures, and likewise for B. If both arms fail this,
the fork is not faithful — most likely the container reconstruction — and **the
experiment is void and reported as void**, not reinterpreted. Passing on one arm
only is reported and the run continues.

## Outcome measures

Declared now, both of them, so neither is a later rescue.

**Primary (H2b): donor match, exact.** For a continuation `c` in arm `X ∈ {A, B}`
with final tracked state `F_c`, `match_A(c) = [F_c == F_A]`. The test statistic
is `P(match_A | arm A) − P(match_A | arm B)`, predicted **> 0** under H2b. The
symmetric statistic on `match_B` is computed and reported alongside; both are
part of the primary claim and both must point the same way for H2b to be
supported.

**Secondary (H2b): donor match, hunk-location.** Exact hash equality may be too
strict to detect a real effect. The secondary measure replaces `F_c == F_A` with
equality of the set of `(file, hunk start line, hunk length)` triples in the
final diff — same edit sites, whitespace and content aside. It is reported
always, and is **secondary**: if primary and secondary disagree, the conclusion
follows the primary and the disagreement is reported as a limitation.

**H2a: abandonment.** `abandon(c) = [S ∉ states(c) after step 0]` — the
continuation leaves `S` and does not end on it. Compared across all three arms.
H2a is supported if the fresh arm's abandonment rate is within the range spanned
by arms A and B; refuted if the fresh arm ends on `S` markedly more often, which
would mean the refutation travelled in the transcript.

**Descriptive, not tested:** distinct final states per arm, step counts, whether
any continuation reaches a final state seen in neither donor.

## Inference and stopping

- **Fixed n. 24 continuations, whatever the counts look like at 12.** No interim
  analysis is run; the analysis script is executed once, after all 24 finish.
- Fisher's exact test, one-sided in the predicted direction, on the 2×2 of
  arm ∈ {A, B} × `match_A`. Reported with the exact counts, not only a p-value.
- α = 0.05 for the primary. The secondary measure and H2a are reported with
  effect sizes and exact counts and are **not** used to declare support for H2b.
- Two hypotheses (H2a, H2b) are tested on one dataset. No multiplicity
  correction is applied because they are separate pre-stated claims reported
  separately; neither is used to rescue the other.
- With 8 per arm, 8/8 vs 0/8 gives p ≈ 0.0002 and 6/8 vs 1/8 gives p ≈ 0.04.
  A weak effect will not be detectable, and that is accepted: this experiment is
  powered for a strong path dependence, not a subtle one.

## Fixed in advance

- The fork point is chosen by the stated rule from Phase A alone, before any
  continuation is run and before donor final states are used for anything except
  defining the outcome targets.
- No arm is added, dropped, resized, or rerun after seeing its results.
- No second fork point on the same task. No second task beyond the single stated
  fallback.
- A continuation that fails for infrastructure reasons — endpoint down,
  container build failure, reconstruction check failure — is rerun and both
  attempts are recorded. A continuation the agent itself ends without a patch is
  data and stays.
- `coding/1` is not extended. The archival channel added in Phase A is storage,
  not representation, and nothing stored there is used to classify anything. Any
  actual change to the feature set means `coding/2` and a written reason.
- If H2b fails, it is reported as failed. The primary experiment's re-divergence
  topology stands as an observation either way; it does not depend on this
  result and will not be re-described to match it.

## Cost

Phase A: 5 runs × ~12 min ≈ 1 h. Phase B: 24 continuations from roughly a third
of the way in, ~7 min each ≈ 2.8 h. Total ≈ 4 GPU-hours, ≈ $2 on one A40.
GPU-hours are recorded; `instance_cost` is unavailable for a self-hosted model
and `MSWEA_COST_TRACKING=ignore_errors` stays set.

---

## Amendment H2.1, 2026-09-08 — donor eligibility, and a batch frozen out

**This amendment was triggered by an outcome, and that is stated first because it
cannot be argued away.** Phase A ran five trajectories, all five completed, all
five passed through the same non-empty source state, and the donor rule above
selected r4 (arrival step 8) and r1 (arrival step 12) — two runs that ended on
the *same* final source state, `ad3317821606…`. The gate reported
`UNIDENTIFIABLE`, no manifest was written, and Phase B did not start. The
numbers are in `paper/manifests/h2_phase_a0_gate_report.json`.

### What was wrong with the rule

Not the sample. The rule. It selects donors by first-arrival step, a quantity
that says nothing whatever about where the two runs end, while the primary
measure is

    P(F_A | C_A) − P(F_A | C_B)

which requires `F_A` and `F_B` to be different states. When they are not, that
expression does not estimate zero — it is undefined. "Context carried the agent
back to A's repair" and "context carried it back to B's repair" are the same
sentence when A and B made the same repair. The original rule could produce a
comparison that no number of continuations could resolve, and nothing in it
prevented that.

### The replacement

Donor eligibility becomes a property of the **pair**:

> A pair is H2b-identifiable only if (1) both runs are `Submitted`, (2) both
> naturally reach the same non-empty tracked source state `S`, and (3) their
> canonical final tracked states differ, `F_A ≠ F_B`.

Among eligible pairs, the original outcome-independent tie-break applies, made
total: widest spread in first-arrival step, then earliest arrival, then run id.
The tie-break reads arrival steps only.

**The fork point `S` is still chosen by the unamended rule.** Conditioning `S` on
whether it yields an eligible pair would be a second selection, and the
conservative reading is that a batch whose `S` has no eligible pair has failed —
not that another `S` should be tried.

### What this costs, said plainly

`F_A ≠ F_B` is an **estimand eligibility condition, not a finding**. H2b no
longer asks whether carried context matters across reconverged trajectories in
general. It asks:

> Among donor pairs that naturally reconverge on `S` and then reach *different*
> repair states, does carried context causally bias a continuation toward its own
> donor's repair?

That is narrower. It is also the only version of the question the design can
answer, and stating the restriction is the difference between a narrowed claim
and an overstated one.

### The five existing runs are frozen out

The five Phase A trajectories are relabelled **Phase A0, design-discovery**. Four
distinct final states exist among them, so an eligible pair could be drawn from
them under the new rule — which is exactly why it will not be. Choosing a pair
after seeing which pairs separate is selection on outcome no matter how
principled the rule looks written down.

A0 supplies no donor, no continuation, and no confirmatory number. Its
trajectories may be described; they may not be tested.

### Phase A1

Five fresh runs, same task, same frozen configuration, same archive. The gate
runs mechanically on them and reports `QUALIFIED`, `UNIDENTIFIABLE`, or
`NO FORK POINT`.

**There is no third attempt.** If Phase A1 also returns `UNIDENTIFIABLE`, the
experiment stops on this task and the result is reported as what it is: this
donor-generation protocol does not reliably produce an identifiable contrast, and
the intervention needs a different design rather than more sampling. Drawing
batches until one yields a usable pair would make the eventual pair a selected
one, and the whole point of the gate is that it cannot be talked past.

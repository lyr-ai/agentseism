# Pre-registration — H3, how trajectory agreement decays with horizon

Written 2026-09-09, before any decay curve has been computed at any horizon
other than the one already fixed. Frozen inputs are those of H2: `coding/1`,
`mini-swe-agent` 2.4.6, `Qwen/Qwen3.6-27B-FP8` at revision
`e89b16ebf1988b3d6befa7de50abc2d76f26eb09`, vLLM 0.28.0, temperature 0,
`max_model_len` 131072, streaming, and the fork machinery in `agents/coding/`.

## Where this comes from, and what that costs

H2b asked whether carried context biases a continuation toward its donor's
repair. It could not be tested: fifteen continuations produced fifteen distinct
final states and the target event never occurred. What made that readable was the
pre-registered manipulation check, which found that **14 of 16 continuations
reproduce their donor's next three action signatures exactly** while **0 of 15
reach its final state**.

So the interesting quantity was never terminal identity. It is the shape in
between.

> **H3.** From an identically reconstructed agent state, trajectory agreement
> with the donor is high at short horizons and decays to near zero over the
> remainder of the execution.

**Only `h = 3` on signatures is already pre-registered** — it is the manipulation
check. Every other horizon on the existing pytest data is **exploratory**, is
computed from the batch that generated this hypothesis, and is labelled as such
wherever it appears. The confirmatory test is a second task.

## The quantity

For continuation `c` in arm `X`, forked from donor `D` at donor step `f`, let
`c_h` be `c`'s own h-th action and `D_{f+h}` the donor's. Two curves, because the
first experiment already showed they are not the same question:

    pointwise(h)   agreement at step h alone      — can fall and recover
    survival(h)    agreement at every step 1..h   — monotone by construction

The 30-run experiment found a `D=1, R=1, F=0` topology: runs that diverge, meet
again, and part. `pointwise` is the curve on which that recovery is visible;
`survival` cannot show it by construction. Reporting only `survival` would define
a known phenomenon out of existence.

Three granularities, all reported, because the claim "locally reproducible"
should not rest on how coarse the projection is:

    signature    the `coding/1` command signature, e.g. `sed:-n`
    command      the exact command string
    state        `tracked_diff_hash` after the action

`signature` abstracts away arguments: two runs that both ran `sed -n` on
different line ranges agree under it and disagree under `command`. The existing
14/16 result is on `signature` alone, and what it licenses is a statement about
**action types**, not about identical actions.

**Censoring.** Agreement at horizon `h` is undefined once either trajectory has
ended. The denominator at each `h` is reported alongside every curve. A curve is
not drawn past the horizon where fewer than half the continuations remain.

**Transport censoring.** A step that took more than one transport attempt was
sampled more than once, and the extra draw lands directly in this quantity. Each
continuation is therefore **right-censored at its first retried step** for the
primary curves, with the uncensored version reported beside it. This is decided
now, before any curve exists, and applies whatever the retry rate turns out to be.

## Summary statistics, fixed now

    half-life     smallest h with survival(h) <= 0.5
    early         pointwise(1)
    terminal      pointwise at the last horizon with a valid denominator

## What supports and what refutes

**Supports H3:** `early > 0.75` and `half-life <= 10` on at least the `signature`
granularity, in both arms, on the confirmatory task.

**Refutes H3, informatively:** `survival(10) > 0.5` — agreement persists, and
reconstructed state does determine long-horizon behaviour after all, which would
make the pytest result a property of that task rather than of the method.

**Refutes H3, differently:** `early <= 0.5` — there is no local reproducibility to
decay from, and the picture is immediate dispersion rather than decay. Then the
word "decay" is wrong and the finding is simpler and starker.

**Uninformative:** censoring bites before `h = 10` in most continuations. Then the
horizon range is too short to see a decay and the design needs longer
trajectories, not more of them.

## The confirmatory task

`pallets__flask-5014`, taken from the fallback order **already frozen in
`paper/INTERVENTION_PREREG_H2.md`** (flask, then sphinx, then astropy). No new
choice is made here. It is the re-divergent one of the three in the 30-run
experiment; sphinx and astropy were absorbed, and they remain available for a
later question about whether decay itself is task-dependent.

Protocol, unchanged from H2: Phase A of 5 runs, the frozen gate
(`experiments/coding/phase_a_gate.py`) selecting a fork point and two donors,
rebuild verification, then 8 continuations per donor arm. Two donors give two
independent decay curves on one task, which is a within-task replication and not
an extra degree of freedom.

The fresh arm is not part of H3.

## Precondition: transport

**This batch is not collected until the endpoint no longer goes through
Cloudflare's HTTP proxy** — a direct TCP port, or a different provider. On the H2
batch, 10 of 15 continuations contained at least one transport retry, and under
the censoring rule above that would truncate two thirds of the curves. Terminal
identity could absorb that as background noise; a horizon curve cannot.

The transport audit runs before the gate, and a batch whose arm-level retry rate
exceeds 0.02 is reported as transport-limited with its censored curves as the
only primary result.

## Fixed in advance

- 5 Phase A runs, 8 continuations per arm, 16 total. No interim curves.
- No horizon, granularity or summary statistic is added after the curves exist.
- The exploratory pytest curves are computed once, labelled exploratory, and are
  not used to choose anything about the flask analysis.
- A continuation that fails for infrastructure reasons is rerun and both attempts
  recorded; one the agent ends itself is data.
- If flask's Phase A gate returns `UNIDENTIFIABLE` or `NO FORK POINT`, H3 is not
  tested on flask and the next task in the frozen order is used, once. The H2b
  eligibility condition `F_A != F_B` is **not** required here — H3 compares each
  continuation with its own donor and never with the other arm's target — but the
  gate is run unmodified and its verdict recorded either way.

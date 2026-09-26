# Decision — main line and RCA backend swap places

**Date:** 2026-09-20. **Status:** adopted. No machine rented.

## The main line

> **Feature-driven agent regression testing.** Apply controlled engineering
> perturbations to the capabilities a team cares about, decide regression on
> **outcomes**, locate the cause with **traces**, and **refuse the comparison**
> when the environment changed.

The former main line — forking at arbitrary trajectory nodes to study when a
run stops being recoverable — becomes an RCA and research tool.

## Priorities

| P | Module | Rationale |
|---|---|---|
| **P0** | Feature contract: capability → mutation → outcome, declared | the entry point |
| **P0** | Baseline/candidate repeated testing and effect size | the core |
| **P0** | `PASS` / `REGRESSION` / `INSUFFICIENT` / `INCOMPARABLE` | the core |
| **P0** | Serving-fingerprint comparability gate | the differentiator |
| P1 | Trace RCA, after a confirmed regression | product value |
| P2 | Budget-adaptive sampling | cost optimisation, **not** a claimed contribution |
| P2 | Node forking and recoverability | RCA backend, or later research |
| **paused** | general mutation score, composite agent score | overlaps prior art and explains poorly |
| **paused** | the paid C2-H experiment | not required by any current decision |

## Why

AgentAssay already covers stochastic repeated evaluation, mutation testing,
SPRT and adaptive budget, the CI/CD gate and behavioural fingerprinting. "We
perturb N features and score the agent" is the same framework with different
nouns. Four things can carry a difference:

1. **Feature contract** — a pre-registered mapping from an engineering change
   to a user-visible capability to an outcome metric, not a generic mutant.
2. **Outcome-first gating** — a trace change is not a regression.
3. **Comparability-first** — an incompatible environment yields `INCOMPARABLE`.
4. **RCA on demand** — locate the divergence only after an outcome regression.

2 and 3 already have frozen evidence
(`paper/COMPARABILITY_COUNTEREXAMPLES.md`). 1 and 4 have none yet.

## The vertical slice, before any large experiment

One public agent · 2–3 real engineering mutations · 3 feature contracts ·
baseline/candidate repeated runs · the four-state verdict · one RCA report on a
confirmed regression · one "trajectory moved, outcome held, do not block"
counterexample · one `INCOMPARABLE`.

### Two of the eight panels are already paid for

| Panel | Source | New compute |
|---|---|---|
| trajectory moved, outcome held | `h2_phase_a1` — a trace detector fires on 6/6 pairs that all resolved | **$0** |
| `INCOMPARABLE` | `gate9` — 0/23 with the agent held fixed | **$0** |
| a confirmed regression, and its RCA | — | new runs |

So the slice needs runs only for the regression arm:

| design | runs | $ median | $ mean |
|---|---:|---:|---:|
| 2 arms × 5 trials | 10 | $6 | $12 |
| **3 arms × 5 trials** | **15** | **$8** | **$16** |
| 3 arms × 8 trials | 24 | $12 | $25 |

Against C2-H's $41 median / $89 mean. **The slice is roughly a fifth of the
experiment it replaces**, because the two hardest panels to produce are the two
already sitting in frozen artifacts.

## The acceptance test, and a problem with it as stated

Stated: *if a developer sees the report and understands it, and would put it in
a PR, the direction holds; if it still needs a long explanation, narrow
further.*

The judgement is right and the test as written is **self-graded**. We wrote the
report, so we will find it clear. Made concrete and cheap:

- show the report **cold** to 3–5 engineers who have not seen this project;
- no explanation, no framing, one question: *what would you do with this PR?*
- record their answers **before** discussing;
- the test passes if they name the degraded capability and the action without
  being told what the columns mean.

Failing that is a finding about the report, which is the thing being tested.
Pre-committing to the question and to writing the answers down first is what
keeps it from becoming a demo we talk people through.

## What is sealed, not discarded

C2-H stays sealed: pre-registered, implemented, audited, `CONDITIONAL GO`, 298
tests. It is not required by any current decision.

Reused as-is by the new main line: the budget state machine and its
billing-baseline semantics, atomic artifacts with digests, the session
fingerprint, fail-closed resume, the frozen correctness checker, the trace and
fork tooling, and the two counterexamples. **The apparatus was not built for
the wrong experiment. It was built in the wrong order, and the order is now
fixed.**

## Next

1. Write the feature contract schema — capability, perturbation, expected
   direction, outcome metric, minimum practical effect. **Expected direction
   registered before running**, or the slice proves nothing.
2. Pick the agent, the task set and 2–3 mutations.
3. Cost it exactly, then decide whether $8–16 of GPU buys the regression panel.
4. Assemble the eight-panel report and run the cold-read test.

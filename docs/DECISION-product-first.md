# Decision — product first, paper discipline kept

**2026-09-20.** Gate 1 is closed. This sets what the next 4–6 weeks buy.

## The unknown has moved

It is no longer *can we write a research story*. It is:

> **Will a real agent developer wire this in, and make a merge or debug
> decision from the report?**

More time polishing paper prose cannot answer that. Only someone else touching
the tool can.

## Split

| | Share |
|---|---:|
| Thin product and integration experience | **60%** |
| Pilot and data | **25%** |
| Paper skeleton, experiment log, related work | **15%** |

**Maintained:** research question, claim boundaries, pre-registration,
experiment log, figure and table placeholders, the related-work matrix.

**Not worth it yet:** polishing the introduction, venue templates, squeezing
for page limits, a full discussion, or designing a narrative around results
that do not exist.

## Order

1. **Close Gate 1** — done (`011f759`). Stop extending the framework.
2. **A vertical slice someone can install**: `init`, `baseline`, `check`
   producing a readable PR report. Shell command, Python callable,
   deterministic evaluator, local artifacts. No adapter zoo.
3. **The $20–30 pilot**, producing the two verdicts frozen data cannot:
   `REGRESSION` and an earned `INSUFFICIENT_EVIDENCE`. **All four verdicts must
   come from real data; none is hand-written.**
4. **Put it in front of 3–5 people**, easiest first: show a report and ask
   whether they could decide a merge from it · ask for a real agent change ·
   integrate it for them · and only last, see whether anyone installs it
   themselves. Step one is asynchronous, so nothing here requires a cold call.
5. **Freeze a formal paper only after external signal**, and only with at
   least two of: the pilot supports the core claim · an unfamiliar developer
   finds the report useful · a public agent integrates end to end · a
   trace-only baseline produces a real false block · the comparability gate
   prevents a real misattribution · RCA localises a known mutation at least
   once.

## Why product-first does not cost the paper

The discipline is already in the code, not in an intention: contracts are
defined in advance, artifacts are frozen with digests, comparability exits
early, outcomes and diagnostics are separated, and a feasibility contract
cannot impersonate a release verdict. Data produced by real use improves the
formal design rather than contaminating it.

The risks of writing the paper first are specific: running a lot of
experiments on features nobody cares about; discovering afterwards that
integration cost forces a different product shape; and producing an RCA that is
statistically correct and useless to act on. Only integration exposes those.

## Time boundary

Four weekends, not open-ended.

| | |
|---|---|
| 1 | resolver + CLI vertical slice — resolver done |
| 2 | pilot, and all four verdicts from real data |
| 3 | public demo, README, a screen recording |
| 4 | 3–5 people: feedback, or integration help |

Then one decision:

| Outcome | Action |
|---|---|
| someone understands it and wants to try | continue the product, widen the paper experiments |
| understood, but nobody installs | fix integration and the GitHub Action |
| installed, but the report changes no decision | **the core value is not established** — change it or stop |
| the pilot does not support the claim | stop extending; **do not rescue it with writing** |

## What the signal is worth

For agent-infrastructure work, the thing to demonstrate is not "I can write a
paper" but: *I found a real reliability problem, designed a falsifiable
experiment, built the system, and someone else used it to solve their problem.*
A tool with rigorous evaluation and an external user is the strongest form of
that; several thin papers with no users is not stronger.

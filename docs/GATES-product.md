# Three gates from here to a downloadable product

**Date:** 2026-09-20. Gate 1 passed. No machine rented.

## The product's opinion, in three rules

Not "we have more metrics" — LangSmith, Braintrust and AgentAssay all have
metrics. The three decision rules are the product:

```
outcome stable + trace changed   → PASS_WITH_DIAGNOSTIC_CHANGE → do not block
serving fingerprint changed      → INCOMPARABLE → rebuild baseline or approve
outcome regression               → trace RCA → localized suspect stage
```

General platforms hand you building blocks. AgentSeism hands you a release
decision that is hard to false-alarm and hard to misattribute.

## Modes

| Mode | Does | Note |
|---|---|---|
| `check` | the daily product: comparable? what regressed? enough evidence? block? where? | the entry point that earns a download |
| `mutate` | tests the **test suite**, not the agent | closer to classical mutation testing; **not the front-page sentence** |
| `diagnose` | reads traces already produced; first outcome-associated separation, tool failure, recovery failure, progress stall, validation omission | **no extra model calls by default**; any fork or intervention shows its estimated cost and is started by the user |

## Gate 1 — may start the vertical slice — **PASSED**

Requires that the *problem* exists, not that the method works.

| Criterion | Evidence |
|---|---|
| harmless trajectory variation false-alarms a trace-only method | four runs all resolved, a composite detector fires on 6/6 pairs |
| a serving-stack change invalidates comparison | Gate 9, 23/23 actions differ with the agent held fixed |
| outcome-first and comparability-first rules are writable | `contracts/default.yaml`, `contract.py` |
| the feature taxonomy is frozen | `FEATURE_TAXONOMY_AND_HYPOTHESES.md`, narrowed by the roadmap |

And the fifth run **did** fail, which is the other half: differences cannot all
be ignored either. Only the outcome separates them.

**So the following may be built now, with no new model calls:** contract
schema, deterministic validator, verdict engine, Markdown PR report, and a demo
on frozen data.

## Gate 2 — may ship a public MVP

A $20–30 pilot. 1 public coding agent · 3 tasks · 3 controlled mutations · 3
trials per condition · cached baseline · results labelled **feasibility only**.

Three classes must appear:

| Case | Success criterion |
|---|---|
| harmful change | ≥2 mutations move their pre-registered primary feature in the expected direction |
| harmless change | ≥1 clear trace shift is **not** called a regression |
| incomparable | a fingerprint mismatch returns `INCOMPARABLE` **before any trial** |

RCA also needs: ≥1 confirmed regression, localised to the component actually
modified, and **not feeding back into the verdict**.

Usability, checked at the same time: the report is legible without ten minutes
of explanation; cost and duration are visible before the run; the contract does
not require understanding statistics; errors and missing data fail closed.

## Gate 3 — may scale the product and write the paper

≥5–8 independent tasks, 3 pre-registered mutations, enough repetition,
scenario-level paired analysis, primary feature and negative control and effect
threshold all frozen in advance, a false-alarm comparison against a
harmless-shift detector, independent validation of the comparability gate, and
**at least one disappointing or null mutation kept under the registered rule**.

Only then: a second agent, framework adapters, adaptive sampling, $100-class
experiments, and whether this is a short paper or a product release.

## MVP boundary

**In:** local-first CLI, shell/Python runner, deterministic evaluator, cached
baseline, repeated comparison, task success + recovery + cost/steps to success,
the four verdicts, serving fingerprint, Markdown/JSON PR report, offline RCA
after a confirmed regression.

**Out:** web dashboard, hosted trace storage, composite score, LLM-judge
marketplace, adaptive sampling, ten adapters, auto-repair, production
monitoring, billing.

## What would stop people downloading it

A complex contract DSL to learn first · uploading production data to try it ·
requiring a cloud subscription · dozens of expensive calls on first run · a
single agent score · a pile of p-values that never says whether to merge · only
supporting our own experimental agent · an RCA that is really just another LLM
summarising a trace.

## Stop conditions — do not rescue these with more trials

- a primary feature cannot separate its expected mutation;
- harmless variation still triggers regression often;
- the comparability rule makes ordinary PRs incomparable;
- RCA produces only generic trace summaries;
- the contract is harder than writing your own eval;
- the report does not change a merge or debug decision.

Each calls for changing the features, the contract or the product boundary.
**More trials on a metric that does not separate buys precision about the wrong
thing.**

## First-phase success, stated in people rather than stars

- 3 unfamiliar developers complete an install;
- ≥2 produce a report on their own agent;
- ≥1 says the report changed a merge or debug decision;
- median integration time ≤ 15 minutes;
- first useful report under $5.

That says more than a few dozen polite stars.

## Pace

> Build the thinnest vertical slice now. After a low-cost pilot passes, invest
> in a downloadable MVP.

Not waiting for the paper; not building a platform before the pilot.

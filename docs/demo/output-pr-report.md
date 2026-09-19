# AgentSeism — pull-request check

> **Format only.** The candidate arm below is illustrative. No baseline/candidate
> comparison has been run, and the planted-regression experiment
> (`DESIGN-ci-stochastic-regression.md` §9) is gated on C2. The baseline column
> is the shape of the real profile in `output-baseline-profile.md`; the candidate
> column is invented to show the report's layout.

```
AgentSeism: SUSPECTED REGRESSION                          [illustrative]

Decision
- Warn. Investigate tool routing before merge.
- Evidence level: suspected — a harmful signal exists, below the
  confirmation threshold. Not "confirmed", and not "safe".

Outcome                                        gate
- final task success   no material change      max_success_rate_drop 0.10   ok
- candidate cost       +31% on 2 tasks         max_cost_increase 0.25       CROSSED
- prohibited behavior  none                    —                            ok

Evidence
- 8 candidate trials across 3 tasks
- 3 independent occurrences of a new behavioural mode
- baseline: 0 occurrences in 18 compatible cached trials
- effective independent histories: 8 (no shared-prefix forks counted)
- stopped at the configured $20 budget

Localization                                   ← diagnosis, not the gate
- first meaningful divergence: tool selection after repository search
- baseline mode:  inspect configuration → edit target file
- candidate mode: call unrelated tool → fail → retry → recover
- localized at, not caused by: no controlled intervention was run

Recommendation
- Warn, do not block. Final success is unchanged; cost and latent failure
  risk are not.
```

## What the layout is committing to

**The decision comes before the analysis.** A reviewer reads one line and knows
whether to merge.

**Outcome and diagnosis are separated on the page**, because they have different
standing. The gate is decided by the outcome block alone. The localization block
explains where to look and is never the reason a merge is blocked.

**"Localized at", never "caused by".** Causal language requires a controlled
intervention or ablation reproducing the outcome change. The report says which
it has.

**An exhausted budget is neutral, never a silent pass.** "We ran out of money"
and "we found nothing" are different findings, and conflating them is how a CI
check becomes theatre.

**Effective independent histories are reported, not trial count.** Shared-prefix
forks are useful for intervention analysis and are not independent evidence; a
report that counts them as samples inflates its own confidence.

## The line this report cannot yet write

Whether "investigate before merge" can become "here is the earliest point where
intervention would still have helped" depends on C2. If divergence is
unrecoverable by the time it is detectable, the Localization block stays
diagnostic and the product promises no repair. See `RUNBOOK-c2.md` §7.

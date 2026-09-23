# Postmortem — the pilot that never ran a cell

**2026-09-23.** Five hosts, `$9.72`, `pilot_runs = 0`, no pilot evidence.
The registered pilot closed as `infrastructure_feasibility_stop_before_run_0`.

## The root cause

> **The tests verified components. Nothing verified the entry point.**

Every gate added over five hosts checked a *part* of the chain, and each was
added after a host had already paid to find the part it checked. The one thing
never tested was the path the experiment would actually take:
`agentseism.pilot --backend real`.

The smoke test — the gate designed to prove the chain end to end — called
`run_cell` **directly**. So it exercised the backend while leaving the public
entry point untouched. A passing smoke and an unrunnable pilot were therefore
perfectly compatible, and on Host 5 that is exactly what happened: every
criterion green, `READY_FOR_MANUAL_PILOT_CONFIRMATION`, and a `SystemExit`
placeholder still sitting in `main`.

## What each host cost to discover

| host | defect | where the test was | $ |
|---|---|---|---|
| 2 | no runner existed at all | constructibility gate, added after | 2.99 |
| 3 | bare model id reached LiteLLM | transport check, added after | 2.12 |
| 4 | cost accounting discarded a successful response | success-path test, added after | 1.56 |
| 5 | entry point never wired to the backend | **nothing checked this** | 3.05 |

All four were reachable offline. None needed a GPU.

## The secondary finding: solved problems not inherited

Two of the four were mechanisms this project had already built and verified,
which the pilot reimplemented or omitted:

- `MSWEA_COST_TRACKING=ignore_errors` — registered in two preregs, set by
  three runners, set by neither pilot component.
- `c2h_checker.label_from_report` — verified 20/20 offline; the pilot wrote a
  second parser against the wrong file, and the two disagreed on real data.

A component library does not protect a new caller that does not use it.

## The third pattern: fixtures owning state they don't own

Four test-side defects, each initially resembling a product bug: a driver
constant rewritten by a blunt numeric replace; an environment leak-check that
demanded a variable be absent when the host exports it deliberately; a mock
carrying its own copy of a frozen count; and a probe globbing for the newest
file on disk instead of its own. None were product defects. All were tests
reaching for state belonging to something else.

## What actually worked

The stopping machinery. Every host stopped *before* producing contaminated
data: no `RESOLVED_FALSE` from a broken chain, no checkpoint authorised by a
stale reading, no budget baseline reset by a new machine, no verdict from an
unbound session. Two checkpoints were superseded with reasons and the
originals left intact. The registered rules were honoured against their own
letter — P.10 would have permitted a sixth host, and it was not used.

The cost of that discipline was five hosts and `$9.72`. The benefit is that
there is no bad data to retract.

## The correction

A test now drives one registered block through `pilot.main()` against real
containers and the real SWE-bench evaluator, and asserts it stops at the next
block boundary. That is the check whose absence defines this postmortem.

**The general lesson is not "add another gate".** Four gates were added and the
fifth defect still slipped past, because every one of them tested a component.
The rule that would have caught all five:

> Test the entry point the experiment will use, on the smallest real unit it
> can run, before spending anything on hardware.

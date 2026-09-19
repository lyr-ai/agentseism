# AgentSeism demo — inputs and outputs

What a user hands AgentSeism and what it hands back. The point is to **fix the
interface** before any of it is implemented, so the shape survives whichever way
C2 goes (`docs/RUNBOOK-c2.md` §7).

Two samples, and the difference between them matters:

| File | Status |
|---|---|
| `output-baseline-profile.md` | **Real.** Every number computed from frozen trajectories in `data/runs/h2_phase_a1/`. |
| `output-pr-report.md` | **Format only.** The candidate arm is illustrative; no such comparison has been run. Labelled as such in the file. |

Nothing here is evidence. `output-baseline-profile.md` reports real measurements
of a real agent; it does not demonstrate a detected regression, because no
regression experiment has been run. The planted-regression experiment
(`DESIGN-ci-stochastic-regression.md` §9) is gated on C2.

## Files

```
input-config.yaml            what the user commits to their repo
input-trace-record.json      one normalized event, annotated against the schema
output-baseline-profile.md   what AgentSeism emits when it profiles a baseline
output-pr-report.md          what it emits on a pull request (format only)
```

## The one design commitment these samples encode

> **Trajectory difference never gates a merge. Only a consequential outcome
> regression does, and trajectories are then used to localise it.**

`output-baseline-profile.md` is what makes that commitment necessary rather than
cautious: five independent runs of one agent on one task at temperature zero
produced five different final repository states, and all five were accepted. An
agent that gates on trajectory identity would block every one of them.

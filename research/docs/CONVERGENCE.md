# What changed, and what did not

**2026-09-20.** A convergence, not a new project.

The problem never moved:

> Agent behaviour is stochastic. After a change to code, prompt, tools or the
> runtime, how does a developer tell whether it actually got worse, and find
> out why?

What moved is the starting point: **from the trajectory, to the engineering
decision.**

| | Before | Now |
|---|---|---|
| Product entry | find where trajectories fork | decide whether a PR regressed a capability |
| Research object | nodes, trajectory difference, recoverability | feature outcomes, comparability, false alarms |
| Intervention | fork and continue at an arbitrary horizon | real engineering mutations |
| Gate | trajectory divergence, likely | outcome-grounded features only |
| Trace | the primary signal | a diagnostic signal, after a confirmed regression |
| Environment change | an experimental variable or a limitation | checked first; incompatible → `INCOMPARABLE` |
| RCA | find the critical node | explain a confirmed baseline/candidate outcome delta |
| User question | why did it fork here? | can I merge this, and what broke? |

## What carries over

Normalized traces · baseline/candidate repeated runs · stochastic variation
measurement · outcome evaluators · artifact freezing with digests · the budget
state machine · the serving fingerprint · the comparability gate · conditional
RCA · the fork and intervention machinery · and the evidence from C2 and
Gate 9.

Two former obstacles became the two product rules:

**Gate 9** was an environment failure that blocked C2. It is now the first
rule: *when the execution stack changes, two batches may not be comparable, and
the difference must not be attributed to an agent revision.*

**Phase A's four correct but different results** became the second: *a
different trajectory is not a worse outcome.* And the fifth run, which really
did fail, is why the rule is outcome-grounded rather than simply permissive.

The earlier experiments were not discarded. They are what tells the product how
to judge.

## What was actually dropped

- arbitrary fork horizons as the product entry point;
- the recoverability curve as the core value;
- searching for important nodes without a target;
- trace divergence as a merge gate;
- claiming the mutation suite, SPRT or the feature scorecard as the paper's
  main novelty;
- spending the next compute budget on C2-H first.

They remain available as internal apparatus or a future RCA backend. They no
longer decide the direction.

## Why the change is healthy

Not a failed experiment repackaged. Three pieces of evidence, two of them ours,
forced the narrowing:

1. **AgentAssay** already covers broad stochastic regression testing,
   mutations, adaptive budget and fingerprinting.
2. **Four of five diverse trajectories were correct**, so trajectory
   consistency punishes correct execution.
3. **Gate 9's 0/23** shows comparability has to be decided before regression.

Together they point at a sharper question than the one we started with:

> When agent behaviour changes, how do we separate harmful regression,
> harmless change, insufficient evidence, and an incomparable environment?

## In one line

The users and the pain did not move. The wedge moved — from trajectory
forensics to a PR regression decision. RCA did not disappear; it became the
module that runs *after* a confirmed regression. The paper thesis moved from
recoverability and critical nodes to outcome grounding and comparability.

The name still fits. **AgentSeism no longer reads every tremor as damage** — it
tells ordinary movement, real damage, and a moved instrument apart.

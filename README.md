> This repository is part of the **[Reliable Long-Running Agents (RLRA)](https://github.com/canis-minor)** research initiative.

# AgentSeism

**Behavioral weak-point discovery for LLM agents.**

> **Boundary.** AgentSeism measures where behavior varies and what that variation
> is associated with. It does not decide whether an outcome is correct.

![status: research prototype](https://img.shields.io/badge/status-research%20prototype-orange)

> Siblings in the RLRA stack —
> [TypedMem](https://github.com/canis-minor/typedmem) ·
> [AgentCheck](https://github.com/canis-minor/agentcheck) ·
> [AgentTrace](https://github.com/canis-minor/agenttrace) ·
> [ReliAgent Bench](https://github.com/canis-minor/reliagent-bench) ·
> [AgentLab](https://github.com/canis-minor/agentlab) ·
> **AgentSeism**

AgentSeism projects heterogeneous agent executions into comparable **execution
features**, then measures which feature variations are most strongly associated
with downstream behavioral variation.

The question is not *did my agent fail?* and not *are two outputs different?*
It is:

```text
Where did behavioral variation emerge inside the execution,
how did it propagate,
and which execution points actually matter to the outcome?
```

## The problem

The same agent, on the same task, run twice:

```text
Run 1   Input → Evidence A → Hypothesis X → Tool 1 → Outcome X
Run 2   Input → Evidence B → Hypothesis Y → Tool 2 → Outcome Y
```

Observability shows both traces. Evaluation says whether each outcome passes.
Neither answers the engineering question: **which internal difference was
behaviorally consequential?** A trace contains many differences; most do not
matter.

## Quickstart

```python
from agentseism import scan
from agents.trajectory import ReActProjector

def my_agent(task, trace):
    # record the raw execution; the projector turns it into features
    ...

report = scan(
    my_agent,
    cases=["why is checkout slow?", "why did auth fail?"],
    trials=10,
    outcome=lambda r: r["answer"],
    projector=ReActProjector(),
)
print(report)
```

The `trace` parameter is optional. Without it you still get outcome-level
variation; with it, the raw trace is projected into the adapter's declared
feature schema and those features are ranked.

```text
Top Behavioral Weak Points   (score = V x A)
──────────────────────────────────────────────

1. Execution feature: tool_set

   Local variation           0.47
   Outcome association       0.87

   Weak-point score          0.41

   Feature family with: tool_sequence
   These co-vary; count them as one finding, not several.

Excluded from attribution: final_answer (declared outcome, not a step toward it).
Feature schema: react/1
```

**High variation ≠ high weakness.** A feature that changes on every run but never
reaches the outcome scores near zero — that is what the negative-control feature
(`pre_final_reasoning`) is there to verify.

## How it works

```text
agent → repeated runs → raw trace → adapter projection → execution features
      → feature variation → outcome association → ranked weak points
```

Raw event occurrence is not a cross-run identity: a ReAct agent's third model
call means something different in every run. So AgentSeism ranks **declared
execution features**, not raw events (DESIGN-FEATURE-PROJECTION.md):

```text
unordered schema   W = LocalVariation × OutcomeAssociation
ordered schema     W = LocalVariation × OutcomeAssociation × Propagation
```

Propagation is scored only when the adapter declares feature order. An unordered
schema gets no propagation term rather than an invented one, and the report
states which mode produced the score.

This is **weak-point localization, not causal attribution**. A high score says a
feature's variation co-varies with outcome variation — not that intervening
there would change the outcome.

## Validating the attribution

`agents/synthetic.py` is a controllable agent with exactly one injected
consequential weak point, plus two decoy points that vary heavily and reach
nothing. The label is hidden from every ranker:

```bash
python experiments/attribution/ground_truth.py
```

```text
Table 1 — Ground-truth attribution (40 injected weak points)

Method                 Attribution@1   Attribution@3
----------------------------------------------------
agentseism                      1.00            1.00
random                          0.00            0.50
first_divergence                0.17            0.25
largest_diff                    0.00            1.00
correlation                     0.80            1.00
```

Read this as a harness check, not a research result: the synthetic agent is easy
by construction, and correlation alone already reaches 0.80@1 on it. The number
that matters comes from real agents with injected interventions (Week 5).

## First agent: GAIA-style LangGraph agent

```bash
# offline plumbing check -- no API keys, not evidence for anything
python experiments/natural_variation/gaia_pilot.py --stub

# the real pilot: 10 tasks x 5 runs against your compiled LangGraph app
python experiments/natural_variation/gaia_pilot.py --app my_module:app
```

The pilot answers three questions before the full 50 x 10 slice is worth paying
for: do traces come back complete, does the answer vary at all, and does the
projection keep the trajectory? It prints an explicit go/no-go verdict.

Pieces involved:

| file | what it does |
|---|---|
| `agents/langgraph_adapter.py` | wraps any compiled LangGraph app; duck-typed, no langchain import |
| `agents/trajectory.py` | records the raw ReAct trace, and projects it into the §8 feature schema |
| `agents/gaia.py` | GAIA state, answer extraction, formatting-insensitive answer equivalence |
| `benchmarks/gaia.py` | Level-1 slice spec (task ids only — GAIA is gated, so no data is vendored) |

**ReAct loops are not fixed workflows.** One run takes three iterations, another
takes seven, so occurrence-index alignment would pair a run's third model call
with another run's detour. AgentSeism projects instead: `tool_set`,
`tool_sequence`, `tool_call_count`, `evidence_set`, `initial_plan`,
`pre_final_reasoning`. Loop length becomes behavior rather than missing data,
and `tool_set` separates *which capabilities* from *which path*. The full raw
trace is still stored, untruncated, for the intervention work in V1.

**The comparator is not a grader.** Two runs that are identically wrong are
behaviorally consistent, and AgentSeism says so. Correctness against the GAIA
reference answer is recorded separately, as context.

## Known limitations (V0)

- **Propagated variation looks like source variation.** A point downstream of the
  real weak point inherits high propagation and outcome association. Separating
  source from consequence needs intervention, not association.
- **Features are hand-defined and frozen per adapter version.** Automatic
  feature discovery is out of scope for V0; schemas must be fixed before
  outcomes are examined, and results from different schema versions are never
  mixed.
- **Correlated features are one finding.** `tool_set`, `tool_sequence` and
  `tool_call_count` often reflect the same underlying change, so the report
  groups them into a feature family instead of claiming three findings.
- **No semantic comparator by default.** Text similarity is token overlap; pass
  your own comparator for anything that needs meaning.
- **The correlation baseline may already be enough.** On an unordered schema the
  score is correlation re-weighted by local variation, so it can rank exactly
  like correlation-only. The pilot checks for this and says so out loud; if it
  holds on real agents, the next method needs intervention, not a better
  weighting (DESIGN-FEATURE-PROJECTION.md §22).

## Layout

```text
src/agentseism/
  runner/        repeated execution + local persistence
  trace/         optional instrumentation
  alignment/     event correspondence across runs
  variation/     outcome- and event-level variation
  attribution/   weak-point ranking + baselines
  metrics/       comparators
agents/          agent adapters (synthetic ground-truth agent today)
experiments/     natural_variation · perturbation · attribution · mitigation
paper/           claims, experiment log, figures
```

## Status

Research prototype, pre-v0.1. The six-week go/no-go plan and explicit success
criteria are in [DESIGN.md](DESIGN.md) §24-25 — including the conditions under
which this project should be stopped.

## Install

```bash
pip install -e ".[dev]"
pytest
```

## License

Apache-2.0

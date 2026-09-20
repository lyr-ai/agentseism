> This repository is part of the **[Reliable Long-Running Agents (RLRA)](https://github.com/canis-minor)** research initiative.

# AgentSeism

**Did this PR make the agent worse — and if so, where?**

> **What it decides.** Outcomes gate a merge. Traces explain a regression after
> one is confirmed. When the execution environment changed, the two sides are
> not compared at all.

![status: research prototype](https://img.shields.io/badge/status-research%20prototype-orange)

> Siblings in the RLRA stack —
> [TypedMem](https://github.com/canis-minor/typedmem) ·
> [AgentCheck](https://github.com/canis-minor/agentcheck) ·
> [AgentTrace](https://github.com/canis-minor/agenttrace) ·
> [ReliAgent Bench](https://github.com/canis-minor/reliagent-bench) ·
> [AgentLab](https://github.com/canis-minor/agentlab) ·
> **AgentSeism**

Agents are stochastic. The same agent, unchanged, produces a different
trajectory almost every run — so "the behaviour changed" is the baseline
condition, not a finding. AgentSeism decides which changes matter:

| Observation | Verdict |
|---|---|
| outcome dropped, environments comparable | `REGRESSION` — and only now, RCA |
| trace moved, outcome held | `PASS_WITH_CHANGE` — do not block |
| serving fingerprint changed | `INCOMPARABLE` — zero trials spent |
| evidence too thin to say | `INSUFFICIENT_EVIDENCE` — not a pass |

Two of those verdicts are demonstrated on frozen data in this repository, with
no model calls:

- [`docs/demo/pr-report-pass-with-change.md`](docs/demo/pr-report-pass-with-change.md)
  — four independent runs of one task, **all four resolved the issue**, and a
  composite trace detector still fires on **6 of 6** pairs.
- [`docs/demo/pr-report-incomparable.md`](docs/demo/pr-report-incomparable.md)
  — the agent held completely fixed, only the GPU and driver changed, and
  **23 of 23** structured actions differ.

`REGRESSION` and `INSUFFICIENT_EVIDENCE` are not demonstrated yet; they need
the pilot, and inventing them would demonstrate the report rather than the
method.

## Quick start

Three lines per capability. You name the threshold; the tool names the
statistics and prints every one of them in the report.

```yaml
# .agentseism/contract.yaml
runner:
  command: "{python} run_agent.py --task {task_file}"
features:
  task_success:     {gate: true,    regression_threshold: 0.10}
  recovery_success: {gate: true,    regression_threshold: 0.15}
  cost_per_success: {gate: warning, regression_threshold: 0.25}
```

That resolves to a complete, auditable contract —
[`contracts/example-resolved.md`](contracts/example-resolved.md) — which is
what gets hashed and reported. Defaults are versioned, so upgrading the tool
cannot make a differently-resolved contract look like the same one.

**Direction:** see [`docs/CONVERGENCE.md`](docs/CONVERGENCE.md) for why this is
narrower than the repository's earlier framing, and what the earlier
experiments contributed to it.

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
positioned feature     W = LocalVariation × OutcomeAssociation × Propagation
trajectory aggregate   W = LocalVariation × OutcomeAssociation
```

Adapters declare execution precedence as a partial order — a DAG, not a total
ordering. A ReAct agent's plan really does precede the evidence it gathers,
which precedes the reasoning before submission; its tool set, tool sequence and
call count are whole-trajectory aggregates with no position at all. Aggregates
get `propagation = None`, printed as `N/A`, never a silent 0 or 1, and the two
groups are ranked separately because their scores are not comparable.

This is **weak-point localization, not causal attribution**. A high score says a
feature's variation co-varies with outcome variation — not that intervening
there would change the outcome. Separating an introduced variation from an
inherited one is what [`DESIGN-INTERVENTION.md`](DESIGN-INTERVENTION.md) is for.

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

## First agent: a multi-node GAIA LangGraph agent

Target: [MarkAZhang/gaia-agent](https://github.com/MarkAZhang/gaia-agent) —
LangGraph, multi-node, 41/53 on GAIA Level 1 validation. Setup, keys, cost and
the exact commands are in [`docs/RUNBOOK-gaia-pilot.md`](docs/RUNBOOK-gaia-pilot.md).

```bash
# offline plumbing check -- no API keys, not evidence for anything
python experiments/natural_variation/gaia_pilot.py --stub

# the real pilot: 10 tasks x 5 runs (~$30 at that agent's reported $0.61/run)
python experiments/natural_variation/gaia_pilot.py \
    --app agentseism_entry:app --system-prompt agentseism_entry:build_system_prompt
```

**That agent trims its own history.** Its `memory_management` node overwrites
earlier tool results with `"removed"`, so reading the trajectory from the final
state would report almost no evidence gathered. The adapter captures the node
update stream instead, and refuses to project a final-state-only trace.

The pilot answers three questions before the full 50 x 10 slice is worth paying
for: do traces come back complete, does the answer vary at all, and does the
projection keep the trajectory? It prints an explicit go/no-go verdict.

Pieces involved:

| file | what it does |
|---|---|
| `agents/langgraph_adapter.py` | wraps any compiled LangGraph app; duck-typed, no langchain import |
| `agents/trajectory.py` | records the raw ReAct trace, and projects it into the §8 feature schema |
| `agents/gaia.py` | GAIA state, answer extraction, formatting-insensitive answer equivalence |
| `agents/gaia_markazhang.py` | the multi-node graph's feature schema: evidence, retries, termination |
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
- **The correlation baseline may already be enough.** For aggregates the score
  is correlation re-weighted by local variation, and even with a propagation
  term the ranking can match correlation-only. The pilot checks this within each
  scoring group and says so out loud. If it holds on real agents, the answer is
  intervention, not another factor in the product
  (DESIGN-FEATURE-PROJECTION.md §22).

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

Research prototype, pre-v0.1. V0 is a **localization heuristic** that produces
candidate weak points; the intervention contract that turns candidates into
causal claims is specified in
[`DESIGN-INTERVENTION.md`](DESIGN-INTERVENTION.md) and not yet implemented. The six-week go/no-go plan and explicit success
criteria are in [DESIGN.md](DESIGN.md) §24-25 — including the conditions under
which this project should be stopped.

## Install

```bash
pip install -e ".[dev]"
pytest
```

## License

Apache-2.0

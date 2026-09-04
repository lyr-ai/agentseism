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

AgentSeism discovers **where small variations are amplified inside LLM-agent
executions**, and ranks the execution points most associated with downstream
behavioral variation.

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

def my_agent(task, trace):
    docs = trace.record("retrieval", "retrieval", input=task, output=search(task))
    evidence = trace.record("decision", "evidence_selection", input=docs, output=pick(docs))
    answer = trace.record("model_call", "answer", input=evidence, output=generate(evidence))
    return {"answer": answer}

report = scan(
    my_agent,
    cases=["why is checkout slow?", "why did auth fail?"],
    trials=10,
    outcome=lambda r: r["answer"],
)
print(report)
```

The `trace` parameter is optional. Without it you still get outcome-level
variation; with it you get event-level weak-point attribution.

```text
AgentSeism
══════════════════════════════════════

Agent: synthetic

Tasks                       20
Executions                 200

Behavioral consistency
                           72%

High-variation tasks
                            11

Top Behavioral Weak Points
──────────────────────────────────────

1. Event group: evidence_selection

   Local variation           0.19
   Downstream propagation    1.00
   Outcome association       1.00

   Weak-point score          0.19
```

**High variation ≠ high weakness.** An execution point whose output changes on
every run but never reaches the outcome scores near zero.

## How it works

```text
agent → repeated runs → trace → run alignment → event-level variation
      → propagation + outcome association → ranked weak points
```

The V0 weak-point score is deliberately simple (DESIGN.md §14):

```text
W(e) = LocalVariation(e) × Propagation(e) × OutcomeAssociation(e)
```

This is **association-based attribution, not causal attribution**. A high score
says variation at that point co-varies with downstream and outcome variation —
not that intervening there would change the outcome.

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
| `agents/trajectory.py` | projects a variable-length ReAct loop onto alignable execution points |
| `agents/gaia.py` | GAIA state, answer extraction, formatting-insensitive answer equivalence |
| `benchmarks/gaia.py` | Level-1 slice spec (task ids only — GAIA is gated, so no data is vendored) |

**ReAct loops are not fixed workflows.** One run takes three iterations, another
takes seven, so occurrence-index alignment would pair a run's third model call
with another run's detour. V0 aligns a projection instead — `tool_sequence`,
`tool_set`, `evidence`, `n_steps` and the first K iterations — which keeps
trajectory length visible as behavior rather than as missing data
(DESIGN.md §11.1). Iterations past the window are counted and reported.

**The comparator is not a grader.** Two runs that are identically wrong are
behaviorally consistent, and AgentSeism says so. Correctness against the GAIA
reference answer is recorded separately, as context.

## Known limitations (V0)

- **Propagated variation looks like source variation.** A point downstream of the
  real weak point inherits high propagation and outcome association. Separating
  source from consequence needs intervention, not association.
- **Alignment is name-and-position based.** Agents whose execution points are not
  stably labelled are out of scope for V0 (DESIGN.md §11).
- **No semantic comparator by default.** Text similarity is token overlap; pass
  your own comparator for anything that needs meaning.
- **One comparator for every execution point.** A tool name, a retrieved
  document and a step count are compared by the same rule today; per-slot
  comparators are a known gap.
- **The outcome must be excluded by hand.** A recorded point that *is* the
  outcome has an association of 1.0 by construction, so pass
  `exclude_slots=("final_answer",)` — the report states what was excluded.

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

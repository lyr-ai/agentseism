# Roadmap

Six weeks, four decision points. Full rationale in [DESIGN.md](DESIGN.md) §24-25.

## Week 1 — One agent · Figure 1

Agent #1 is a GAIA-style LangGraph agent: multi-step, tool-using, cheap to
attach, and the outcome is a single final answer.

- [x] Experiment runner, trace collection, outcome extraction, local persistence
- [x] Outcome variation (`C_t`, `V_t`, outcome modes)
- [x] LangGraph adapter + feature projection for variable-length ReAct loops
- [x] Feature model: roles, per-feature comparators, schema freeze, families
- [x] GAIA answer-equivalence comparator (formatting-insensitive, not a grader)
- [x] Task slice spec: Level 1, no attachments, sorted by `task_id`
- [x] Pilot harness with go/no-go checks (`experiments/natural_variation/gaia_pilot.py`)
- [ ] Run the pilot against a real agent: 10 tasks × 5 runs (§25 checks)
- [ ] If the pilot passes: 50 tasks × 10 trials → Figure 1

**Pilot before scale-up:** the 10 × 5 pilot exists to find out whether traces
come back complete, whether the answer varies at all, and whether the projection
keeps the trajectory — before paying for 500 executions.

## Week 2 — Generality · answer RQ1

Agent #2 is structurally different on purpose: an environment-interacting web
agent (AgentLab / WorkArena) rather than a general tool-use assistant. If both
show weak-point concentration, RQ1/RQ2 generality gets much stronger.

- [ ] A second, structurally different agent
- [ ] Repeat the natural-variation experiment

**Stop condition:** if neither agent shows meaningful variation, stop.

## Week 3 — Execution analysis · Figure 2

- [x] Feature-name alignment, with missingness as observable difference
- [x] Feature-level variation table
- [ ] Is consequential variation concentrated, or spread evenly? (RQ2)

**Stop condition:** if variation is uniformly distributed, the thesis is wrong.

Later agents, in order, each with a stated scientific purpose: m&ms (reference
plans make plan/tool-selection variation directly measurable), WebArena (heavy
environment, for paper strengthening), a coding agent (external validity, only
once there is a result to strengthen).

## Week 4 — Controlled perturbation · Figure 3

- [ ] `paraphrase`, `context_order` — two transformations, no catalogue
- [ ] Where does a known input variation get amplified?

## Week 5 — Attribution · Table 1

- [x] Weak-point ranking, with propagation only on ordered schemas
- [x] Baselines: random, first-divergence, largest-diff, correlation
- [x] Ground-truth harness with injected weak points (`experiments/attribution/`)
- [x] Tie-aware Attribution@k (expected credit under a random tie-break)
- [ ] LLM-debugger baseline
- [ ] Attribution@1 / @3 on real agents with injected interventions

**Planned falsification test:** if correlation-only matches AgentSeism on real
agents, the score is not a contribution and the next method must introduce
controlled intervention or counterfactual replay.

## Week 6 — Actionability · Figure 4

- [ ] Manual mitigation of top-ranked weak points
- [ ] Held-out evaluation: variation, quality, cost, latency

## Deliberately postponed

Automatic perturbation discovery · automatic mitigation · pytest and CI
integration · polished CLI · HTML reports · LangSmith and OpenTelemetry adapters
· cloud execution · team features · telemetry.

Also postponed, and tracked as known limitations: automatic feature discovery,
and separating a weak point from the features that merely inherit its variation
— that needs intervention, not association.

Each is downstream of the same bet: that consequential variation is concentrated
and attributable. No feature enters V0 unless a weekly deliverable requires it.

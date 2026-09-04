# Roadmap

Six weeks, four decision points. Full rationale in [DESIGN.md](DESIGN.md) §24-25.

## Week 1 — One agent · Figure 1

- [x] Experiment runner, trace collection, outcome extraction, local persistence
- [x] Outcome variation (`C_t`, `V_t`, outcome modes)
- [ ] One public multi-step LLM agent adapter in `agents/`
- [ ] 50 tasks × 10 trials → distribution of run-to-run behavioral variation

## Week 2 — Generality · answer RQ1

- [ ] A second, structurally different agent
- [ ] Repeat the natural-variation experiment

**Stop condition:** if neither agent shows meaningful variation, stop.

## Week 3 — Execution analysis · Figure 2

- [x] Run alignment (name + occurrence)
- [x] Event-level variation table
- [ ] Is consequential variation concentrated, or spread evenly? (RQ2)

**Stop condition:** if variation is uniformly distributed, the thesis is wrong.

## Week 4 — Controlled perturbation · Figure 3

- [ ] `paraphrase`, `context_order` — two transformations, no catalogue
- [ ] Where does a known input variation get amplified?

## Week 5 — Attribution · Table 1

- [x] Weak-point ranking (local × propagation × outcome association)
- [x] Baselines: random, first-divergence, largest-diff, correlation
- [x] Ground-truth harness with injected weak points (`experiments/attribution/`)
- [ ] LLM-debugger baseline
- [ ] Attribution@1 / @3 on real agents with injected interventions

## Week 6 — Actionability · Figure 4

- [ ] Manual mitigation of top-ranked weak points
- [ ] Held-out evaluation: variation, quality, cost, latency

## Deliberately postponed

Automatic perturbation discovery · automatic mitigation · pytest and CI
integration · polished CLI · HTML reports · LangSmith and OpenTelemetry adapters
· cloud execution · team features · telemetry.

Each is downstream of the same bet: that consequential variation is concentrated
and attributable. No feature enters V0 unless a weekly deliverable requires it.

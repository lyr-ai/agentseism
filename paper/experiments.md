# Experiment log

Append-only. One entry per run that produced a number anyone might cite.

Template:

```text
## YYYY-MM-DD — <name>

Agent:          <agent + version/config>
Tasks:          <n, source>
Trials:         <n>
Comparator:     <outcome comparator>
Command:        <exact command>
Artifact:       results/<file>.json

Result:         <the number(s)>
Reading:        <what it does and does not support>
```

---

## 2026-09-03 — attribution harness check (synthetic)

Agent:          `agents/synthetic.py`, 4 injection sites × 10 seeds
Tasks:          4
Trials:         8
Comparator:     exact (outcome), structured (events)
Command:        `python experiments/attribution/ground_truth.py`
Artifact:       `results/attribution_ground_truth.json`

Result:         AgentSeism 1.00 @1 / 1.00 @3; correlation 0.80 / 1.00;
                first-divergence 0.17 / 0.25; largest-diff 0.00 / 1.00;
                random 0.00 / 0.50

Reading:        The harness and the baselines run end to end, and the two naive
                trace-diff heuristics are demonstrably fooled by decoy points.
                This says nothing about real agents: the synthetic agent has one
                injected source by construction, and correlation alone nearly
                solves it. Supports no hypothesis in `claims.md`.

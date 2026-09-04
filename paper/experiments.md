# Experiment log

Append-only. One entry per run that produced a number anyone might cite.

Template:

```text
## YYYY-MM-DD — <name>

Agent:          <agent + version/config>
Tasks:          <n, source>
Trials:         <n>
Comparator:     <outcome comparator>
Schema:         <adapter_version / feature_schema_version>
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

---

## 2026-09-03 — attribution harness, feature-projection model (synthetic)

Agent:          `agents/synthetic.py`, 4 injection sites × 10 seeds
Tasks:          4
Trials:         8
Comparator:     exact (outcome); per-feature comparators from the schema
Schema:         synthetic/1, ordered → scoring mode V × A × P
Command:        `python experiments/attribution/ground_truth.py`
Artifact:       `results/attribution_ground_truth.json`

Result:         AgentSeism 1.00 @1 / 1.00 @3; correlation 0.46 / 0.93;
                random 0.17 / 0.50; first-divergence 0.17 / 0.50;
                largest-diff 0.00 / 1.00

Reading:        Rerun of the earlier harness check under the v0.2 model, with two
                corrections that changed the numbers: the declared outcome
                observation is now rejected from every method's candidate set,
                and Attribution@k is scored as expected credit under a random
                tie-break instead of alphabetical order. Correlation-only moved
                from 0.80 to 0.46 @1 as a result — the earlier 0.80 was partly an
                artifact of the outcome observation being rankable. Still a
                synthetic agent with one injected source by construction;
                supports no hypothesis in `claims.md`.

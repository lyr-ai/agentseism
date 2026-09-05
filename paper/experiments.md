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

---

## 2026-09-03 — partial-order rerun (synthetic) + stub §22 check

Agent:          `agents/synthetic.py` (4 injection sites × 10 seeds); stub ReAct
Tasks:          4 / 10
Trials:         8 / 5
Comparator:     exact (outcome); per-feature comparators from the schema
Schema:         synthetic/1 (all features positioned); react/1 (3 positioned + 3 aggregates)
Command:        `python experiments/attribution/ground_truth.py`;
                `python experiments/natural_variation/gaia_pilot.py --stub`
Artifact:       `results/attribution_ground_truth.json`, `results/gaia_pilot_stub_react.json`

Result:         Ground truth unchanged by the switch from total order to declared
                precedence: AgentSeism 1.00 @1, correlation 0.46 @1.
                On the stub ReAct agent, correlation-only reproduces the AgentSeism
                ranking in **both** scoring groups.

Reading:        Partial order did not dissolve the §22 risk, and was not expected
                to. Where the score beats correlation (synthetic), the margin comes
                from the propagation term over a real precedence chain plus local
                variation; where the schema is thin (stub ReAct), correlation is
                already sufficient. The stub is not evidence about real agents
                either way. The structural point stands: a propagation factor
                cannot answer "introduced or inherited?" — intervention can.

---

## 2026-09-04 — pilot instrumentation check (real graph, pre-pilot)

Agent:          `MarkAZhang/gaia-agent` @ `b53f536`, via `agentseism_entry:app`
Tasks:          1 (first of the frozen pilot slice, `0383a3ee`)
Trials:         2 under `gaia-mz/1`, then 3 under `gaia-mz/2`
Comparator:     exact (outcome); per-feature comparators from the schema
Schema:         `gaia-mz/1` rejected; `gaia-mz/2` adopted
Command:        `python experiments/natural_variation/gaia_pilot.py --app agentseism_entry:app
                --system-prompt agentseism_entry:build_system_prompt
                --config agentseism_entry:config --tasks 1 --trials 3`
Artifact:       `results/gaia_pilot_agentseism_entry_app.json`

Result:         Runs completed 100%; all 3 runs answered `Rockhopper penguin`,
                matching the reference. Under `gaia-mz/1`, evidence similarity
                between any two runs was 0.0 and could not have been anything
                else: the search provider stamps a per-call `request_id` UUID, a
                `response_time` float, and a per-result `id` into every response,
                and `evidence_set` compared that serialization directly. Two runs
                retrieving byte-identical documents scored 0.0, exactly as two
                runs retrieving disjoint documents did. Under `gaia-mz/2`, which
                compares canonicalized evidence content, the same synthetic pair
                scores 1.00 and the three real runs score 0.333 pairwise.

Reading:        `gaia-mz/1` is invalid for any experiment, not merely noisy:
                `evidence_set` had zero discriminating power, and as a positioned
                feature its guaranteed divergence would have propagated into the
                ranking as if it were behavior. It was rejected during the §5
                instrumentation check, before pilot data was collected, so no
                number from it has been cited. This is an instrumentation
                correction, not feature engineering against an outcome: the
                feature failed its own definition, which was checked before the
                numbers were read.

                Supports no hypothesis in `claims.md`. One task and three trials
                is a plumbing check; the identical outcome across runs says
                nothing about whether this agent varies.

Open:           `evidence_set` is keyed on canonical URL *and* normalized content,
                so the same document returned with a different snippet counts as
                different evidence. On these 3 runs that reads 0.333 for every
                pair, while URL-only identity separates them (0.500 / 0.875 /
                0.556). Whether provider snippet jitter is evidence variation or
                environment noise is unresolved, and 3 runs is too few to decide.
                Left as-is for the pilot rather than re-tuned against 3 numbers.

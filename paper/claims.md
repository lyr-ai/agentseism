# Claims

Hypotheses, not findings. Nothing here may be written as a fact until the
corresponding experiment has been run and recorded in `experiments.md`.

| # | Hypothesis | RQ | Evidence | Status |
|---|------------|----|----------|--------|
| A | LLM-agent behavioral variation is substantial even when conventional task quality remains acceptable | RQ1 | Figure 1 | not started |
| B | Consequential variation is concentrated rather than uniformly distributed across execution | RQ2 | Figure 2 | not started |
| C | Execution-feature variation analysis localizes consequential weak points better than trace-diff baselines | RQ3 | Table 1 | harness only (synthetic) |
| D | Weak-point-guided intervention improves robustness on held-out tasks without degrading quality | RQ4 | Figure 4 | not started |

## Status vocabulary

- **not started** — no experiment run
- **harness only** — the measurement pipeline runs, on synthetic data
- **preliminary** — real agents, one configuration
- **supported / refuted** — replicated across agents and seeds

## Standing caveats

1. **Localization, not causal attribution.** The V0 score ranks execution
   *features* whose variation co-varies with outcome variation. A feature
   downstream of the true source inherits that signal, and association cannot
   separate the two. The paper says "weak-point localization"; "causal
   attribution" is reserved for intervention-based versions.
2. **Synthetic ≠ evidence.** `agents/synthetic.py` validates the harness. It is
   not a data point for any hypothesis above.
3. **Comparator dependence.** Every variation number is relative to the outcome
   comparator. Report the comparator alongside the number, always.
4. **Schema dependence.** Every weak-point number is relative to a frozen
   feature schema. Report `adapter_version` and `feature_schema_version`, and
   never mix results across schemas (§7, §24).
5. **Ties are not wins.** Attribution@k is scored as expected credit under a
   random tie-break, for AgentSeism and every baseline alike. A three-way tie
   for first place is worth 1/3, not 1.

## Planned falsification test

Hypothesis C dies if correlation-only matches AgentSeism on real agents with
injected interventions. On an unordered schema the V0 score is correlation
re-weighted by local variation, so this is a live structural risk, not a remote
one — the pilot reports the comparison directly. If it fires, the answer is
intervention or counterfactual replay, not a better weighting
(DESIGN-FEATURE-PROJECTION.md §22).

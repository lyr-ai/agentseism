# Claims

Hypotheses, not findings. Nothing here may be written as a fact until the
corresponding experiment has been run and recorded in `experiments.md`.

| # | Hypothesis | RQ | Evidence | Status |
|---|------------|----|----------|--------|
| A | LLM-agent behavioral variation is substantial even when conventional task quality remains acceptable | RQ1 | Figure 1 | not started |
| B | Consequential variation is concentrated rather than uniformly distributed across execution | RQ2 | Figure 2 | not started |
| C | Execution-level variation analysis identifies consequential weak points better than trace-diff baselines | RQ3 | Table 1 | harness only (synthetic) |
| D | Weak-point-guided intervention improves robustness on held-out tasks without degrading quality | RQ4 | Figure 4 | not started |

## Status vocabulary

- **not started** — no experiment run
- **harness only** — the measurement pipeline runs, on synthetic data
- **preliminary** — real agents, one configuration
- **supported / refuted** — replicated across agents and seeds

## Standing caveats

1. **Association, not causation.** The V0 score ranks execution points whose
   variation co-varies with outcome variation. A point downstream of the true
   source inherits that signal. Any causal language requires an intervention
   experiment.
2. **Synthetic ≠ evidence.** `agents/synthetic.py` validates the harness. It is
   not a data point for any hypothesis above.
3. **Comparator dependence.** Every variation number is relative to the outcome
   comparator. Report the comparator alongside the number, always.

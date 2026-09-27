# Contributing

AgentSeism makes CI decisions for stochastic AI agents. Contributions are
welcome, especially reports from running it on your own agent: what it caught,
what it missed, what was confusing and what it cost.

## Before opening a PR

- **Say which user problem the change serves.** New features need a concrete
  case where the current verdict was wrong, unhelpful or too expensive.
- **Keep the decision rule's guarantees.** Changes to how verdicts are decided
  (gates, thresholds, minimum evidence, multiplicity) are method changes, not
  refactors. They need a dated design note in `analysis/` and operating
  characteristics (`analysis/ci_v1/operating_characteristics.py`) showing the
  effect on false blocks and detection, before any code.
- **Never turn an unscorable run into a failure.** Infrastructure faults are
  `invalid`, never `FAIL`.

## Development

```bash
pip install -e ".[dev]"
pytest
ruff check .
```

`pytest` runs the product suite only. The archived research line keeps its own
tests under `research/tests/`, and they are not part of CI.

If a change affects what `seism demo` prints, regenerate the README figures:

```bash
python docs/figures/make_readme_figures.py
```

## Reporting a negative result

Negative results are first-class here. If AgentSeism blocked a healthy PR, missed
a regression you know was real, or a simple heuristic did as well on your agent,
open an issue with the data. That is worth more than a feature.

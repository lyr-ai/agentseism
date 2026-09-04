# Contributing

AgentSeism is a research prototype. The scope rule is strict:

> No feature enters V0 unless it is required by one of the six weekly
> deliverables in [ROADMAP.md](ROADMAP.md).

## Before opening a PR

- Say which research question (RQ1-RQ4 in DESIGN.md §22) the change serves.
- Keep the [non-goals](DESIGN.md#5-non-goals) intact. In particular, AgentSeism
  does not judge outcome correctness.
- Attribution claims are association claims. Do not describe a ranked weak point
  as a cause anywhere in code, output, or docs.

## Development

```bash
pip install -e ".[dev]"
pytest
ruff check .
```

New attribution logic must come with a ground-truth test: inject a known weak
point in `agents/synthetic.py`, hide the label, and show the ranker recovers it
while at least one trivial baseline does not.

## Reporting a negative result

Negative results are first-class here. If an experiment shows that variation is
uniform, or that a baseline matches AgentSeism, open an issue with the data —
that outcome is more valuable than a feature.

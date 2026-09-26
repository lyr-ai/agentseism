# Research line (archived)

This directory is AgentSeism's **pre-product research line**: the natural-variation
pilots on GAIA and OpenRCA, the C2/C2-H coding-agent experiments, the vLLM/GPU
inference work, the paper drafts and pre-registrations, and the design documents
that were superseded when the project became a product on 2026-09-20.

**It is not part of the AgentSeism product.** Nothing in `src/`, `agents/coding/` or
`tests/` imports it, and it is not packaged. It is kept here, rather than
deleted, so that the history behind the product stays one directory away.

## What is here

| path | what it was |
|---|---|
| `paper/` | paper drafts, pre-registrations, frozen manifests |
| `experiments/` | the C2/C2-H, natural-variation and recovery-challenge experiment code |
| `data/`, `results/`, `logs/` | raw and summarised research data. `data/runs/*/*.archive/` step archives are gitignored and kept locally only |
| `inference/` | self-hosted vLLM deployment (GPU) and its lock files |
| `benchmarks/` | the frozen GAIA pilot slice |
| `agents/` | research agents and adapters (GAIA, OpenRCA, LangGraph, stubs), plus the instrumented and forking coding-agent components |
| `tests/` | the research tests. They are not collected by the product's `pytest` run |
| `docs/`, `DESIGN*.md`, `ROADMAP.md`, `INVARIANTS.md` | superseded plans, runbooks and design drafts |

## Paths and reproducibility

Files moved here on 2026-09-26 and were not rewritten. Many of them, and parts of
`analysis/`, cite the old top-level paths (`paper/…`, `experiments/…`, `data/…`),
and research code still imports `experiments.*` from the repository root. **To
run or cite this work at its original paths, check out the tag
`archive/pre-product-layout`.** The pre-product GPU/pilot branch is preserved as
`archive/eval-pilot-outcome-grounded-ci`.

The product's evidence is not here. It lives in `analysis/`: the CI v0 run card
and the v1 design, operating characteristics and Stage C confirmatory study.

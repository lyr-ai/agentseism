# Roadmap

AgentSeism is early. This file says where it is going next, and why, so you can
tell whether it's heading somewhere useful for your agent. Direction comes from
evidence and from users: if something here matters to you, or is missing,
[open an issue](https://github.com/lyr-ai/agentseism/issues).

## Now: v0.1.x, making it usable

- **Integration polish.** Make it easy to wire `seism` to an agent that isn't a
  SWE-bench coding agent: clearer runner and evaluator examples, better errors.
- **The first external agent.** Run AgentSeism on someone else's agent and
  learn what breaks. One real user is worth more than any number of extra
  benchmark runs.

## Next: questions the current evidence can't answer yet

- **Other kinds of regression.** All evidence so far comes from cutting an
  agent's step budget. Prompt, tool, model and retrieval changes are untested.
- **Cost to a decision.** 8 runs per task on each side is a validation design,
  not a CI budget. The aim is to measure what a trustworthy verdict costs per PR,
  and bring it down.
- **Sequential, adaptive sampling.** Start small and buy more runs only where
  the evidence is uncertain: more reruns when one task is noisy, more tasks
  when the question is the whole suite. Stop as soon as the verdict is
  defensible.
- **The capability gate on its own.** Show, on fresh real data, a collapse that
  only the capability gate catches.

## Not planned

A hosted service, dashboards, tracing, or an eval-metrics library. AgentSeism is
a CI decision layer, and it should stay small enough to drop into the CI you
already have.

## How changes are made

Changes to how verdicts are decided need a dated design note and a simulation
of their false-block and detection rates, before any code, and they are
confirmed on data the rule hasn't seen. See
[`analysis/`](analysis/) and
[`docs/EXPERIMENTAL_PRODUCT_DEVELOPMENT.md`](docs/EXPERIMENTAL_PRODUCT_DEVELOPMENT.md).

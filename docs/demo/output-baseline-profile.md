# AgentSeism — baseline profile

**Every number below is computed from frozen trajectories in
`data/runs/h2_phase_a1/`.** This is a real measurement of a real agent. It is
not a demonstration of a detected regression; no regression experiment has been
run.

```
AgentSeism: BASELINE CACHED — 1 task, 5 independent histories

Task        pytest-dev__pytest-10051
Agent       mini-swe-agent 2.4.6
Model       Qwen/Qwen3.6-27B-FP8 @ e89b16eb, temperature 0
Serving     vLLM, max_model_len 131072, prefix caching on

Outcome
- exit status          Submitted     5 / 5
- final patch produced 5 / 5

Stability  ← this is why one run is not evidence
- distinct final repository states      5 of 5 runs
      ed135952e20c   843 B      901cfacceed3  1229 B
      687e8628805f   978 B      5ece9b7438d7  1939 B
      5b38138161e5   690 B
- trajectory length                     31, 31, 33, 41, 47 steps
- shared intermediate state             all 5 pass through 400ed4047a82 (438 B),
                                        the one-line self.records = []
                                        → self.records.clear()

Reading
- Five runs of one agent, one task, one model, temperature zero produced five
  different accepted solutions. Trajectory identity is not a quality target
  here, and a check that gated on it would block all five.
- The shared intermediate state is robust across two context lengths and two
  transport paths. Whatever drives runs to it survives serving changes that
  visibly change everything downstream.
- This is descriptive. These runs were collected to generate donors; no batch
  was registered as a test of the topology.

Budget
- 5 histories cached. Reused on every pull request until the agent, tasks,
  evaluator, model or environment compatibility key changes.
```

## What a user does with this

Nothing about merging. A baseline profile answers one prior question: **how much
does this agent vary when nothing has changed?** Five distinct outcomes from an
unchanged agent sets the floor for what a candidate has to do before a difference
means anything.

The number that matters for CI design is not 5/5 distinct. It is that they were
all *accepted*: the variation is real and consequential-looking, and none of it
is a defect.

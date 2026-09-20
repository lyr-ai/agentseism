## AgentSeism: PASS — behaviour changed, outcomes held

Trajectories moved and outcomes did not. Not a reason to block.

| Capability | Baseline | PR | Change | Decision |
|---|---:|---:|---:|---|
| Task success | 4 / 4 | 4 / 4 | 0 pp | PASS |
| Trace divergence | — | 6/6 pairs differ | n/a | diagnostic |

**Evidence**

- Four independent runs of one task, **all four resolved** the issue.
- Steps ranged 31–47; final patches 843–1939 bytes.
- A composite trace detector fires on **6 of 6** correct/correct pairs. Ground truth: none is a regression.
- Source: `data/runs/h2_phase_a1`, recomputed from frozen artifacts.

---

<sub>contract `default-1` `1e3047d6fefbdae6` · protocol v1</sub>

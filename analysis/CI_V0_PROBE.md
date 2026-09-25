# Haiku 4.5 feasibility probe — pre-registration

Written **before the probe runs**. One task, one run, not scored, not Stage A
evidence under any later reading.

2026-09-25, `product/ci-v0`.

## The only question it may answer

> Can `claude-haiku-4-5-20251001` operate this coding-agent setup at all, or
> does it floor / fail to integrate?

It may **not** answer whether AgentSeism works, whether Haiku is good at
SWE-bench, or anything about specificity or sensitivity.

## Configuration

| | |
|---|---|
| model | `anthropic/claude-haiku-4-5-20251001` |
| task | `astropy__astropy-12907` — the first frozen task, alphabetically; not chosen for difficulty, which was never inspected |
| runs | **1** |
| `step_limit` | 250, the frozen baseline value |
| everything else | as frozen in `analysis/ci_v0/` |

## Pass criteria — mechanical, fixed before the output is seen

All five must hold:

1. **Execution valid.** The runner exits 0 and writes `agent_run.json`.
2. **Repository modification attempted.** `exit_status` is a registered
   terminal status, not a format/transport failure.
3. **Non-empty patch.** `patch_bytes > 0`.
4. **Evaluator completes.** `swebench_evaluator.py` returns a JSON object
   containing `success`, not `invalid`.
5. **No infrastructure invalidity.** No `infra_failure`, no unapplied patch,
   no harness error.

**SWE-bench PASS is explicitly not required.** One run on one task failing the
tests is ordinary and says nothing. The probe excludes only "this model cannot
drive this agent".

## Outcomes, declared in advance

| result | meaning | next step |
|---|---|---|
| all five hold | Haiku 4.5 is viable | freeze it as the validation model; decide Stage A separately |
| 3 or 4 fails | the model cannot produce a usable patch here | probe failure; consider Sonnet 5 at roughly 2× cost |
| 1, 2 or 5 fails | integration or infrastructure defect | fix offline, re-probe; **not** a model verdict |

## The second thing it buys

The **first real hosted cost measurement** for this setup. `~$0.30/run` is an
estimate built on assumed token counts with a ±2× error bar, and prompt-caching
savings on an agentic trajectory depend on prefix reuse that has never been
measured here.

Declared in advance, so it is not rationalised afterwards:

- **≤ $0.50** — consistent with the estimate. Stage A ≈ $15 and the economics
  stand as analysed.
- **$0.50 – $1.00** — Stage A ≈ $25–50. Re-examine before committing; the $25
  stop would likely fire mid-run.
- **> $1.00** — the estimate was wrong by more than its stated error bar.
  **Do not start Stage A.** Re-open the model and design question, including
  whether 5 × 5 × 2 is the right shape at this price.

Choosing Haiku does not commit us to Stage A at any price the probe reveals.

## Hard boundary

Stop immediately after the probe. Report the five criteria and the actual cost.
**Do not start Stage A**, whatever the result.

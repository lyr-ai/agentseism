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

---

## Result — recorded 2026-09-25, probe commit `e662ffd`

| criterion | required | observed |
|---|---|---|
| 1. execution valid | exit 0, `agent_run.json` written | ✅ |
| 2. repository modification attempted | registered terminal status | ✅ `Submitted` |
| 3. non-empty patch | `patch_bytes > 0` | ✅ **504** |
| 4. evaluator completes | JSON with `success`, not `invalid` | ✅ |
| 5. no infrastructure invalidity | no infra_failure, patch applied | ✅ |

**All five hold. Probe passes. `claude-haiku-4-5-20251001` is frozen as the
validation model.**

```text
instance      astropy__astropy-12907
exit_status   Submitted
patch_bytes   504
model_calls   24
seconds       90.59
usd           0.099506
label         PASS   (success 1)
```

### The cost measurement

**$0.0995 for one run** — inside the pre-declared `≤ $0.50` band, and about 3×
below the `~$0.30` estimate. At this rate Stage A's 50 invocations project to
roughly **$5**, and the frozen $25 stop has about 5× headroom rather than
firing mid-run.

The estimate's stated ±2× error bar was too narrow and wrong in the cheap
direction. The assumption that overshot was steps per run: ~40 assumed, **24**
observed. Prompt caching is doing what the fix intended.

### The instance resolved, and that is not the finding

`label: PASS` — the agent produced the correct fix, a one-line change in
`_cstack`. **This was explicitly not a pass criterion** and must not be read as
one. n = 1 on one task supports no claim about resolve rate, and the probe was
designed to exclude only "this model cannot drive this agent".

What it does license, narrowly: the floor worry that motivated choosing between
Haiku and Sonnet is not realised here. One resolved instance is not a rate, but
it is incompatible with a model that cannot operate the agent at all.

### What this does not establish

Nothing about AgentSeism. No specificity, no sensitivity, no verdict quality.
The probe is not Stage A evidence and its artifacts are not Stage A data under
any later reading.

### Stop

Stage A is **not started**, as pre-registered. Total spend on this probe:
**$0.0995**.

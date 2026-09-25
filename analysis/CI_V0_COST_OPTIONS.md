# CI v0 — model and cost options

Investigation only. Nothing was run, no credential was used, and tasks, trials,
contract and thresholds are untouched. Prices are read from litellm's local
table (`model_prices_and_context_window_backup.json`, 3917 entries), not from
memory.

2026-09-25.

## First: two findings that change the arithmetic

### 1. The adapter disables Anthropic prompt caching — a 5–10× cost error

mini-swe-agent turns caching on by default for Anthropic models, but only in
`minisweagent.models.get_model()`:

```python
if (any(s in resolved_model_name.lower()
        for s in ["anthropic", "sonnet", "opus", "claude"])
        and "set_cache_control" not in config):
    config["set_cache_control"] = "default_end"
```

`agents/coding/swebench_runner.py` constructs `LitellmModel(...)` **directly**
and bypasses that path, so every step would re-send the whole conversation at
full price. On a SWE-bench trajectory — where each step resends a growing
prefix — that is the difference between roughly **$0.60 and $3.30 per run**.

**This must be fixed before any paid run**, and it is a defect rather than a
design change: one line, either calling `get_model()` or passing
`set_cache_control="default_end"`. Every estimate below assumes it is fixed.

### 2. No baseline can be reused

Checked directly:

- **Zero** existing artifacts for any of the five frozen tasks. All prior
  coding work used `pytest-dev__pytest-10051`, the C2-H donor.
- Every prior run used `Qwen/Qwen3.6-27B-FP8` on a self-hosted vLLM. That model
  has no endpoint now, and it is not any hosted model — so even with task
  overlap the arms would differ on `model_revision` and the contract would
  return `INCOMPARABLE` rather than compare them.

So all 50 Stage A invocations are new. There is no 25-invocation saving
available.

## The cost model, with its assumptions exposed

No measured token count exists for this agent on these tasks, so every figure
below is arithmetic over stated assumptions, not data:

| assumption | value | basis |
|---|---|---|
| steps per run | ~40 | `step_limit` is 250; typical SWE-bench completions are far shorter. The one real datum is the host-5 smoke: 54 requests on one instance |
| cumulative input per run, uncached | ~1.6 M tokens | 40 steps over a prefix growing to ~80 k |
| effective input with caching | ~0.25 M | ~90 % of the prefix served from cache |
| output per run | ~10 k tokens | 40 steps × ~250 tokens |

The honest error bar on these is roughly **±2×**. They are good enough to rank
options and not good enough to promise a total.

## Options

| | model | $/M in · out | est. per run | **est. Stage A (50)** | key needed |
|---|---|---|---|---|---|
| **A** | `claude-sonnet-5` | 2.00 · 10.00 | ~$0.60 | **~$30** | Anthropic |
| **B** | `claude-haiku-4-5-20251001` | 1.00 · 5.00 | ~$0.30 | **~$15** | Anthropic (same key as A) |
| **C** | `deepseek/deepseek-v3.2` | 0.28 · 0.42 | ~$0.10–0.45 | **~$5–22** | DeepSeek |

Rejected, and why — this is the part that matters more than the prices:

- **Sub-$0.10 models** (glm-4.7-flash at $0.06, qwen3-4b, llama-3.1-8b, nova-micro).
  These are 4–30 B class. On SWE-bench Verified they would resolve close to
  zero, and **a floored baseline makes the negative control vacuous**: baseline
  0.00 against candidate 0.00 gives an effect of exactly zero and a confident
  PASS that demonstrates nothing about specificity. Cheapness that destroys the
  measurement is not a saving.
- `claude-sonnet-4-5-20250929` (mini-swe-agent's shipped default) is **more**
  expensive than `claude-sonnet-5` — $3/$15 against $2/$10 — with a 200 k
  context instead of 1 M. There is no reason to prefer it except as a fallback
  if `claude-sonnet-5` does not resolve.

### What separates B from A

Option B is the same provider and the same key as A, half the price, and a
genuinely capable coding model. The question it raises is whether Haiku's
SWE-bench resolve rate is high enough to avoid a partial floor. If baseline
resolves, say, 1 task in 5, the negative control still has variance to misread
and remains a real test; if it resolves 0 in 5, it has the same vacuity problem
as the rejected tier.

That is answerable for about **$0.30**: run one task, once, and see whether the
agent produces a plausible patch. It is not part of Stage A and would not be
scored as such.

### What separates C from A and B

Option C is cheapest per token and needs a **second provider account**. It also
has no Anthropic-style automatic cache control in this adapter, so its estimate
is the widest. Its resolve rate on SWE-bench Verified is respectable, but the
extra credential and the wider uncertainty buy maybe $10 against option B.

## Recommendation

**Option B — `claude-haiku-4-5-20251001`, estimated ~$15 for Stage A**, with a
single calibration run first to confirm it does not floor.

Reasons, in order: it uses the credential you already intend to supply; it is
half the price of A for the same provider and tooling; and the only risk it
adds over A — a partial floor — is measurable in advance for about thirty
cents. If calibration shows a floor, fall back to A at roughly $30 rather than
adding a provider.

## What still needs to be frozen before any run

A dollar stop, declared as a number with an outcome, replacing the vague "stop
if it climbs unexpectedly" that this card previously carried:

> **Stage A stops at 50 invocations or $X, whichever comes first.** If the
> dollar stop fires, the outcome is `COST_STOP / incomplete` — not a verdict,
> and the partial data is **not** read as specificity evidence.

`$X` is yours to set. Given option B, **$25** leaves roughly 60 % headroom over
the estimate without being unbounded. This is separate from mini-swe-agent's
per-run `cost_limit: 3.0`, which stays untouched: lowering that would truncate
runs and confound the control.

Nothing here is authorised to run.

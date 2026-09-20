# Gate 9 — execution log

Audit record for the serving-stack behavioural compatibility gate
(`PREREG_C2_RECOVERABILITY.md` amendments C2.3 and C2.3.1).

**Host.** Lambda VM, NVIDIA H100 PCIe 80 GB, driver 580.105.08, Ubuntu 22.04,
x86_64 native, Docker 29.2.1. Serving stack recorded at `~/c2-serving/stack.txt`
on the host: vLLM 0.28.0, torch 2.13.0+cu130, CUDA 13.0,
`Qwen/Qwen3.6-27B-FP8 @ e89b16eb`, `max_model_len` 131072 allocated in full
(KV cache 40.12 GiB, 631,254 tokens) — **no fallback to 65536 was needed or
taken**.

**Protocol hash `0fafa0a2534272a6` throughout.** No horizon, trajectory,
replication count, threshold, decision rule or spec changed at any point below.

---

## Aborted attempts

Three invocations were stopped before producing results. **Each produced zero
valid model responses and wrote no Gate 9 artifact**, and no matching threshold
or decision rule was altered in response to any of them. All three were defects
in the instrument or the deployment, none was an observation about the host.

| # | Started (UTC) | Aborted because | Valid responses | Artifact written |
|---|---|---|---|---|
| 1 | 2026-09-20 02:37 | `gate9.py` issued a plain non-streaming OpenAI call, dropping the registered `stream=True`, `attempt_timeout=180`, `max_attempts=6`. Compounded by a serving config missing `--reasoning-parser qwen3`, so chain-of-thought returned as content: one root passed 36,000 generated tokens against a 503-character donor turn with no bound. | 0 | no |
| 2 | 2026-09-20 02:48 | Server rejected the agent's tool calls: `"auto" tool choice requires --enable-auto-tool-choice and --tool-call-parser`. `model_h2.yaml` had never carried the three parser keys its own header claims. | 0 | no |
| 3 | 2026-09-20 02:59 | litellm raised `Error calculating cost ... This model isn't mapped yet` **after** generating, discarding every response. The registered `MSWEA_COST_TRACKING=ignore_errors` was exported by `run_phase_a.sh` but not by `run_c2.py` or `gate9.py`. | 0 | no |

### Fixes, and why none is a protocol change

| Commit | Class |
|---|---|
| `282b88e` | Instrument defect. `gate9.py` now builds `InstrumentedLitellmModel` exactly as `run_c2.py` does, so "the generation parameters the continuation would use" is not a separate notion that can drift. |
| `32baf82` | Config completeness defect. `model_h2.yaml` gains `enable_auto_tool_choice`, `tool_call_parser: qwen3_coder`, `reasoning_parser: qwen3`, copied verbatim from `configs/model.yaml`. The donor batch demonstrably ran with them: `h2_phase_a1` records a separate `reasoning` token column, and archived assistant turns carry `extra.actions`. |
| `a9d3da7` | Deployment defect. `requirements.txt` pins never resolved in a clean environment; `vllm==0.28.0` kept as the anchor and full locks committed. |
| (host) | `start_vllm.sh` hardcoded `--host 0.0.0.0`, which on a public-IP VM publishes an unauthenticated endpoint. Now from config, default loopback. |
| `2f82c01` | **Registered-environment propagation defect.** `MSWEA_COST_TRACKING=ignore_errors` is pre-registered (`INTERVENTION_PREREG_H2.md:228`, `CODING_EXPERIMENT_PREREG.md:91`) and exported by the donor runners; `run_c2.py` and `gate9.py` inherited it from whatever shell launched them. Both now set it themselves. |

The last one would have destroyed the C2 batch as well: all 72 continuations
would have paid for generation and then discarded the response. It is classified
as **registered-environment propagation**, not as a protocol change — the value
was already registered; only its propagation into the new runners was missing.

---

## Integrity gate, applied before any verdict

C2.3's three branches are evaluated **only** on a complete set of valid
responses. Before reading them, all of the following must hold across the 23
archived-comparable roots:

1. 23 / 23 received a non-empty model response;
2. raw assistant text parsed for every root;
3. structured action / tool call extracted for every root;
4. no `request_error`, timeout, empty response or parse failure.

Any of those is **execution-invalid** and is *not* a behavioural mismatch. **If
even one root is execution-invalid, Gate 9 is marked incomplete and stops.** It
does not fall through to branch 3.

`A_6 h=16` remains `compatibility_unknown` under C2.3.1 and is outside this
count; the admissible phrasing stays *"all 23 archived-comparable fork roots
…"*, never *"all fork roots"*.

---

## Attempt 4

Started 2026-09-20 03:08 UTC. The only change from attempt 3 is restoration of
the pre-registered environment variable. Result recorded below when complete.

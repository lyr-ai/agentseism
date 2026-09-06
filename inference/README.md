# Cloud inference deployment

Written before renting anything, so that the first billable minute is spent
running an experiment rather than reading vLLM documentation.

## Why this exists

The local route ended on measurement, not opinion. An M4 Pro with 24 GB of
unified memory serving DeepSeek-Coder-V2-Lite-Instruct 4-bit:

| context | TTFT | decode | available | swap delta |
|---|---|---|---|---|
| 24 | -- | 36.8 tok/s | 3.9 GB | ~0 |
| 7,640 | 10.3 s | 89.8 tok/s | 4.5 GB | **+1242 MB** |
| 15,240 | 22.2 s | 65.8 tok/s | 4.2 GB | **+1647 MB** |

A pre-declared rule stopped the local route at 16k: swap grew by more than a
gigabyte at every step and never returned. **That is a hardware result, not a
model result** -- the model was competent at short context, and 32k was never
tested because the rule said not to. Continuing locally would have folded a
memory bottleneck into every subsequent measurement.

Two numbers from that table are worth carrying forward as expectations. TTFT
roughly doubled when context doubled, which is prefill being linear in prompt
length. Decode fell much less, because each new token attends to a cache that
already exists. Those shapes should reappear on a GPU; what should *not* is the
swap.

## The $3 lab

```
rent 48 GB (A6000 / A40)  ->  docker run  ->  ./run_qualification.sh  ->  terminate
```

**Run it by hand the first time.** The script exists so that nothing is
improvised at an hourly rate, but a single invocation hands back a CSV and
teaches nothing about where the memory went. Stop at each step instead:
`nvidia-smi` on the empty card, then after vLLM loads -- weights against KV cache
-- then 8k cold, 8k repeated, 16k cold, 16k repeated, reading `gpu.csv`
alongside. Use the script end-to-end from the second session onward.

`run_qualification.sh` does health, stress, one SWE-bench task, and prints a
reminder. 48 GB before 80 GB, and not an H100: the first session is for learning
where the memory goes, and a faster card teaches that less clearly.

## What is pinned, and why

`configs/model.yaml` fixes the checkpoint **revision**, dtype, quantization,
`max_model_len`, GPU memory utilisation and the sampler; `requirements.txt` fixes
vLLM, torch and transformers; the Dockerfile pins its base tag. `start_vllm.sh`
writes the resolved versions and the GPU model to `stack.txt` before serving.

The reason is specific. This project has already had one result move because an
upstream default changed underneath it. A serving stack that drifts would make
every later difference ambiguous between agent variation -- the object of study
-- and a different inference engine.

`model.id` is intentionally empty. DeepSeek-Coder-V2-Lite was a choice made under
a 24 GB constraint that no longer applies; on a 48 GB card the question is which
open-weight coder is most competent within budget, and that is answered by
measuring rather than by inheriting.

## One thing to look for

`enable_prefix_caching` matters more for this workload than for most. The agent
resends its full history every step, so step N re-prefills everything from step
N-1, and prefill is the linear cost above.

Under two conditions -- history grows roughly linearly per round, and each round
re-prefills all of it -- total prefill work over N rounds is 1 + 2 + ... + N,
which is O(N^2). Both conditions hold for this agent and neither is general:
an agent that summarises its history, or a server that reuses a cached prefix,
breaks the first and second respectively. Stated without those conditions the
claim would be wrong about agent serving in general.

Whether the reuse actually happens shows up as a flat TTFT on the repeated
request in `stress_test.py`, which is the first thing worth reading in the
results.

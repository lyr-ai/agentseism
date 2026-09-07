# First session on RunPod

## Image: use vLLM's, not ours

The `Dockerfile` here builds on `vllm/vllm-openai:v0.28.0` and copies scripts in.
Using it on RunPod would mean building locally, pushing to a registry, and
pulling it back — three steps that buy nothing for a first session, since the
only thing our image adds is a handful of scripts that `git clone` also provides.

So: run the stock image and fetch the scripts inside it.

    Container image:  vllm/vllm-openai:v0.28.0
    Container disk:   30 GB      (image + OS, no weights)
    Volume:           80 GB  ->  /workspace
    Expose HTTP port: 8000
    Env:              HF_HOME=/workspace/hf

The volume is where the weights go, and 80 GB is deliberate: 30.9 GB of FP8
weights, the HF cache's temporary copy during download, and room to try a second
model without re-renting. Container disk holds no weights, so 30 GB is enough.

**Do not set a `docker command` in the template.** The stock image's entrypoint
starts vLLM immediately with its own defaults, which are not ours. Override the
container start command with `sleep infinity` so the pod comes up idle and every
step below is deliberate.

## Boot sequence

Nothing here is one-shot. The point of the first session is watching where the
memory goes.

```bash
# 1 — the empty card, before anything is loaded
nvidia-smi

# 2 — scripts and config
cd /workspace
git clone --depth 1 https://github.com/lyr-ai/agentseism
cd agentseism/inference
pip install -q huggingface_hub openai pyyaml

# 3 — weights onto the volume (~31 GB, several minutes)
export HF_HOME=/workspace/hf
python3 -c "
from huggingface_hub import snapshot_download
snapshot_download('Qwen/Qwen3.6-27B-FP8',
                  revision='e89b16ebf1988b3d6befa7de50abc2d76f26eb09')"

# 4 — serve, and read stack.txt before anything else
OUTPUT_DIR=/workspace/runs CONFIG=./configs/model.yaml ./start_vllm.sh 2>&1 | tee /workspace/serve.log &

# 5 — the number this session exists for: weights vs KV cache
#     Run while vLLM logs its memory profile, and compare with step 1.
watch -n2 nvidia-smi

# 6 — health, then tool calling. The second is the one that matters:
#     a wrong parser serves happily and returns no actions.
./healthcheck.sh

# 7 — cold and warm at each context. The warm request is the prefix-cache test.
python3 stress_test.py --base-url http://localhost:8000/v1 \
    --contexts 8000,16000 --repeat 2 --out /workspace/runs/stress.json

# 8 — one real trajectory
pip install -q mini-swe-agent datasets
export OPENAI_API_BASE=http://localhost:8000/v1 OPENAI_API_KEY=not-needed
python3 -m minisweagent.run.benchmarks.swebench_single \
    --subset verified --split test -i astropy__astropy-12907 \
    -m openai/Qwen/Qwen3.6-27B-FP8 -y --exit-immediately \
    -o /workspace/runs/qualification.json

# 9 — copy /workspace/runs off the pod, then shutdown_checklist.md
```

Step 8 needs Docker inside the pod for the SWE-bench container, which RunPod does
not provide. If that blocks, stop after step 7: the inference measurements are
the session's main purpose and the agent run can happen anywhere the endpoint is
reachable.

## Stop early if

- vLLM reports the architecture needs sharding. Every example on the model card
  uses `--tensor-parallel-size 8`; one 48 GB card at 32k context should be
  enough, but that is an inference from the numbers, not a confirmation.
- `healthcheck.sh` fails on tool calling. The parser is wrong and no amount of
  agent debugging will help.
- Weights do not load within ~15 minutes.

Terminate first, diagnose from the logs afterwards.

## Planned as a second experiment, not now

`--language-model-only` skips the vision tower and its profiling, which should
leave more room for KV cache on a text-only workload. Worth measuring as
on-versus-off once the baseline allocation is known — changing it before the
first boot would mean never seeing what the default actually reserves.

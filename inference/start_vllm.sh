#!/usr/bin/env bash
# Start vLLM from configs/model.yaml and record the stack that served the run.
#
# Every parameter comes from the config file rather than the command line, so
# that what was served is recoverable from a committed artifact rather than from
# shell history.
set -euo pipefail

CFG="${CONFIG:-/srv/configs/model.yaml}"
OUT="${OUTPUT_DIR:-/models/runs}"
mkdir -p "$OUT"

y() { python3 -c "import yaml,sys; d=yaml.safe_load(open('$CFG')); v=d
for k in '$1'.split('.'): v=v.get(k) if isinstance(v,dict) else None
print('' if v is None else v)"; }

MODEL=$(y model.id); REV=$(y model.revision)
[ -n "$MODEL" ] || { echo "FATAL: model.id is unset in $CFG" >&2; exit 2; }
[ -n "$REV" ]   || { echo "FATAL: model.revision is unset -- pin a commit sha, not a branch" >&2; exit 2; }

# The stack, captured before anything is served. If a later result disagrees
# with an earlier one, this file is what distinguishes agent variation from a
# different serving stack.
{
  echo "timestamp=$(date -u +%FT%TZ)"
  echo "model=$MODEL"
  echo "revision=$REV"
  echo "vllm=$(python3 -c 'import vllm;print(vllm.__version__)' 2>/dev/null || echo unknown)"
  echo "torch=$(python3 -c 'import torch;print(torch.__version__)' 2>/dev/null || echo unknown)"
  echo "cuda=$(python3 -c 'import torch;print(torch.version.cuda)' 2>/dev/null || echo unknown)"
  nvidia-smi --query-gpu=name,memory.total,driver_version --format=csv,noheader 2>/dev/null \
    | sed 's/^/gpu=/' || echo "gpu=none"
} | tee "$OUT/stack.txt"

ARGS=(--model "$MODEL" --revision "$REV" --host 0.0.0.0 --port 8000
      --dtype "$(y model.dtype)"
      --max-model-len "$(y serving.max_model_len)"
      --gpu-memory-utilization "$(y serving.gpu_memory_utilization)"
      --tensor-parallel-size "$(y serving.tensor_parallel_size)"
      --max-num-seqs "$(y serving.max_num_seqs)"
      --swap-space "$(y serving.swap_space)")
[ "$(y model.quantization)" != "" ] && ARGS+=(--quantization "$(y model.quantization)")
[ "$(y serving.enable_prefix_caching)" = "True" ] && ARGS+=(--enable-prefix-caching)
[ "$(y model.trust_remote_code)" = "True" ] && ARGS+=(--trust-remote-code)

echo "+ vllm serve ${ARGS[*]}"
exec python3 -m vllm.entrypoints.openai.api_server "${ARGS[@]}"

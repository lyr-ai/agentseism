#!/usr/bin/env bash
# Run this in the first minute of a pod's life, before downloading anything.
#
# Exists because recording a fact is not the same as gating on it. The first
# session captured `570.195.03` correctly in stack.txt and then spent thirty
# minutes discovering what it meant. These are the same three facts, checked
# instead of logged.
set -uo pipefail

MIN_DRIVER="${MIN_DRIVER:-580}"   # driver >= 580 exposes CUDA 13.0
fail=0
note() { printf '  %-14s %s\n' "$1" "$2"; }

echo "=== preflight ==="

if ! command -v nvidia-smi >/dev/null; then
  note "driver" "FAIL  no nvidia-smi -- this host has no GPU"
  exit 1
fi
DRIVER=$(nvidia-smi --query-gpu=driver_version --format=csv,noheader | head -1)
GPU=$(nvidia-smi --query-gpu=name,memory.total --format=csv,noheader | head -1)
MAJOR=${DRIVER%%.*}
if [ "$MAJOR" -ge "$MIN_DRIVER" ]; then
  note "driver" "ok    $DRIVER"
else
  note "driver" "FAIL  $DRIVER  (need >= $MIN_DRIVER for CUDA 13 wheels)"
  fail=1
fi
note "gpu" "$GPU"

if python3 -c "import torch" 2>/dev/null; then
  read -r TV TC TA <<<"$(python3 -c "
import torch
print(torch.__version__, torch.version.cuda, torch.cuda.is_available())" 2>/dev/null)"
  if [ "$TA" = "True" ]; then
    note "torch" "ok    $TV  cuda $TC  available"
  else
    note "torch" "FAIL  $TV  cuda $TC  NOT available -- driver/runtime mismatch"
    fail=1
  fi
else
  note "torch" "FAIL  not installed -- use an image that ships it"
  fail=1
fi

if VV=$(python3 -c "import vllm; print(vllm.__version__)" 2>/dev/null); then
  note "vllm" "ok    $VV"
else
  note "vllm" "FAIL  not installed -- installing it here is how the first session was lost"
  fail=1
fi

echo
if [ "$fail" -eq 0 ]; then
  echo "PREFLIGHT OK -- safe to download weights"
else
  echo "PREFLIGHT FAILED -- terminate this pod, do not repair it"
  echo "  A mismatch here costs pennies. Repairing it on a billed instance costs"
  echo "  half an hour and still fails, which is what happened the first time."
fi
exit "$fail"

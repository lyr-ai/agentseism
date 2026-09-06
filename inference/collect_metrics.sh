#!/usr/bin/env bash
# Sample GPU state alongside a workload. Run in the background during a test;
# the CSV lines up with the timestamps the stress test records.
set -euo pipefail
OUT="${1:-/models/runs/gpu.csv}"; INTERVAL="${INTERVAL:-2}"
echo "timestamp,gpu_util_pct,mem_used_mb,mem_total_mb,power_w,temp_c" > "$OUT"
while true; do
  nvidia-smi --query-gpu=utilization.gpu,memory.used,memory.total,power.draw,temperature.gpu \
    --format=csv,noheader,nounits | sed "s/^/$(date -u +%FT%TZ),/" >> "$OUT"
  sleep "$INTERVAL"
done

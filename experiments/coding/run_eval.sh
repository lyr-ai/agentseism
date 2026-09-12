#!/usr/bin/env bash
# Evaluate every recorded submission, one run at a time.
#
# SWE-bench keys predictions by instance_id and the surviving data is twenty
# runs of one instance, so they cannot share a predictions file. Each run is its
# own evaluation with its own run_id, and the reports are collected afterwards.
set -uo pipefail
cd "$(dirname "$0")/../.."

PRED=data/eval/predictions
OUT=data/eval/reports
mkdir -p "$OUT"

for f in "$PRED"/*.jsonl; do
  key=$(basename "$f" .jsonl)
  if [ -s "$OUT/agentseism.$key.json" ]; then echo "skip  $key"; continue; fi
  T0=$SECONDS
  .venv-eval/bin/python -m swebench.harness.run_evaluation \
    --dataset_name SWE-bench/SWE-bench_Verified --split test \
    --predictions_path "$f" --run_id "$key" \
    --max_workers 1 --timeout 1800 --report_dir "$OUT" \
    >"$OUT/$key.log" 2>&1
  R=$(python3 -c "
import json,sys
try:
    d=json.load(open('$OUT/agentseism.$key.json'))
    print('resolved' if d.get('resolved_ids') else 'UNRESOLVED')
except Exception as e: print('NOREPORT')")
  printf '%-52s %5ds  %s\n' "$key" "$((SECONDS-T0))" "$R"
done

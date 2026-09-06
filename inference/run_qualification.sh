#!/usr/bin/env bash
# The whole $3 lab, in order, so that nothing is improvised while the meter runs.
#
#   health -> stress -> one SWE-bench task -> record cost -> remind to terminate
#
# Stops at the first failure. A qualification that half-ran is not a cheaper
# qualification, it is an ambiguous one.
set -euo pipefail

BASE="${BASE:-http://localhost:8000}"
OUT="${OUTPUT_DIR:-/models/runs/$(date -u +%Y%m%dT%H%M%SZ)}"
INSTANCE="${INSTANCE:-astropy__astropy-12907}"   # the task the Sonnet runs used
mkdir -p "$OUT"
START=$SECONDS

echo "=== 1/4 health ==="
BASE="$BASE" ./healthcheck.sh | tee "$OUT/health.txt"

echo "=== 2/4 gpu sampler ==="
./collect_metrics.sh "$OUT/gpu.csv" & METRICS=$!
trap 'kill $METRICS 2>/dev/null || true' EXIT

echo "=== 3/4 context stress ==="
python3 stress_test.py --base-url "$BASE/v1" --out "$OUT/stress.json" | tee "$OUT/stress.txt"

echo "=== 4/4 one SWE-bench task ==="
# mini-swe-agent reaches the endpoint through litellm's openai-compatible path.
# The model is served locally, so no key is needed and none is sent.
export OPENAI_API_BASE="$BASE/v1" OPENAI_API_KEY="not-needed"
MODEL=$(curl -s "$BASE/v1/models" | python3 -c 'import json,sys;print(json.load(sys.stdin)["data"][0]["id"])')
python3 -m minisweagent.run.benchmarks.swebench_single \
  --subset verified --split test -i "$INSTANCE" \
  -m "openai/$MODEL" -y --exit-immediately \
  -o "$OUT/qualification.json" 2>&1 | tail -20 | tee "$OUT/agent.txt"

echo "=== done in $((SECONDS - START))s ==="
python3 - "$OUT/qualification.json" <<'PY'
import json, sys
d = json.load(open(sys.argv[1])); i = d["info"]
print("exit_status:", i.get("exit_status"))
print("patch bytes:", len(i.get("submission") or ""))
print("api_calls  :", i["model_stats"].get("api_calls"))
PY
echo
echo "REMINDER: the GPU is still billing. See shutdown_checklist.md"

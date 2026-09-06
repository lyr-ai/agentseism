#!/usr/bin/env bash
# Block until the endpoint answers, then prove it can actually decode.
# A served /v1/models does not mean weights finished loading.
set -euo pipefail
BASE="${BASE:-http://localhost:8000}"; DEADLINE=$((SECONDS + ${TIMEOUT:-900}))

printf 'waiting for %s/v1/models ' "$BASE"
until curl -sf "$BASE/v1/models" >/dev/null 2>&1; do
  [ $SECONDS -lt $DEADLINE ] || { echo " TIMEOUT"; exit 1; }
  printf '.'; sleep 5
done
echo " up after ${SECONDS}s"

MODEL=$(curl -s "$BASE/v1/models" | python3 -c 'import json,sys;print(json.load(sys.stdin)["data"][0]["id"])')
echo "serving: $MODEL"

RESP=$(curl -sf "$BASE/v1/chat/completions" -H 'Content-Type: application/json' -d "$(python3 -c "
import json;print(json.dumps({'model':'$MODEL','messages':[{'role':'user','content':'Reply with exactly: OK'}],'max_tokens':8,'temperature':0}))")")
echo "decode: $(echo "$RESP" | python3 -c 'import json,sys;print(repr(json.load(sys.stdin)["choices"][0]["message"]["content"]))')"
echo "HEALTHY"

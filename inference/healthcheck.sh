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
# Tool calling, checked separately: the agent is unusable without it, and a
# wrong parser reports no actions rather than an error.
TOOLS=$(curl -sf "$BASE/v1/chat/completions" -H 'Content-Type: application/json' -d "$(python3 -c "
import json
print(json.dumps({'model':'$MODEL','max_tokens':64,'temperature':0,
 'messages':[{'role':'user','content':'List the files in the current directory.'}],
 'tools':[{'type':'function','function':{'name':'bash','description':'Run a bash command',
   'parameters':{'type':'object','properties':{'command':{'type':'string'}},'required':['command']}}}]}))")")
if echo "$TOOLS" | python3 -c 'import json,sys; d=json.load(sys.stdin); sys.exit(0 if d["choices"][0]["message"].get("tool_calls") else 1)' 2>/dev/null; then
  echo "tool calling: OK"
else
  echo "tool calling: FAILED -- mini-swe-agent will receive no actions" >&2
  echo "  check --tool-call-parser against the model card" >&2
  exit 1
fi

echo "HEALTHY"

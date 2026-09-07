#!/usr/bin/env bash
# The pre-registered coding experiment: 10 repositories x 3 runs.
#
# Each run writes its own trajectory and probe file, so an interruption costs
# the run in flight and nothing else. Nothing here selects or skips a task --
# the manifest is frozen and read as given.
set -uo pipefail
export PATH="$HOME/.local/bin:$PATH"

MINI="${MINI:?set MINI to the mini-swe-agent checkout}"
OUT="${OUT:-$MINI/runs/exp1}"
RUNS="${RUNS:-3}"
INSTANCES="${INSTANCES:-/tmp/swe_final.txt}"
mkdir -p "$OUT"

export MSWEA_COST_TRACKING=ignore_errors
export PYTHONPATH=/Users/ruxiz/project/agentseism
cd "$MINI"

START=$SECONDS
while read -r IID; do
  [ -n "$IID" ] || continue
  IMG="swebench/sweb.eval.x86_64.$(echo "$IID" | sed 's/__/_1776_/' | tr 'A-Z' 'a-z'):latest"
  # A custom environment_class must carry its own image: upstream's swebench.py
  # injects one only for the literal names "docker" and "swerex_modal".
  cat > "$OUT/$IID.yaml" <<YAML
environment:
  environment_class: agents.coding.instrumented_docker.InstrumentedDockerEnvironment
  image: $IMG
model:
  model_name: "openai/Qwen/Qwen3.6-27B-FP8"
  model_kwargs:
    drop_params: true
YAML
  for r in $(seq 0 $((RUNS-1))); do
    TRAJ="$OUT/${IID}__r${r}.json"
    if [ -s "$TRAJ" ]; then echo "skip  $IID r$r (exists)"; continue; fi
    export AGENTSEISM_PROBE_OUTPUT="$OUT/${IID}__r${r}.probe.jsonl"
    rm -f "$AGENTSEISM_PROBE_OUTPUT"
    T0=$SECONDS
    .venv/bin/python -m minisweagent.run.benchmarks.swebench_single \
      --subset verified --split test -i "$IID" \
      -c src/minisweagent/config/benchmarks/swebench.yaml -c "$OUT/$IID.yaml" \
      -y --exit-immediately -o "$TRAJ" >"$OUT/${IID}__r${r}.log" 2>&1
    S=$(python3 -c "
import json,sys
try:
    d=json.load(open('$TRAJ')); i=d['info']
    print(i.get('exit_status'), len(i.get('submission') or ''), i['model_stats'].get('api_calls'))
except Exception: print('NOFILE 0 0')")
    printf '%-34s r%d  %4ds  %s\n' "$IID" "$r" "$((SECONDS-T0))" "$S"
  done
done < <(cat "$INSTANCES"; echo)

echo "total $(( (SECONDS-START)/60 )) min"

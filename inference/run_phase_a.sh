#!/usr/bin/env bash
# H2 Phase A: fresh donors for the intervention, with the archive turned on.
#
# One task, five independent runs. These are new runs on purpose. The three
# pytest runs in the primary batch generated the hypothesis -- they are what
# showed that a run can meet another on a real source state and part again --
# and using them again as the thing the intervention is measured against would
# be testing a hypothesis on the data that produced it.
#
# The only differences from run_coding_experiment.sh are the ones the
# pre-registration names: an archiving agent, an archive directory per run, and
# a server started from configs/model_h2.yaml at 131072.
set -uo pipefail
export PATH="$HOME/.local/bin:$PATH"

MINI="${MINI:?set MINI to the mini-swe-agent checkout}"
OUT="${OUT:-$MINI/runs/h2_phase_a}"
RUNS="${RUNS:-5}"
IID="${IID:-pytest-dev__pytest-10051}"
mkdir -p "$OUT"

export MSWEA_COST_TRACKING=ignore_errors
export PYTHONPATH=/Users/ruxiz/project/agentseism
cd "$MINI"

IMG="swebench/sweb.eval.x86_64.$(echo "$IID" | sed 's/__/_1776_/' | tr 'A-Z' 'a-z'):latest"
cat > "$OUT/$IID.yaml" <<YAML
environment:
  environment_class: agents.coding.instrumented_docker.InstrumentedDockerEnvironment
  image: $IMG
model:
  model_name: "openai/Qwen/Qwen3.6-27B-FP8"
  model_kwargs:
    drop_params: true
YAML

START=$SECONDS
for r in $(seq 0 $((RUNS-1))); do
  TRAJ="$OUT/${IID}__r${r}.json"
  if [ -s "$TRAJ" ]; then echo "skip  $IID r$r (exists)"; continue; fi
  export AGENTSEISM_PROBE_OUTPUT="$OUT/${IID}__r${r}.probe.jsonl"
  # One archive tree per run. The probe writes repository bytes into it and the
  # archiving agent writes the message log into the same step directories, so a
  # fork point is one directory rather than a join across two files.
  export AGENTSEISM_PROBE_ARCHIVE="$OUT/${IID}__r${r}.archive"
  rm -rf "$AGENTSEISM_PROBE_OUTPUT" "$AGENTSEISM_PROBE_ARCHIVE"
  T0=$SECONDS
  .venv/bin/python -m minisweagent.run.benchmarks.swebench_single \
    --subset verified --split test -i "$IID" \
    --agent-class agents.coding.archiving_agent.ArchivingInteractiveAgent \
    -c src/minisweagent/config/benchmarks/swebench.yaml -c "$OUT/$IID.yaml" \
    -y --exit-immediately -o "$TRAJ" >"$OUT/${IID}__r${r}.log" 2>&1
  S=$(python3 -c "
import json,glob
try:
    d=json.load(open('$TRAJ')); i=d['info']
    n=len(glob.glob('$AGENTSEISM_PROBE_ARCHIVE/step_*/messages.json'))
    print(i.get('exit_status'), len(i.get('submission') or ''), i['model_stats'].get('api_calls'), 'forkpoints='+str(n))
except Exception: print('NOFILE 0 0 forkpoints=0')")
  printf '%-34s r%d  %4ds  %s\n' "$IID" "$r" "$((SECONDS-T0))" "$S"
done

echo "total $(( (SECONDS-START)/60 )) min"
echo
echo "next: pick the fork point and check it rebuilds, with no model in the loop"
echo "  PYTHONPATH=\$PYTHONPATH python experiments/coding/fork_validation.py \\"
echo "    --runs $OUT --task $IID --image $IMG --work /tmp/h2_forkcheck --platform '' --no-replay"

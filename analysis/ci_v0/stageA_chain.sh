#!/bin/zsh
# Stage A, unattended, second and final attempt (the one fix-forward; see the
# 2026-09-25 deviation in analysis/CI_V0_RUN_CARD.md).
#
# Differences from the first attempt are operational only:
#   * state lives in <repo>/.runs/stageA, not /tmp, so a reboot cannot erase it;
#   * the whole chain runs under caffeinate, so the Mac cannot sleep it;
#   * the $25 stop is enforced by a watchdog during the arms, not only between them.
# Model, tasks, contract, thresholds, trials and degradation are untouched.
# Stops at the end of Stage A. Stage B is not started here under any outcome.
source ~/.zshrc >/dev/null 2>&1
REPO=$HOME/project/agentseism
cd $REPO || exit 1
R=$REPO/.runs/stageA
PY=.venv/bin/python
COST_STOP=25

caffeinate -dimsu -w $$ &

# Pre-flight, before any paid call: the evaluator and the agent both need Docker
# and the five task images. A missing daemon would turn the first runs invalid.
if ! docker info >/dev/null 2>&1; then
  echo "STOP: Docker daemon not reachable. Nothing was run."; exit 1
fi
for t in astropy__astropy-12907 django__django-10097 matplotlib__matplotlib-13989 \
         mwaskom__seaborn-3069 pallets__flask-5014; do
  if ! docker images --format '{{.Repository}}:{{.Tag}}' | grep -q "${t//__/_1776_}"; then
    echo "STOP: image for $t not present locally. Nothing was run."; exit 1
  fi
done

# Starting from 0/50 means starting from an empty directory. Never resume.
if [ -e "$R" ]; then
  echo "STOP: $R already exists. Stage A restarts from zero only; move it aside by hand."
  exit 1
fi
mkdir -p $R/.agentseism/{baselines,runs} $R/tasks
cp analysis/ci_v0/tasks/*.json $R/tasks/
cp analysis/ci_v0/tasks.yaml $R/.agentseism/tasks.yaml
sed "s|AGENTSEISM_ROOT|$REPO|g" analysis/ci_v0/contract.yaml > $R/.agentseism/contract.yaml
echo "=== Stage A attempt 2 — $(date -u +%FT%TZ) — $(git rev-parse --short HEAD) ==="
git status --porcelain | grep -v '^??' && echo "WARNING: tracked files modified at launch"

spend() { find $R/.agentseism/runs -name agent_run.json 2>/dev/null -exec cat {} + 2>/dev/null \
          | grep -o '"usd": [0-9.]*' | awk -F': ' '{s+=$2} END {printf "%.4f", s+0}'; }
count() { find $R/.agentseism/runs -name agent_run.json 2>/dev/null | wc -l | tr -d ' '; }

# The frozen $25 stop, enforced while an arm is running. Stops everything that
# carries the run directory in its command line, then records the outcome.
( while sleep 60; do
    if awk -v t="$(spend)" -v c=$COST_STOP 'BEGIN{exit !(t>c)}'; then
      echo "COST_STOP / incomplete: \$$(spend) after $(count) runs — killing Stage A"
      touch $R/COST_STOP
      pkill -TERM -f "$R"
      exit 0
    fi
  done ) &
WATCHDOG=$!
trap 'kill $WATCHDOG 2>/dev/null' EXIT

# 1. baseline arm, 25 invocations
$PY -m agentseism.cli --dir $R baseline --trials 5
[ -f $R/COST_STOP ] && exit 1
echo "=== baseline arm finished: $(count) runs, \$$(spend) ==="

# 2. refuse to spend on a candidate if the baseline is not usable
if [ ! -f "$R/.agentseism/baselines/main.json" ]; then
  echo "STOP: no frozen baseline. Not running the candidate arm."; exit 1
fi
VALID=$($PY -c "
import json;d=json.load(open('$R/.agentseism/baselines/main.json'))
print(sum(1 for r in d['results'] if not r['invalid']))")
echo "baseline valid runs: $VALID / 25"
if [ "$VALID" -lt 13 ]; then
  echo "STOP: only $VALID/25 baseline runs valid. Not spending on the candidate."
  exit 1
fi

# 3. the unchanged candidate, 25 invocations -- identical config, that is the control
echo "=== candidate arm (unchanged, step_limit 250) ==="
$PY -m agentseism.cli --dir $R check --trials 5
[ -f $R/COST_STOP ] && exit 1
echo "=== Stage A complete: $(count) runs, total spend \$$(spend) ==="
echo "Stage B NOT started, by pre-registration."

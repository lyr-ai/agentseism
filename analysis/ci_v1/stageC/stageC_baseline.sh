#!/bin/zsh
# Stage C, checkpoint 1: the fresh baseline. 7 tasks x 8 trials = 56 runs,
# step_limit 250, v1 frozen at bdd3f93. Stops at the end of the baseline; no
# candidate arm is started here under any outcome.
source ~/.zshrc >/dev/null 2>&1
REPO=$HOME/project/agentseism
cd $REPO || exit 1
C=$REPO/analysis/ci_v1/stageC
R=$REPO/.runs/stageC
PY=.venv/bin/python
COST_STOP=60          # the study's frozen external stop, counted from zero here

caffeinate -dimsu -w $$ &

# ── pre-flight: nothing below this block may spend ──
fail() { echo "STOP: $*. Nothing was run."; exit 1; }
docker info >/dev/null 2>&1 || fail "Docker daemon not reachable"
TASKS=(psf__requests-1142 pydata__xarray-2905 pylint-dev__pylint-4551
       pytest-dev__pytest-10051 scikit-learn__scikit-learn-10297
       sphinx-doc__sphinx-10323 sympy__sympy-11618)
for t in $TASKS; do
  docker images --format '{{.Repository}}:{{.Tag}}' | grep -q "${t//__/_1776_}" \
    || fail "image for $t not present locally"
done
[ -z "$(git status --porcelain)" ] || fail "working tree is not clean"
git diff --quiet bdd3f93 HEAD -- src agents/coding \
  || fail "method code differs from the v1 freeze at bdd3f93"
(cd $C && shasum -a 256 -c -s MANIFEST.sha256) || fail "study config does not match its manifest"
$PY -c "import json,sys; sys.exit(json.load(open('agents/coding/agent_config.json'))['step_limit']!=250)" \
  || fail "step_limit is not 250"
[ -e "$R" ] && fail "$R already exists; the baseline starts from zero only"

mkdir -p $R/.agentseism/{baselines,runs} $R/tasks
cp $C/tasks/*.json $R/tasks/
cp $C/tasks.yaml $R/.agentseism/tasks.yaml
sed "s|AGENTSEISM_ROOT|$REPO|g" $C/contract.yaml > $R/.agentseism/contract.yaml
echo "=== Stage C baseline — $(date -u +%FT%TZ) — $(git rev-parse --short HEAD) (method bdd3f93) ==="

spend() { find $R/.agentseism/runs -name agent_run.json 2>/dev/null -exec cat {} + 2>/dev/null \
          | grep -o '"usd": [0-9.]*' | awk -F': ' '{s+=$2} END {printf "%.4f", s+0}'; }
count() { find $R/.agentseism/runs -name agent_run.json 2>/dev/null | wc -l | tr -d ' '; }

( while sleep 60; do
    if awk -v t="$(spend)" -v c=$COST_STOP 'BEGIN{exit !(t>c)}'; then
      echo "COST_STOP / incomplete: \$$(spend) after $(count) runs — killing Stage C"
      touch $R/COST_STOP; pkill -TERM -f "$R(/| |$)"; exit 0
    fi
  done ) &
WATCHDOG=$!
trap 'kill $WATCHDOG 2>/dev/null' EXIT

$PY -m agentseism.cli --dir $R baseline --trials 8
[ -f $R/COST_STOP ] && exit 1
[ -f $R/.agentseism/baselines/main.json ] || { echo "STOP: no baseline written"; exit 1; }
echo "=== baseline complete: $(count) runs, spend \$$(spend) ==="
echo "No candidate arm started, by protocol."

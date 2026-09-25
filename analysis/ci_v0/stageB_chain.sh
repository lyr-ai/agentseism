#!/bin/zsh
# Stage B, unattended: the pre-declared degraded candidate (step_limit 40)
# against the frozen Stage A baseline. 25 invocations. Stops at the end.
source ~/.zshrc >/dev/null 2>&1
REPO=$HOME/project/agentseism
cd $REPO || exit 1
A=$REPO/.runs/stageA
R=$REPO/.runs/stageB
PY=.venv/bin/python
COST_STOP=25

caffeinate -dimsu -w $$ &

# ── pre-flight: nothing below this block may spend ──
fail() { echo "STOP: $*. Nothing was run."; exit 1; }
docker info >/dev/null 2>&1 || fail "Docker daemon not reachable"
for t in astropy__astropy-12907 django__django-10097 matplotlib__matplotlib-13989 \
         mwaskom__seaborn-3069 pallets__flask-5014; do
  docker images --format '{{.Repository}}:{{.Tag}}' | grep -q "${t//__/_1776_}" \
    || fail "image for $t not present locally"
  cmp -s $A/tasks/$t.json analysis/ci_v0/tasks/$t.json || fail "task file $t differs from the frozen one"
done
[ "$(git rev-parse --short HEAD)" = "6a5af4c" ] || fail "HEAD is not 6a5af4c"
[ -z "$(git status --porcelain)" ] || fail "working tree is not clean"
$PY -c "import json,sys; sys.exit(json.load(open('agents/coding/agent_config.json'))['step_limit']!=40)" \
  || fail "step_limit is not 40"
[ -e "$R" ] && fail "$R already exists; Stage B starts from zero only"

mkdir -p $R/.agentseism/{baselines,runs}
cp -p $A/.agentseism/baselines/main.json $A/.agentseism/baselines/main.json.sha256 $R/.agentseism/baselines/
cp -p $A/.agentseism/contract.yaml $R/.agentseism/contract.yaml
cmp -s $A/.agentseism/baselines/main.json $R/.agentseism/baselines/main.json || fail "baseline copy differs"
cmp -s $A/.agentseism/contract.yaml $R/.agentseism/contract.yaml || fail "contract copy differs"
# Absolute paths into Stage A's task directory: the baseline keys its results
# by those exact strings, and the paired bootstrap pairs on them.
for t in astropy__astropy-12907 django__django-10097 matplotlib__matplotlib-13989 \
         mwaskom__seaborn-3069 pallets__flask-5014; do
  echo "- $A/tasks/$t.json"
done > $R/.agentseism/tasks.yaml

$PY - "$R" <<'EOF' || fail "baseline and candidate task keys do not pair"
import json, sys, types
from agentseism.cli import _load
root, c, s, src, tasks = _load(types.SimpleNamespace(dir=sys.argv[1]))
base = json.load(open(root / "baselines" / "main.json"))
bt = {r["task"] for r in base["results"]}
assert set(tasks) == bt == set(base["tasks"]) and len(bt) == 5, (tasks, bt)
print("pairing ok: 5 tasks, identical keys in both arms")
EOF

echo "=== Stage B — $(date -u +%FT%TZ) — $(git rev-parse --short HEAD) (b2f1bdf + step_limit 40) ==="
echo "baseline sha256 $(shasum -a 256 $R/.agentseism/baselines/main.json | cut -c1-16)"

spend() { find $R/.agentseism/runs -name agent_run.json 2>/dev/null -exec cat {} + 2>/dev/null \
          | grep -o '"usd": [0-9.]*' | awk -F': ' '{s+=$2} END {printf "%.4f", s+0}'; }
count() { find $R/.agentseism/runs -name agent_run.json 2>/dev/null | wc -l | tr -d ' '; }

( while sleep 60; do
    if awk -v t="$(spend)" -v c=$COST_STOP 'BEGIN{exit !(t>c)}'; then
      echo "COST_STOP / incomplete: \$$(spend) after $(count) runs — killing Stage B"
      touch $R/COST_STOP; pkill -TERM -f "$R(/| |$)"; exit 0
    fi
  done ) &
WATCHDOG=$!
trap 'kill $WATCHDOG 2>/dev/null' EXIT

echo "=== degraded candidate (step_limit 40), 25 invocations ==="
$PY -m agentseism.cli --dir $R check --trials 5
RC=$?
[ -f $R/COST_STOP ] && exit 1
echo "=== Stage B complete: $(count) runs, total spend \$$(spend), check exit $RC ==="

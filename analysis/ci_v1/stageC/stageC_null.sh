#!/bin/zsh
# Stage C, checkpoint 2: the null arm. An unchanged candidate (step_limit 250),
# 7 tasks x 8 trials = 56 runs, against the frozen Stage C baseline. Blind.
# Stops after the null arm under every verdict; step 40 is never started here.
source ~/.zshrc >/dev/null 2>&1
REPO=$HOME/project/agentseism
cd $REPO || exit 1
C=$REPO/analysis/ci_v1/stageC
B=$REPO/.runs/stageC            # the baseline run directory, read only
R=$REPO/.runs/stageC_null
PY=.venv/bin/python
COST_STOP=60                    # the study's frozen stop, cumulative across arms

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
  cmp -s $B/tasks/$t.json $C/tasks/$t.json || fail "baseline task file $t differs from the frozen one"
done
[ -z "$(git status --porcelain)" ] || fail "working tree is not clean"
git diff --quiet bdd3f93 HEAD -- src agents/coding \
  || fail "method code differs from the v1 freeze at bdd3f93"
(cd $C && shasum -a 256 -c -s MANIFEST.sha256) || fail "study config does not match its manifest"
$PY -c "import json,sys; sys.exit(json.load(open('agents/coding/agent_config.json'))['step_limit']!=250)" \
  || fail "step_limit is not 250"
[ -f $B/.agentseism/baselines/main.json ] || fail "no Stage C baseline"
[ -e "$R" ] && fail "$R already exists; the null arm starts from zero only"

mkdir -p $R/.agentseism/{baselines,runs}
cp -p $B/.agentseism/baselines/main.json $B/.agentseism/baselines/main.json.sha256 $R/.agentseism/baselines/
cp -p $B/.agentseism/contract.yaml $R/.agentseism/contract.yaml
cmp -s $B/.agentseism/baselines/main.json $R/.agentseism/baselines/main.json || fail "baseline copy differs"
cmp -s $B/.agentseism/contract.yaml $R/.agentseism/contract.yaml || fail "contract copy differs"
# Absolute paths into the baseline's task directory: the baseline keys its
# results by those exact strings, and both gates pair on them.
for t in $TASKS; do echo "- $B/tasks/$t.json"; done > $R/.agentseism/tasks.yaml

$PY - "$R" <<'EOF' || fail "baseline and candidate task keys do not pair"
import json, sys, types
from agentseism.cli import _load
root, c, s, src, tasks = _load(types.SimpleNamespace(dir=sys.argv[1]))
base = json.load(open(root / "baselines" / "main.json"))
bt = {r["task"] for r in base["results"]}
assert set(tasks) == bt == set(base["tasks"]) and len(bt) == 7, (tasks, bt)
assert "capability_regression" in c.features["task_success"], "capability gate missing"
print("pairing ok: 7 tasks, identical keys in both arms; capability gate declared")
EOF

spend_dir() { find $1/.agentseism/runs -name agent_run.json 2>/dev/null -exec cat {} + 2>/dev/null \
              | grep -o '"usd": [0-9.]*' | awk -F': ' '{s+=$2} END {printf "%.4f", s+0}'; }
BASE_SPEND=$(spend_dir $B)
total() { awk -v a=$BASE_SPEND -v b=$(spend_dir $R) 'BEGIN{printf "%.4f", a+b}'; }
count() { find $R/.agentseism/runs -name agent_run.json 2>/dev/null | wc -l | tr -d ' '; }

echo "=== Stage C null arm — $(date -u +%FT%TZ) — $(git rev-parse --short HEAD) (method bdd3f93) ==="
echo "baseline sha256 $(shasum -a 256 $R/.agentseism/baselines/main.json | cut -c1-16); study spend so far \$$BASE_SPEND"

( while sleep 60; do
    if awk -v t="$(total)" -v c=$COST_STOP 'BEGIN{exit !(t>c)}'; then
      echo "COST_STOP / incomplete: study total \$$(total) after $(count) null runs — killing"
      touch $R/COST_STOP; pkill -TERM -f "$R(/| |$)"; exit 0
    fi
  done ) &
WATCHDOG=$!
trap 'kill $WATCHDOG 2>/dev/null' EXIT

$PY -m agentseism.cli --dir $R check --trials 8
RC=$?
[ -f $R/COST_STOP ] && exit 1
echo "=== null arm complete: $(count) runs, arm \$$(spend_dir $R), study total \$$(total), check exit $RC ==="
echo "Step 40 NOT started, by protocol."

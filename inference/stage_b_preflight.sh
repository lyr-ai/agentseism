#!/usr/bin/env bash
# Stage B preflight for the Gate 2 feasibility pilot. Runs on host 2, once.
#
# It prepares and verifies. It never runs a pilot cell, and it stops at
# READY_FOR_MANUAL_PILOT_CONFIRMATION with pilot_runs = 0. The registered
# runner is started by a human afterwards, not from here.
#
# Why a script and not a checklist: host 1 was prepared by hand, one command at
# a time, and the cost of the human round-trips between steps was charged to
# the pilot. Every step below is idempotent, so a host that dies halfway is
# resumed rather than restarted -- except the serving fingerprint, which is
# regenerated on every run because a restarted vLLM is a different session.
#
# FAIL CLOSED. The script will not:
#   * change max_model_len, the model revision, or any registered parameter;
#   * change the task-selection rule or skip a candidate that failed to pull;
#   * retry a failed operation silently;
#   * continue past any failed check;
#   * invoke the real pilot runner;
#   * write an estimated cost anywhere a billing reading is expected.
#
# Usage, on the instance, after reading the Usage page post-launch:
#
#   EXPECTED_COMMIT=<sha> READING1_USD=<page total> \
#     bash inference/stage_b_preflight.sh
#
# Exit codes: 0 ready · 64 usage · 65 check failed · 75 re-login required.
set -euo pipefail

# ── frozen values. Changing one here is changing the experiment. ──
PROTOCOL_HASH="cc9b0c3ff329ef58"   # moved by P.3, P.5-P.9
ORDER_HASH="cfe8856c9c9167b5"
EXPECTED_CELLS=18
EXPECTED_TESTS=745
BASELINE_USD="7.16"
BASELINE_CURRENCY="USD"
BASELINE_PERIOD="September 2026"
EXPECTED_MODEL="Qwen/Qwen3.6-27B-FP8"
EXPECTED_REVISION="e89b16ebf1988b3d6befa7de50abc2d76f26eb09"
EXPECTED_MAX_MODEL_LEN=131072
SERVING_CONFIG="inference/configs/model_h2.yaml"
# The exclusion and the draw rule live in pilot_protocol.EXCLUDED_INSTANCES
# and pilot_protocol.select_tasks, which are unit-tested. This script runs
# the rule; it does not restate it.
TASKS_WANTED=3
DATASET="SWE-bench/SWE-bench_Verified"
EXPECTED_UNIVERSE=500
# Overridable only so the mock harness can clone from a local path. The
# commit is verified either way, so the origin cannot change what runs.
REPO_URL="${REPO_URL:-https://github.com/lyr-ai/agentseism.git}"
BRANCH="${BRANCH:-eval/pilot-outcome-grounded-ci}"
UV_VERSION="0.12.9"
PY_EVAL="3.13"
MIN_DRIVER=580
MIN_DISK_GB=100
MIN_GPU_MIB=80000
MIN_FREE_GPU_MIB=79000      # before vLLM starts, the card must be genuinely idle
VLLM_PORT=8000
# A bounded wait for readiness, not a retry: the operation is issued once and
# we wait for it to finish. Loading 31 GB of FP8 weights and profiling the KV
# pool took minutes on the reference host.
WAIT_VLLM_SECONDS=1800

# Exported before any Python starts, for every entry point this script has:
# the constructibility gate, the smoke test and the pilot runner all inherit
# it. mini-swe-agent's retry loop reads this variable; the default is ten
# attempts, which is what host 3 logged. The backend verifies it and refuses
# to set it, so a process can never repair its own transport policy and then
# report that the policy was in force.
export MSWEA_MODEL_RETRY_STOP_AFTER_ATTEMPT=1
# LiteLLM prices a response after generating it and a locally served model has
# no price entry, so the answer is thrown away by accounting the pilot does not
# need. This one is read at *import* time, so exporting it here is not
# belt-and-braces -- it is the only moment it can be set from outside. The
# backend also sets it on the model config, which is what actually holds.
export MSWEA_COST_TRACKING=ignore_errors

WORK="${WORK:-$HOME/agentseism-stageb}"
REPO="$WORK/repo"
STATE="$WORK/state"
STEPS="$STATE/steps"
# The run log and artifacts live outside the checkout. Appending a billing
# reading to the tracked data/runs/pilot/run.jsonl would dirty the worktree,
# and step 3 refuses to run from a dirty tree -- so the second invocation of
# this script would fail on the residue of the first.
PILOT_DIR="$WORK/pilot"

# ── output helpers ──
_hr() { printf '──── %s ────\n' "$1"; }
step() { CURRENT_STEP="$1"; printf '\n'; _hr "$1"; }
note() { printf '  %-34s %s\n' "$1" "$2"; }
ok()   { printf '  %-34s ok  %s\n' "$1" "${2:-}"; }

die() {
  printf '\n'
  printf 'PREFLIGHT FAILED\n'
  printf '  step   %s\n' "${CURRENT_STEP:-<none>}"
  printf '  reason %s\n' "$1"
  printf '\n'
  printf 'pilot_runs = 0\n'
  printf 'No registered parameter was changed and nothing was repaired\n'
  printf 'automatically. Decide, record the decision, then re-run -- the\n'
  printf 'completed steps are resumed, not repeated.\n'
  exit "${2:-65}"
}

usage() { printf 'usage: %s\n' "$1" >&2; exit 64; }

is_done()   { [ -f "$STEPS/$1.done" ]; }
mark_done() { mkdir -p "$STEPS"; date -u +%FT%TZ > "$STEPS/$1.done"; }
skip()      { note "$1" "already done -- skipping (resumable step)"; }

# `pytest -q` ends with a line like "483 passed in 21.02s", or with failures
# named before it. Parse the count instead of grepping for the literal, so a
# 484 reads as a mismatch rather than as an absence of "483 passed".
parse_passed() { grep -oE '[0-9]+ passed' "$1" | tail -1 | cut -d' ' -f1; }

disk_gb() { df -BG --output=avail "$1" | tail -1 | tr -dc '0-9'; }

# `< /proc/pid/cmdline` is checked rather than attempted: a failed redirection
# is reported by the shell before any 2>/dev/null on the same command applies,
# so the fallback would still print an error.
# pid plus its start time. A pid alone is not an identity: a server that died
# and was restarted can hold the same number, and the fingerprint would then
# describe a session that never served the smoke test.
vllm_identity() {
  printf '%s|%s' "$1" "$(ps -o lstart= -p "$1" 2>/dev/null | tr -s ' ')"
}

cmdline_of() {
  if [ -r "/proc/$1/cmdline" ]; then
    tr '\0' ' ' < "/proc/$1/cmdline"
  else
    ps -o args= -p "$1" 2>/dev/null || true
  fi
}

sha_of() { sha256sum "$1" | cut -d' ' -f1; }

# ════════════════════════════════════════════════════════════════════════
# 0. arguments, before anything is touched
# ════════════════════════════════════════════════════════════════════════
preflight_args() {
  step "0. arguments"
  [ -n "${EXPECTED_COMMIT:-}" ] || usage \
    "EXPECTED_COMMIT=<sha> is required. The commit is verified, not trusted
   from the branch head, so that a push during the run cannot change what ran."
  [ -n "${READING1_USD:-}" ] || usage \
    "READING1_USD=<page total> is required. Read the Lambda Usage page after
   this instance launched and pass the cumulative total exactly as shown.
   It is a billing reading: do not compute it from hours x rate."
  case "$READING1_USD" in
    ''|*[!0-9.]*|*.*.*) die "READING1_USD=$READING1_USD is not a plain number" 64 ;;
  esac
  ok "expected commit" "$EXPECTED_COMMIT"
  ok "reading #1" "\$$READING1_USD (manual, from the Usage page)"
  mkdir -p "$WORK" "$STATE" "$STEPS"
}

# ════════════════════════════════════════════════════════════════════════
# 1. architecture, GPU, memory, disk, Docker
# ════════════════════════════════════════════════════════════════════════
check_host() {
  step "1. host"
  local arch; arch="$(uname -m)"
  [ "$arch" = "x86_64" ] || die "uname -m is $arch, the frozen images are x86_64"
  ok "arch" "$arch"

  command -v nvidia-smi >/dev/null || die "no nvidia-smi on this host"
  local gpus; gpus="$(nvidia-smi --query-gpu=name --format=csv,noheader | wc -l)"
  [ "$gpus" -eq 1 ] || die "$gpus GPUs visible; the registered serving is tensor_parallel_size 1 on one card"
  local name mib driver
  name="$(nvidia-smi --query-gpu=name --format=csv,noheader | head -1)"
  mib="$(nvidia-smi --query-gpu=memory.total --format=csv,noheader,nounits | head -1)"
  driver="$(nvidia-smi --query-gpu=driver_version --format=csv,noheader | head -1)"
  case "$name" in *H100*) : ;; *) die "GPU is '$name', not an H100" ;; esac
  [ "$mib" -ge "$MIN_GPU_MIB" ] || die "GPU has ${mib} MiB, need >= ${MIN_GPU_MIB}"
  [ "${driver%%.*}" -ge "$MIN_DRIVER" ] || die "driver $driver < $MIN_DRIVER (CUDA 13 wheels)"
  ok "gpu" "$name  ${mib} MiB  driver $driver"

  local disk; disk="$(disk_gb /)"
  [ "${disk:-0}" -ge "$MIN_DISK_GB" ] || die "${disk} GB free on /, need >= ${MIN_DISK_GB}"
  ok "disk" "${disk} GB free"

  command -v docker >/dev/null || die "docker is not installed"
  ok "docker client" "$(docker --version)"
}

# ════════════════════════════════════════════════════════════════════════
# 2. docker group. If a re-login is needed we stop and say so -- `sg` or
#    `newgrp` would hide the fact that the shell the pilot runs in later may
#    not have the group either.
# ════════════════════════════════════════════════════════════════════════
check_docker_group() {
  step "2. docker without sudo"
  if docker info >/dev/null 2>&1; then
    ok "docker daemon" "reachable as $(id -un)"
    ok "groups" "$(id -Gn)"
    return 0
  fi
  if ! id -nG | tr ' ' '\n' | grep -qx docker; then
    note "docker daemon" "not reachable as $(id -un); adding to the docker group"
    sudo usermod -aG docker "$(id -un)" || die "usermod failed"
    printf '\n'
    printf 'RE-LOGIN REQUIRED\n'
    printf '  %s has been added to the docker group. Group membership is\n' "$(id -un)"
    # shellcheck disable=SC2016  # prose, not an expansion
    printf '  established at login, and this script will not use `newgrp` or\n'
    # shellcheck disable=SC2016
    printf '  `sg` to fake it -- the shell that runs the pilot later must have\n'
    printf '  the group for real.\n\n'
    printf '  Log out, log back in, and run this script again. Completed steps\n'
    printf '  are skipped.\n\n'
    printf 'pilot_runs = 0\n'
    exit 75
  fi
  die "in the docker group but the daemon is still unreachable: $(docker info 2>&1 | tail -1)"
}

# ════════════════════════════════════════════════════════════════════════
# 3. repository at the expected commit
# ════════════════════════════════════════════════════════════════════════
check_repo() {
  step "3. repository"
  if [ ! -d "$REPO/.git" ]; then
    git clone --branch "$BRANCH" "$REPO_URL" "$REPO" \
      || die "clone failed (private repo? configure credentials first)"
  else
    git -C "$REPO" fetch --quiet origin "$BRANCH" || die "fetch failed"
  fi
  git -C "$REPO" checkout --quiet --detach "$EXPECTED_COMMIT" \
    || die "commit $EXPECTED_COMMIT is not in $BRANCH"
  # Resolve before comparing. A short sha is what a human copies out of `git
  # log`, and comparing it against a 40-character HEAD fails on a tree that is
  # in fact correct -- which is a check that rejects the right answer.
  # `--verify` refuses an unknown or ambiguous abbreviation, so this is not a
  # loosening.
  local want head
  want="$(git -C "$REPO" rev-parse --verify --quiet "${EXPECTED_COMMIT}^{commit}")" \
    || die "$EXPECTED_COMMIT does not resolve to a commit here (unknown, or an ambiguous abbreviation)"
  head="$(git -C "$REPO" rev-parse HEAD)"
  [ "$head" = "$want" ] \
    || die "HEAD is $head, expected $want (from $EXPECTED_COMMIT)"
  # Everything downstream -- the fingerprint, the report -- records the full sha.
  EXPECTED_COMMIT="$head"
  [ -z "$(git -C "$REPO" status --porcelain)" ] \
    || die "worktree is dirty; the pilot must run from a clean frozen tree"
  ok "commit" "$head"
  ok "worktree" "clean"
  mkdir -p "$PILOT_DIR"
  if [ ! -f "$PILOT_DIR/run.jsonl" ]; then
    cp "$REPO/data/runs/pilot/run.jsonl" "$PILOT_DIR/run.jsonl" \
      || die "the frozen baseline is not in the checkout"
    ok "run log" "seeded from the frozen tree into $PILOT_DIR"
  else
    ok "run log" "$PILOT_DIR/run.jsonl (resumed, baseline not re-entered)"
  fi
  ok "serving config" "$(sha_of "$REPO/$SERVING_CONFIG" | cut -c1-16)…  $SERVING_CONFIG"
}

# ════════════════════════════════════════════════════════════════════════
# 3b. reading #1, recorded against the frozen $7.16 baseline. Early, because
#     a budget that is already past its ceiling should stop the host before it
#     downloads 31 GB of weights.
# ════════════════════════════════════════════════════════════════════════
record_reading_one() {
  step "3b. billing reading #1"
  cd "$REPO"
  PYTHONPATH=src READING1_USD="$READING1_USD" BASELINE_USD="$BASELINE_USD" \
  BASELINE_PERIOD="$BASELINE_PERIOD" BASELINE_CURRENCY="$BASELINE_CURRENCY" \
  RUN_LOG="$PILOT_DIR/run.jsonl" HOST_ID="$(hostname)@$(uptime -s 2>/dev/null || echo unknown)" \
  python3 - <<'PY' || die "reading #1 refused -- see the message above"
import os, sys
from pathlib import Path
from agentseism.budget import Budget, BudgetStop, RunLog
from agentseism.pilot import PILOT_THRESHOLDS

log = RunLog(Path(os.environ["RUN_LOG"]))
b = Budget(log, PILOT_THRESHOLDS)
base = b.baseline()
if base is None:
    sys.exit("no frozen baseline in data/runs/pilot/run.jsonl")
want = float(os.environ["BASELINE_USD"])
if abs(base["current_total"] - want) > 1e-9:
    sys.exit(f"baseline is ${base['current_total']}, expected ${want}")
if base["billing_period"] != os.environ["BASELINE_PERIOD"]:
    sys.exit(f"baseline period is {base['billing_period']!r}")
if base.get("currency") != os.environ["BASELINE_CURRENCY"]:
    sys.exit(f"baseline currency is {base.get('currency')!r}")

usd = float(os.environ["READING1_USD"])
host_id = os.environ["HOST_ID"]

# The guard is per host, not per log. The run log is carried from host to
# host -- that is what keeps the baseline frozen -- so "a reading already
# exists" would have silenced every host after the first, and this host's
# launch reading would never have been entered at all.
# `host_start` is the older name for the same record; both are honoured so a
# host that recorded one is not asked for a second.
started = [r for r in log.read()
           if r["kind"] in ("host_launch_reading", "host_start")
           and r.get("host_id") == host_id]
if started:
    print(f"  launch reading already recorded for this host "
          f"({started[0]['ts']})")
else:
    # This is taken **after** the host launched, so it already contains
    # whatever this machine has billed so far. It is not the pre-launch
    # settled total -- that is the `billing_observation` read with nothing
    # running -- and calling it a "host start total" would make it look as
    # though the launch interval had not been counted. It authorises nothing
    # and moves no threshold; the baseline is the only origin.
    log.append("host_launch_reading", host_id=host_id, page_total=usd,
               taken="after this host launched",
               billing_period=os.environ["BASELINE_PERIOD"],
               currency=os.environ["BASELINE_CURRENCY"],
               note="manual page total read after launch. NOT a budget "
                    "baseline, NOT the pre-launch settled observation, and it "
                    "does not reset the experiment's origin")
    b.record_reading(usd, source="manual",
                     billing_period=os.environ["BASELINE_PERIOD"],
                     currency=os.environ["BASELINE_CURRENCY"],
                     note=f"launch reading for host {host_id}")
spend = round(usd - base["current_total"], 2)
hosts = [r for r in log.read()
         if r["kind"] in ("host_launch_reading", "host_start")]
obs = [r for r in log.read() if r["kind"] == "billing_observation"]
print(f"  experiment_billing_baseline  ${base['current_total']:.2f}  "
      f"{base['billing_period']}  frozen {base['ts']}, never reset")
if obs:
    o = obs[-1]["current_total"]
    print(f"  host_start_total             ${o:.2f}  settled, before this host "
          f"launched, nothing running")
    print(f"  launch_reading               ${usd:.2f}  after launch  ({host_id})")
    print(f"  billed since that reading    ${round(usd - o, 2):.2f}")
else:
    print(f"  launch_reading               ${usd:.2f}  after launch  ({host_id})")
print(f"  cumulative_pilot_spend       ${spend:.2f}  "
      f"= ${usd:.2f} - ${base['current_total']:.2f}")
if len(hosts) > 1:
    print(f"  hosts so far                 {len(hosts)}; earlier hosts' cost is "
          "inside the figure above and is not forgiven")
for name, level in (("warning", PILOT_THRESHOLDS["warning"]),
                    ("no new block", PILOT_THRESHOLDS["no_new_block"]),
                    ("absolute stop", PILOT_THRESHOLDS["absolute"])):
    print(f"  {name:<28} at a page total of "
          f"${base['current_total'] + level:.2f}")
if spend < 0:
    sys.exit("reading is below the baseline; a cumulative total cannot fall")
w = PILOT_THRESHOLDS["warning"]
if spend >= w:
    print(f"  WARNING: pilot spend has already reached ${w:.0f} before run 0")
PY
  cd - >/dev/null
}

# ════════════════════════════════════════════════════════════════════════
# 4. environments, from the frozen locks
# ════════════════════════════════════════════════════════════════════════
build_envs() {
  step "4. environments from frozen locks"
  cd "$REPO"
  # From here on the instance starts spending on things the billing page has
  # not seen yet: wheels, images, 31 GB of weights. The moment is recorded so
  # `after_setup` can refuse any reading older than it.
  PYTHONPATH=src RUN_LOG="$PILOT_DIR/run.jsonl" python3 - <<'PY' || die "could not mark setup_started"
import os
from pathlib import Path
from agentseism.budget import RunLog
log = RunLog(Path(os.environ["RUN_LOG"]))
if not [r for r in log.read() if r["kind"] == "phase" and r.get("name") == "setup_started"]:
    r = log.append("phase", name="setup_started")
    print(f"  setup_started                       {r['ts']}")
else:
    print("  setup_started                       already marked (resumed run)")
PY

  if ! command -v uv >/dev/null; then
    note "uv" "installing $UV_VERSION"
    curl -LsSf "https://astral.sh/uv/$UV_VERSION/install.sh" | sh >/dev/null \
      || die "uv install failed"
    export PATH="$HOME/.local/bin:$PATH"
  fi
  ok "uv" "$(uv --version)"

  # The eval environment needs >= 3.11 (pyproject), and Ubuntu 22.04 ships
  # 3.10, so the interpreter comes from uv rather than from apt.
  if is_done env_eval && [ -x "$WORK/.venv-eval/bin/python" ]; then
    skip "eval env"
  else
    uv venv --quiet --python "$PY_EVAL" "$WORK/.venv-eval" || die "uv venv failed"
    uv pip install --quiet --python "$WORK/.venv-eval/bin/python" \
      -r inference/requirements-eval.lock.txt || die "eval lock install failed"
    uv pip install --quiet --python "$WORK/.venv-eval/bin/python" \
      --no-deps -e . || die "agentseism install failed"
    mark_done env_eval
  fi
  ok "eval env" "$("$WORK/.venv-eval/bin/python" -V)"

  # vLLM keeps the system 3.10, which is what served the reference batch.
  if is_done env_vllm && [ -x "$WORK/.venv-vllm/bin/python" ]; then
    skip "vllm env"
  else
    python3 -m venv "$WORK/.venv-vllm" || die "venv failed (apt install python3-venv)"
    "$WORK/.venv-vllm/bin/pip" install --quiet --upgrade pip || die "pip upgrade failed"
    "$WORK/.venv-vllm/bin/pip" install --quiet \
      -r inference/requirements-vllm.lock.txt || die "vllm lock install failed"
    mark_done env_vllm
  fi
  ok "vllm env" "$("$WORK/.venv-vllm/bin/python" -V)"
  ok "vllm" "$("$WORK/.venv-vllm/bin/python" -c 'import vllm;print(vllm.__version__)')"
  # vLLM builds kernels at startup and shells out to ninja; its absence is how
  # one earlier session died after the weights were already on disk.
  "$WORK/.venv-vllm/bin/python" -c 'import ninja' 2>/dev/null \
    || [ -x "$WORK/.venv-vllm/bin/ninja" ] \
    || die "ninja is missing from the vllm env; vLLM's kernel build needs it"
  ok "ninja" "present"
  cd - >/dev/null
}

# ════════════════════════════════════════════════════════════════════════
# 5. the full test suite
# ════════════════════════════════════════════════════════════════════════
run_tests() {
  step "5. full test suite"
  cd "$REPO"
  local log="$STATE/pytest.log"
  "$WORK/.venv-eval/bin/python" -m pytest -q >"$log" 2>&1 || {
    tail -25 "$log"
    die "the suite did not pass; see $log"
  }
  local passed; passed="$(parse_passed "$log")"
  [ "${passed:-0}" -eq "$EXPECTED_TESTS" ] \
    || die "$passed tests passed, expected exactly $EXPECTED_TESTS -- the tree is not the tree the count was frozen against"
  ok "pytest" "$passed passed"
  cd - >/dev/null
}

# ════════════════════════════════════════════════════════════════════════
# 6. the frozen plan
# ════════════════════════════════════════════════════════════════════════
verify_plan() {
  step "6. frozen plan"
  cd "$REPO"
  local log="$STATE/resolve_only.log"
  PYTHONPATH=src "$WORK/.venv-eval/bin/python" -m agentseism.pilot \
    --resolve-only >"$log" 2>&1 || { cat "$log"; die "--resolve-only failed"; }
  grep -q "RESOLVE-ONLY: PASS" "$log" || { cat "$log"; die "--resolve-only did not pass"; }

  local ph oh cells
  ph="$(sed -nE 's/^protocol ([0-9a-f]+).*/\1/p' "$log" | head -1)"
  oh="$(sed -nE 's/.*order ([0-9a-f]+).*/\1/p' "$log" | head -1)"
  cells="$(sed -nE 's/.*cells ([0-9]+).*/\1/p' "$log" | head -1)"
  [ "$ph" = "$PROTOCOL_HASH" ] || die "protocol hash $ph != frozen $PROTOCOL_HASH"
  [ "$oh" = "$ORDER_HASH" ]    || die "order hash $oh != frozen $ORDER_HASH"
  [ "${cells:-0}" -eq "$EXPECTED_CELLS" ] || die "$cells cells, expected $EXPECTED_CELLS"
  ok "protocol hash" "$ph"
  ok "order hash" "$oh"
  ok "cells" "$cells"
  cd - >/dev/null
}

# ════════════════════════════════════════════════════════════════════════
# 6b. can a cell actually run? Host 2 reported READY with no runner, because
#     preflight verified the environment and never verified the execution
#     path. This is that check, and it runs before the expensive steps so a
#     missing backend costs no images and no weights.
# ════════════════════════════════════════════════════════════════════════
verify_backend_constructible() {
  step "6b. real backend constructibility"
  cd "$REPO"
  PYTHONPATH=src:. "$WORK/.venv-eval/bin/python" - <<'PY' || die "the real backend is not constructible; preflight does not report READY without a runner"
import json
from agentseism.real_backend import build, BackendUnavailable
try:
    r = build(dry_run=True)
except BackendUnavailable as e:
    raise SystemExit(f"  BackendUnavailable: {e}")
for k in ("containers_created", "images_pulled", "model_requests",
          "evaluator_invocations"):
    if r[k] != 0:
        raise SystemExit(f"  the dry run performed {r[k]} {k}; it must perform none")
print(f"  agent                              ok  {r['agent']['wrapped']}")
print(f"  challenge wrapper                  ok  overrides step, exposes challenge_eligible")
print(f"  evaluator                          ok  {r['evaluator']['swebench']}  (inspected, not invoked)")
print(f"  hints                              ok  {', '.join(r['hints']['hints'])}")
print(f"  execution path                     ok  run_cell present")
print(f"  side effects                       ok  0 containers, 0 pulls, 0 model requests")
PY
  cd - >/dev/null
}

# ════════════════════════════════════════════════════════════════════════
# 8b. the frozen digests, against local image metadata only
# ════════════════════════════════════════════════════════════════════════
verify_backend_images() {
  step "8b. backend binds the frozen digests"
  cd "$REPO"
  DIGESTS="$STATE/image_digests.tsv" MODEL="$EXPECTED_MODEL" \
  BASE_URL="http://127.0.0.1:$VLLM_PORT/v1" PYTHONPATH=src:. \
  "$WORK/.venv-eval/bin/python" - <<'PY' || die "the backend cannot bind the frozen image digests or address the model"
import os
from pathlib import Path
from agentseism.real_backend import BackendConfig, _check_images, _check_transport
rows = [l.split("\t") for l in
        Path(os.environ["DIGESTS"]).read_text().splitlines() if l.strip()]
cfg = BackendConfig(image_digests={t: d for t, d in rows}, work_dir=Path("."),
                    model_base_url=os.environ["BASE_URL"],
                    model_name=os.environ["MODEL"], model_revision="")
# The address and the retry policy, checked without sending a request. Host 3
# reached the container and then failed on the first model call.
t = _check_transport(cfg)
assert t["requests_sent"] == 0
print(f"  registered_model_id                ok  {t['registered_model_id']}")
print(f"  transport_model                    ok  {t['transport_model']}")
print(f"  api_base                           ok  {t['api_base']}")
print(f"  transport attempts                 ok  {t['attempts']}  "
      f"litellm {t['retry_knobs']}")
print(f"  retry layer (env)                  ok  {t['retry_env']}")
assert t["retry_env_in_process"] == t["retry_env"], t["retry_env_in_process"]
print(f"  retry env in this process          ok  exported before Python started")
out = _check_images(cfg)
assert out["pulled"] is False
for t, d in sorted(out["images"].items()):
    print(f"  {t:<34} ok  {d.split('@')[1][:23]}…")
print("  pulled                             ok  0 -- local metadata only")
PY
  cd - >/dev/null
}

# ════════════════════════════════════════════════════════════════════════
# 7. the task draw. Mechanical: sort ascending, walk in order, pull once each,
#    record every attempt, take the first three that succeed. The rule does not
#    look at what the tasks are, and neither does this code.
# ════════════════════════════════════════════════════════════════════════
draw_tasks() {
  step "7. task draw"
  cd "$REPO"
  local universe="$STATE/universe.txt" tsv="$STATE/task_draw.tsv" drawn="$STATE/drawn.txt"

  if is_done universe && [ -s "$universe" ]; then
    skip "instance universe"
  else
    HF_HOME="$WORK/hf" DATASET="$DATASET" \
    "$WORK/.venv-eval/bin/python" - >"$universe" <<'PY' || die "could not load the instance universe"
import os
from datasets import load_dataset
ds = load_dataset(os.environ["DATASET"], split="test")
for i in sorted(ds["instance_id"]):
    print(i)
PY
    mark_done universe
  fi
  local n; n="$(wc -l < "$universe")"
  [ "$n" -eq "$EXPECTED_UNIVERSE" ] \
    || die "$DATASET has $n instances, expected $EXPECTED_UNIVERSE -- the candidate set changed and the draw is not the registered one"
  ok "universe" "$n instances  sha $(sha_of "$universe" | cut -c1-16)…"

  # The rule itself is `pilot_protocol.select_tasks` and is unit-tested; this
  # shell does not reimplement it, it runs it. One pull per candidate the rule
  # asks about, every examined candidate written with its reason, and a stop
  # -- never a relaxation -- if three distinct repositories are not found.
  if is_done draw && [ -s "$drawn" ] && [ "$(wc -l < "$drawn")" -eq "$TASKS_WANTED" ]; then
    skip "draw"
  else
    PYTHONPATH=src:. "$WORK/.venv-eval/bin/python" -m agentseism.task_draw \
      --universe "$universe" --tsv "$tsv" --drawn "$drawn" \
      --min-disk-gb "$MIN_DISK_GB" \
      || die "the task draw did not complete; every candidate examined is in $tsv"
    mark_done draw
  fi

  local repos; repos="$(cut -f2 "$tsv" | tail -n +2 | sort -u | wc -l | tr -d ' ')"
  local distinct; distinct="$(awk -F'\t' '$4=="selected"{print $2}' "$tsv" | sort -u | wc -l | tr -d ' ')"
  [ "$(wc -l < "$drawn")" -eq "$TASKS_WANTED" ] || die "the draw did not produce $TASKS_WANTED ids"
  [ "$distinct" -eq "$TASKS_WANTED" ] \
    || die "the drawn tasks span $distinct repositories, not $TASKS_WANTED"
  note "drawn" "$(tr '\n' ' ' < "$drawn")"
  ok "distinct repositories" "$distinct"
  note "examined" "$(( $(wc -l < "$tsv") - 1 )) candidates recorded in $tsv"
  note "skip reasons" "$(awk -F'\t' 'NR>1 && $4!="selected"{print $4}' "$tsv" | sort | uniq -c | tr '\n' ' ')"
  note "repositories seen" "$repos"
  cd - >/dev/null
}

# ════════════════════════════════════════════════════════════════════════
# 8. image digests
# ════════════════════════════════════════════════════════════════════════
freeze_image_digests() {
  step "8. image digests"
  local drawn="$STATE/drawn.txt" out="$STATE/image_digests.tsv"
  : > "$out"
  # Image names come from the draw record, so there is one place that knows
  # how an instance id becomes an image name.
  local iid img dig
  while read -r iid; do
    [ -n "$iid" ] || continue
    img="$(awk -F'\t' -v i="$iid" '$1==i && $4=="selected"{print $3}' "$STATE/task_draw.tsv")"
    [ -n "$img" ] || die "no image recorded for $iid in the draw log"
    dig="$(docker image inspect "$img" --format '{{index .RepoDigests 0}}' 2>/dev/null || true)"
    [ -n "$dig" ] || die "no repo digest for $img -- it cannot be frozen"
    printf '%s\t%s\n' "$iid" "$dig" >> "$out"
    ok "$iid" "$dig"
  done < "$drawn"
  mark_done digests
}

# ════════════════════════════════════════════════════════════════════════
# 9. the weights, at the frozen revision
# ════════════════════════════════════════════════════════════════════════
download_model() {
  step "9. model weights"
  local cfg_model cfg_rev
  cfg_model="$(yaml_get "$REPO/$SERVING_CONFIG" model.id)"
  cfg_rev="$(yaml_get "$REPO/$SERVING_CONFIG" model.revision)"
  [ "$cfg_model" = "$EXPECTED_MODEL" ] || die "config model is $cfg_model, frozen is $EXPECTED_MODEL"
  [ "$cfg_rev" = "$EXPECTED_REVISION" ] || die "config revision is $cfg_rev, frozen is $EXPECTED_REVISION"

  if is_done weights; then
    skip "weights"
  else
    # snapshot_download is itself idempotent: a complete local snapshot is not
    # re-fetched. The marker only avoids the round trip.
    HF_HOME="$WORK/hf" MODEL="$EXPECTED_MODEL" REV="$EXPECTED_REVISION" \
    "$WORK/.venv-vllm/bin/python" - <<'PY' || die "weight download failed"
import os
from huggingface_hub import snapshot_download
p = snapshot_download(os.environ["MODEL"], revision=os.environ["REV"])
print(f"  snapshot {p}")
PY
    mark_done weights
  fi
  ok "model" "$EXPECTED_MODEL @ $EXPECTED_REVISION"
}

yaml_get() {
  "$WORK/.venv-eval/bin/python" -c "
import sys, yaml
d = yaml.safe_load(open(sys.argv[1]))
v = d
for k in sys.argv[2].split('.'):
    v = v.get(k) if isinstance(v, dict) else None
print('' if v is None else v)" "$1" "$2"
}

# ════════════════════════════════════════════════════════════════════════
# 10. vLLM. Started, then left alone: no completion request is issued from
#     here, so model_requests stays 0 through preflight.
# ════════════════════════════════════════════════════════════════════════
start_serving() {
  step "10. vLLM"
  local pidfile="$STATE/vllm.pid" log="$STATE/vllm.log"
  if [ -f "$pidfile" ] && kill -0 "$(cat "$pidfile")" 2>/dev/null; then
    ok "vllm" "already serving, pid $(cat "$pidfile")"
    return 0
  fi

  local used
  used="$(nvidia-smi --query-gpu=memory.used --format=csv,noheader,nounits | head -1)"
  local free=$(( $(nvidia-smi --query-gpu=memory.total --format=csv,noheader,nounits | head -1) - used ))
  [ "$free" -ge "$MIN_FREE_GPU_MIB" ] \
    || die "only ${free} MiB free on the card (${used} MiB in use); a leftover process would make vLLM refuse the KV pool"
  ok "card" "${free} MiB free"

  cd "$REPO"
  # Everything comes from the config file. max_model_len is NOT negotiated
  # here: model_h2.yaml records a 65536 fallback, and this script does not take
  # it. If vLLM refuses the pool at 131072, that is a stop and a decision for a
  # human to record, because every run in the pilot must be served at one
  # length.
  PATH="$WORK/.venv-vllm/bin:$PATH" \
  HF_HOME="$WORK/hf" CONFIG="$REPO/$SERVING_CONFIG" OUTPUT_DIR="$STATE/serving" \
    nohup bash inference/start_vllm.sh >"$log" 2>&1 &
  echo $! > "$pidfile"
  cd - >/dev/null
  note "vllm" "started, pid $(cat "$pidfile"), waiting up to ${WAIT_VLLM_SECONDS}s"

  local waited=0
  until curl -sf "http://127.0.0.1:$VLLM_PORT/v1/models" >/dev/null 2>&1; do
    # The KV-pool refusal is checked before liveness: it is the reason the
    # process died, and reporting only "it exited" would invite a retry at a
    # smaller length, which is exactly what must not happen automatically.
    if grep -qi "less than desired GPU memory utilization\|No available memory for the cache" "$log"; then
      tail -20 "$log"
      die "vLLM refused the KV pool at max_model_len $EXPECTED_MAX_MODEL_LEN. Not retrying at a smaller length: the fallback is a registered decision, not an automatic one"
    fi
    kill -0 "$(cat "$pidfile")" 2>/dev/null || { tail -30 "$log"; die "vLLM exited during startup; see $log"; }
    waited=$((waited + 5)); sleep 5
    [ "$waited" -lt "$WAIT_VLLM_SECONDS" ] || { tail -20 "$log"; die "vLLM was not ready after ${WAIT_VLLM_SECONDS}s"; }
  done
  ok "vllm" "ready after ${waited}s, pid $(cat "$pidfile")"
  date -u +%FT%TZ > "$STATE/vllm.started_at"
  local ident; ident="$(vllm_identity "$(cat "$pidfile")")"
  # A new session invalidates the smoke test. The smoke run binds to the
  # server that answered it, so a restarted server has not been smoke tested
  # and the marker must not carry over.
  if [ -f "$STATE/vllm.identity" ] && [ "$ident" != "$(cat "$STATE/vllm.identity")" ]; then
    rm -f "$STEPS/smoke.done"
    note "vllm session" "new session -- the smoke test will be re-run against it"
  fi
  printf '%s' "$ident" > "$STATE/vllm.identity"
}

# ════════════════════════════════════════════════════════════════════════
# 10b. the registered smoke test (P.4). The only place the dynamic chain may
#      be demonstrated, and it runs *before* the fingerprint so the bound
#      session is one that actually served something.
# ════════════════════════════════════════════════════════════════════════
run_smoke_test() {
  step "10b. registered smoke test (P.4)"
  if is_done smoke && [ -s "$PILOT_DIR/../smoke/smoke_report.json" ]; then
    skip "smoke"
    return 0
  fi
  # The smoke task's image is pulled once and frozen like any other. It is
  # the instance P.3 excludes, so this cannot touch the draw.
  local smoke_img
  smoke_img="$(PYTHONPATH=src:. "$WORK/.venv-eval/bin/python" -c \
    "from agentseism.task_draw import image_for; from agentseism.smoke import SMOKE_TASK; print(image_for(SMOKE_TASK))")"
  # Kept out of image_digests.tsv: that file is the draw's record, and the
  # smoke task is deliberately not in the draw. The two are concatenated only
  # to hand the runner one file.
  if [ ! -s "$STATE/smoke_image.tsv" ]; then
    docker pull --platform linux/amd64 --quiet "$smoke_img" </dev/null >/dev/null \
      || die "the smoke task's image did not pull"
    local dig
    dig="$(docker image inspect "$smoke_img" --format '{{index .RepoDigests 0}}')"
    [ -n "$dig" ] || die "no repo digest for the smoke image"
    printf 'pytest-dev__pytest-10051\t%s\n' "$dig" > "$STATE/smoke_image.tsv"
    ok "smoke image" "$dig"
  fi
  cat "$STATE/image_digests.tsv" "$STATE/smoke_image.tsv" > "$STATE/smoke_digests.tsv"
  local pid before after locks cfgsha
  pid="$(cat "$STATE/vllm.pid")"
  before="$(vllm_identity "$pid")"
  [ "$before" = "$(cat "$STATE/vllm.identity")" ] \
    || die "the vLLM session changed before the smoke test even started"
  locks="$(cat "$REPO/inference/requirements-vllm.lock.txt" \
               "$REPO/inference/requirements-eval.lock.txt" | sha256sum | cut -d' ' -f1)"
  cfgsha="$(sha_of "$REPO/$SERVING_CONFIG")"

  cd "$REPO"
  PYTHONPATH=src:. HF_HOME="$WORK/hf" "$WORK/.venv-eval/bin/python" \
    -m agentseism.smoke --digests "$STATE/smoke_digests.tsv" \
    --out "$WORK/smoke" --work-dir "$WORK/smoke-work" \
    --model-base-url "http://127.0.0.1:$VLLM_PORT/v1" \
    --model-name "$EXPECTED_MODEL" --model-revision "$EXPECTED_REVISION" \
    --vllm-pid "$pid" --dependency-lock-sha256 "$locks" \
    --serving-config-sha256 "$cfgsha" \
    || die "the registered smoke test failed; the chain is not connected and no pilot run follows"
  cd - >/dev/null

  # The same session, still alive. A restart between the smoke run and the
  # fingerprint would bind the pilot to a server that never answered it.
  after="$(vllm_identity "$pid")"
  [ "$after" = "$before" ] \
    || die "the vLLM session changed during the smoke test ($before -> $after); the fingerprint would not describe the server that served it"
  ok "vllm session" "unchanged across the smoke run, pid $pid"

  # The moment `after_setup` must be newer than (P.4): the checkpoint has to
  # cover the smoke test's cost, not only setup's.
  PYTHONPATH=src RUN_LOG="$PILOT_DIR/run.jsonl" python3 - <<'PY' || die "could not mark smoke_completed"
import os
from pathlib import Path
from agentseism.budget import RunLog
log = RunLog(Path(os.environ["RUN_LOG"]))
if not [r for r in log.read() if r["kind"] == "phase" and r.get("name") == "smoke_completed"]:
    r = log.append("phase", name="smoke_completed")
    print(f"  smoke_completed                    {r['ts']}")
else:
    print("  smoke_completed                    already marked (resumed run)")
PY
  mark_done smoke
}

# ════════════════════════════════════════════════════════════════════════
# 11. the serving fingerprint. Never skipped: a restarted server is a new
#     session, and a fingerprint carried over from the previous one would
#     describe a process that no longer exists.
# ════════════════════════════════════════════════════════════════════════
fingerprint() {
  step "11. serving fingerprint"
  local pid; pid="$(cat "$STATE/vllm.pid")"
  local args; args="$(cmdline_of "$pid")"
  # If the server is a child of the wrapper, find the process actually serving.
  case "$args" in
    *api_server*) : ;;
    *) pid="$(pgrep -f 'vllm.entrypoints.openai.api_server' | head -1)"
       [ -n "$pid" ] || die "cannot find the vLLM api_server process"
       args="$(cmdline_of "$pid")"
       case "$args" in *api_server*) : ;;
         *) die "pid $pid does not look like the vLLM server: $args" ;; esac ;;
  esac

  # The three parser flags are the ones that were claimed in a config header
  # and absent from the file, so the server accepted no tool call. They are
  # checked on the live command line, which is stronger evidence than the file.
  local required=(--enable-auto-tool-choice
                  "--tool-call-parser qwen3_coder"
                  "--reasoning-parser qwen3"
                  "--max-model-len $EXPECTED_MAX_MODEL_LEN"
                  "--revision $EXPECTED_REVISION"
                  "--model $EXPECTED_MODEL")
  local r
  for r in "${required[@]}"; do
    case "$args" in *"$r"*) ok "launch arg" "$r" ;;
      *) die "the serving command line is missing: $r" ;; esac
  done

  [ "$(vllm_identity "$pid")" = "$(cat "$STATE/vllm.identity")" ] \
    || die "the vLLM session is not the one the smoke test ran against"
  local locks; locks="$(cat "$REPO/inference/requirements-vllm.lock.txt" \
                            "$REPO/inference/requirements-eval.lock.txt" | sha256sum | cut -d' ' -f1)"
  STATE="$STATE" REPO="$REPO" PID="$pid" ARGS="$args" LOCKS="$locks" \
  MODEL="$EXPECTED_MODEL" REV="$EXPECTED_REVISION" COMMIT="$EXPECTED_COMMIT" \
  VLLM_BIN="$WORK/.venv-vllm/bin/python" \
  python3 - <<'PY' || die "fingerprint could not be written"
import hashlib, json, os, subprocess, sys
from pathlib import Path

def sh(*c):
    try:
        return subprocess.run(c, capture_output=True, text=True, timeout=60).stdout.strip()
    except Exception:
        return ""

gpu = sh("nvidia-smi", "--query-gpu=uuid,name,driver_version,memory.total",
         "--format=csv,noheader").split(", ")
fp = {
    "kind": "serving_fingerprint",
    "recorded_at": sh("date", "-u", "+%FT%TZ"),
    "repo_commit": os.environ["COMMIT"],
    "model": os.environ["MODEL"],
    "model_revision": os.environ["REV"],
    "vllm_pid": int(os.environ["PID"]),
    "vllm_started_at": Path(os.environ["STATE"], "vllm.started_at").read_text().strip(),
    "launch_args": os.environ["ARGS"].strip(),
    "gpu_uuid": gpu[0] if gpu else "",
    "gpu_name": gpu[1] if len(gpu) > 1 else "",
    "driver_version": gpu[2] if len(gpu) > 2 else "",
    "gpu_memory_total": gpu[3] if len(gpu) > 3 else "",
    "cuda_version": sh("bash", "-c",
                       "nvidia-smi | sed -nE 's/.*CUDA Version: ([0-9.]+).*/\\1/p' | head -1"),
    "vllm_version": sh(os.environ["VLLM_BIN"], "-c", "import vllm;print(vllm.__version__)"),
    "torch_version": sh(os.environ["VLLM_BIN"], "-c", "import torch;print(torch.__version__)"),
    "dependency_lock_sha256": os.environ["LOCKS"],
    "serving_config_sha256": hashlib.sha256(
        Path(os.environ["REPO"], "inference/configs/model_h2.yaml").read_bytes()).hexdigest(),
    "uname": sh("uname", "-a"),
    "docker_version": sh("docker", "version", "--format", "{{.Server.Version}}"),
    "note": "a restart of vLLM invalidates this record: the pid and the "
            "session it names no longer exist, and the fingerprint is "
            "regenerated rather than reused",
}
for k in ("gpu_uuid", "driver_version", "cuda_version", "vllm_version"):
    if not fp[k]:
        sys.exit(f"fingerprint field {k} is empty; refusing to write a partial record")
out = Path(os.environ["STATE"], "serving_fingerprint.json")
body = json.dumps(fp, indent=2, sort_keys=True) + "\n"
out.write_text(body)
Path(str(out) + ".sha256").write_text(hashlib.sha256(body.encode()).hexdigest() + "\n")
print(json.dumps({k: fp[k] for k in
      ("vllm_pid", "gpu_uuid", "driver_version", "cuda_version",
       "vllm_version", "dependency_lock_sha256")}, indent=2))
PY
  ok "fingerprint" "$STATE/serving_fingerprint.json"
}

# ════════════════════════════════════════════════════════════════════════
# 12. retrieval rehearsal, on an empty artifact tree. The point is to find out
#     now whether the bundle packs, digests and unpacks -- not after 18 runs.
# ════════════════════════════════════════════════════════════════════════
rehearse_retrieval() {
  step "12. retrieval rehearsal"
  local art="$PILOT_DIR/artifacts" bundle="$STATE/retrieval_rehearsal.tgz"
  mkdir -p "$art"
  [ -z "$(ls -A "$art")" ] || die "$art is not empty before run 0"
  ok "artifact dir" "empty, as it must be before run 0"

  tar czf "$bundle" -C "$(dirname "$PILOT_DIR")" "$(basename "$PILOT_DIR")" \
    || die "could not pack the bundle"
  sha_of "$bundle" > "$bundle.sha256"
  local tmp; tmp="$(mktemp -d)"
  tar xzf "$bundle" -C "$tmp" || die "the bundle does not unpack"
  diff <(cd "$(dirname "$PILOT_DIR")" && find "$(basename "$PILOT_DIR")" -type f | sort) \
       <(cd "$tmp" && find "$(basename "$PILOT_DIR")" -type f | sort) >/dev/null \
    || die "the unpacked bundle does not match what was packed"
  rm -rf "$tmp"
  ok "bundle" "$(sha_of "$bundle" | cut -c1-16)…  packs, digests and unpacks"
  printf '  retrieval command for the operator, after the run:\n'
  printf '    scp ubuntu@<host>:%s .\n' "$bundle"
  printf '    sha256sum -c %s\n' "$(basename "$bundle").sha256"
  mark_done retrieval
}

# ════════════════════════════════════════════════════════════════════════
# 13. the report, and the stop
# ════════════════════════════════════════════════════════════════════════
write_report() {
  step "13. preflight report"
  cd "$REPO"
  # `after_setup` is deliberately NOT taken here. The only reading in the log
  # is the one entered at launch, and everything since -- wheels, images,
  # weights, serving -- is not on the billing page yet. Authorising the
  # checkpoint with it would pass the state machine while missing the entire
  # cost of setup. It is taken separately, with a number read now:
  #
  #   python -m agentseism.pilot_budget --log <run.jsonl> \
  #     --reading <page total> --checkpoint after_setup --not-before @smoke_completed
  #
  # which refuses any reading older than the smoke_completed marker,
  # so the checkpoint covers the smoke test's cost as well as setup's.
  PYTHONPATH=src RUN_LOG="$PILOT_DIR/run.jsonl" \
  "$WORK/.venv-eval/bin/python" - <<'PY' || die "could not read the budget state"
import os
from pathlib import Path
from agentseism.budget import Budget, RunLog
from agentseism.pilot import PILOT_THRESHOLDS
b = Budget(RunLog(Path(os.environ["RUN_LOG"])), PILOT_THRESHOLDS)
log = b.log
base, last = b.baseline(), log.last_billing()
mark = [r for r in log.read() if r["kind"] == "phase" and r.get("name") == "smoke_completed"]
print(f"  baseline      ${base['current_total']:.2f}")
print(f"  last reading  ${last['current_total']:.2f}   entered {last['ts']}")
print(f"  smoke ended   {mark[-1]['ts'] if mark else '(unmarked)'}")
print("  after_setup   DEFERRED -- the only reading predates setup; it cannot")
print("                authorise a checkpoint covering setup's cost")
PY
  cd - >/dev/null

  # Invariant: the smoke test ran against the stack the pilot will use. Not
  # assumed from the ordering -- compared field by field, because "the same
  # server" is exactly the thing a restart would quietly break.
  SMOKE_REPORT="$WORK/smoke/smoke_report.json" FP="$STATE/serving_fingerprint.json" \
    python3 - <<'PY' || die "the smoke test did not run against the stack the pilot will use"
import json, os, sys
from pathlib import Path
sm = json.loads(Path(os.environ["SMOKE_REPORT"]).read_text())
fp = json.loads(Path(os.environ["FP"]).read_text())
got = sm.get("serving") or {}
if not got:
    sys.exit("  the smoke report records no serving stack")
pairs = [("model_revision", "model_revision"),
         ("dependency_lock_sha256", "dependency_lock_sha256"),
         ("serving_config_sha256", "serving_config_sha256"),
         ("vllm_pid", "vllm_pid")]
for a, b in pairs:
    x, y = str(got.get(a, "")), str(fp.get(b, ""))
    if x != y:
        sys.exit(f"  smoke {a}={x!r} but fingerprint {b}={y!r}")
    print(f"  {a:<34} ok  {x[:40]}")
print(f"  {'endpoint':<34} ok  {got.get('model_base_url')}")
PY

  STATE="$STATE" COMMIT="$EXPECTED_COMMIT" RUN_LOG="$PILOT_DIR/run.jsonl" \
  SMOKE_REPORT="$WORK/smoke/smoke_report.json" \
    python3 - <<'PY' || die "report could not be written"
import hashlib, json, os
from pathlib import Path
st = Path(os.environ["STATE"])
def lines(p):
    f = st / p
    return f.read_text().splitlines() if f.exists() else []
rep = {
    "kind": "stage_b_preflight_report",
    "repo_commit": os.environ["COMMIT"],
    "drawn_tasks": lines("drawn.txt"),
    "drawn_repositories": sorted({i.rsplit("-", 1)[0] for i in lines("drawn.txt")}),
    "draw_examined": lines("task_draw.tsv")[1:],
    "image_digests": dict(l.split("\t") for l in lines("image_digests.tsv") if "\t" in l),
    "serving_fingerprint": json.loads((st / "serving_fingerprint.json").read_text()),
    "serving_fingerprint_sha256": (st / "serving_fingerprint.json.sha256").read_text().strip(),
    "run_log": os.environ["RUN_LOG"],
    "pilot_runs": 0,
    "pilot_model_requests": 0,
    "smoke": json.loads(Path(os.environ["SMOKE_REPORT"]).read_text())
             if Path(os.environ["SMOKE_REPORT"]).exists() else None,
    "after_setup_checkpoint": "deferred: requires a billing reading taken "
                              "after the smoke_completed marker",
    "backend_constructible": True,
    "unverified": [],
    "note": "pilot_model_requests is 0: the only model requests made here "
            "belong to the registered smoke test, which is not pilot "
            "evidence. Tool-call parsing is exercised by that smoke run.",
    "status": "READY_FOR_MANUAL_PILOT_CONFIRMATION",
}
body = json.dumps(rep, indent=2, sort_keys=True) + "\n"
(st / "preflight_report.json").write_text(body)
(st / "preflight_report.json.sha256").write_text(hashlib.sha256(body.encode()).hexdigest() + "\n")
print(f"  report  {st / 'preflight_report.json'}")
print(f"  sha256  {hashlib.sha256(body.encode()).hexdigest()}")
PY

  printf '\n'
  printf '════════════════════════════════════════════════════════════\n'
  printf 'READY_FOR_MANUAL_PILOT_CONFIRMATION\n'
  printf 'pilot_runs = 0\n'
  printf '════════════════════════════════════════════════════════════\n'
  printf '\n'
  printf 'Nothing further happens automatically. The registered runner is\n'
  printf 'started by a human, with the drawn ids from %s.\n' "$STATE/drawn.txt"
  printf '\n'
  printf 'Before that, confirm by hand:\n'
  printf '  * the drawn ids and every recorded pull attempt look right;\n'
  printf '  * the serving fingerprint names the pid that is serving now;\n'
  printf '  * the after_setup checkpoint is taken with a reading from NOW:\n'
  printf '      python -m agentseism.pilot_budget --log %s \\\n' "$PILOT_DIR/run.jsonl"
  printf '        --reading <page total> --checkpoint after_setup \\\n'
  printf '        --not-before @smoke_completed\n'
  printf '    The launch reading cannot authorise it: setup spent money the\n'
  printf '    page had not seen when that number was read.\n'
  printf '  * then a further fresh reading before block 1 -- one reading\n'
  printf '    authorises one block.\n'
}

main() {
  preflight_args
  check_host
  check_docker_group
  check_repo
  record_reading_one
  build_envs
  run_tests
  verify_plan
  verify_backend_constructible
  draw_tasks
  freeze_image_digests
  verify_backend_images
  download_model
  start_serving
  run_smoke_test
  fingerprint
  rehearse_retrieval
  write_report
}

# Sourced with STAGE_B_LIB_ONLY=1 the file defines its functions and runs
# nothing, so the pure ones can be tested without a GPU.
if [ -z "${STAGE_B_LIB_ONLY:-}" ]; then
  main "$@"
fi

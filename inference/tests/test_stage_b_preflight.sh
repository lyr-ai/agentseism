#!/usr/bin/env bash
# Mock/dry-run tests for inference/stage_b_preflight.sh.
#
# No GPU, no Docker, no network, no model. A fake host is built from shims and
# the script is run end to end against it. Every negative scenario asserts the
# same thing in a different way: the script stops rather than adapts.
#
#   bash inference/tests/test_stage_b_preflight.sh
#
# shellcheck disable=SC2030,SC2031
# Each scenario runs in its own ( ) subshell so that one mock environment
# cannot leak into the next. That isolation is the design, not an accident.
set -uo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(cd "$HERE/../.." && pwd)"
SCRIPT="$ROOT/inference/stage_b_preflight.sh"
REAL_PYTHON="${REAL_PYTHON:-$ROOT/.venv/bin/python}"
COMMIT="${COMMIT:-$(git -C "$ROOT" rev-parse HEAD)}"
BRANCH_UNDER_TEST="${BRANCH_UNDER_TEST:-$(git -C "$ROOT" rev-parse --abbrev-ref HEAD)}"

# shellcheck source=inference/tests/mock_stage_b_env.sh
. "$HERE/mock_stage_b_env.sh"

# Each scenario runs in its own ( ) so its mock environment cannot leak into
# the next one -- which means a shell variable counter would not survive it.
# Results go to a file instead.
# shellcheck disable=SC2030,SC2031  # the subshell isolation is the point
RESULTS="$(mktemp)"
ok()   { printf '  \033[32mPASS\033[0m  %s\n' "$1"; echo PASS >> "$RESULTS"; }
bad()  { printf '  \033[31mFAIL\033[0m  %s\n' "$1"; echo FAIL >> "$RESULTS"; }

# run_scenario <name> -- remaining env comes from the caller's exported vars.
# Prints nothing; leaves $OUT (combined output) and $RC (exit code).
# A mock server left alive by the previous scenario would answer the next
# scenario's readiness probe, and the OOM case would then look like a success.
kill_mock_servers() {
  /usr/bin/pkill -f 'vllm.entrypoints.openai.api_server' >/dev/null 2>&1 || true
}
trap 'kill_mock_servers; rm -f "$RESULTS"' EXIT

run_scenario() {
  kill_mock_servers
  SANDBOX="$(mktemp -d)"
  build_mock_host "$SANDBOX" "$REAL_PYTHON"
  OUT="$(cd "$ROOT" && env PATH="$SANDBOX/bin:$PATH" \
        WORK="$SANDBOX/work" \
        REPO_URL="$ROOT" BRANCH="$BRANCH_UNDER_TEST" \
        EXPECTED_COMMIT="${SCENARIO_COMMIT:-$COMMIT}" \
        READING1_USD="${SCENARIO_READING:-7.16}" \
        MOCK_SUDO_LOG="$SANDBOX/sudo.log" \
        MOCK_PULLED="$SANDBOX/pulled.txt" \
        bash "$SCRIPT" 2>&1)"
  RC=$?
  kill_mock_servers
}

_dump() { printf '%s\n' "$OUT" | tail -12 | sed 's/^/        /'; }
expect_rc() {
  if [ "$RC" -eq "$1" ]; then ok "$2"; else bad "$2 (rc=$RC, wanted $1)"; _dump; fi
}
expect_out() {
  if printf '%s' "$OUT" | grep -qF -- "$1"; then ok "$2"; else bad "$2 (missing: $1)"; _dump; fi
}
expect_not_out() {
  if printf '%s' "$OUT" | grep -qF -- "$1"; then bad "$2 (present: $1)"; else ok "$2"; fi
}
# assert_true/false <$?> <message>. Written this way rather than A && ok || bad,
# which is not if-then-else: if `ok` ever returned non-zero the failure branch
# would run too.
assert_true()  { if [ "$1" -eq 0 ]; then ok "$2"; else bad "$2"; fi; }
assert_false() { if [ "$1" -ne 0 ]; then ok "$2"; else bad "$2"; fi; }

printf '\n──── static properties ────\n'
grep -q -- "--execute-registered-pilot" "$SCRIPT"
assert_false $? "never names --execute-registered-pilot"
grep -qE -- "--backend[[:space:]]+real" "$SCRIPT"
assert_false $? "never selects --backend real"
# An invocation, not the sentence that explains why there is none.
grep -qE "^[[:space:]]*(newgrp|sg)[[:space:]]" "$SCRIPT"
assert_false $? "no newgrp/sg bypass"
grep -q "Not retrying at a smaller length" "$SCRIPT"
assert_true $? "refuses the smaller-max_model_len fallback in so many words"
# A checkpoint is a reading, not a moment: preflight must not take after_setup
# on the number that was read before setup spent anything.
grep -qF 'b.check("after_setup")' "$SCRIPT"
assert_false $? "preflight never authorises after_setup itself"
grep -q "setup_started" "$SCRIPT"
assert_true $? "preflight marks when setup began"
# The draw is executed by src/agentseism/task_draw.py, which is the only place
# that touches Docker for an image.
DRAW="$ROOT/src/agentseism/task_draw.py"
if [ "$(grep -c '"docker", "pull"' "$DRAW")" -eq 1 ]; then
  ok "exactly one docker pull call site (no retry loop)"
else
  bad "more than one docker pull call site"
fi
if [ "$(grep -c "docker_pull" "$DRAW")" -eq 2 ]; then
  ok "docker_pull is defined once and called once"
else
  bad "docker_pull appears $(grep -c "docker_pull" "$DRAW") times, expected 2"
fi
if [ "$(grep -cE "^ *(if docker pull|docker pull)" "$SCRIPT")" -eq 0 ]; then
  ok "the shell does not pull images itself"
else
  bad "the shell still pulls images"
fi

printf '\n──── 1. happy path (real pytest, real resolve-only) ────\n'
( run_scenario
  expect_rc 0 "exits 0"
  expect_out "READY_FOR_MANUAL_PILOT_CONFIRMATION" "reaches the ready banner"
  expect_out "pilot_runs = 0" "reports pilot_runs = 0"
  expect_out "614 passed" "runs the real suite and sees 614"
  expect_out "cfe8856c9c9167b5" "verifies the order hash"
  expect_out "5f4b95c9a250fccf" "verifies the protocol hash (moved by P.3)"
  expect_out "pilot_spend   \$0.00" "computes spend against the frozen baseline"
  expect_out "after_setup   DEFERRED" "does not authorise after_setup with the launch reading"
  expect_out "setup began" "records when setup started"
  expect_out "--tool-call-parser qwen3_coder" "checks the parser flags on the live command line"
  REPORT="$SANDBOX/work/state/preflight_report.json"
  "$REAL_PYTHON" - "$REPORT" <<'REPORTCHECK'
import json, sys
r = json.load(open(sys.argv[1]))
assert r["status"] == "READY_FOR_MANUAL_PILOT_CONFIRMATION", r["status"]
assert r["pilot_runs"] == 0 and r["model_requests"] == 0
assert len(r["drawn_tasks"]) == 3, r["drawn_tasks"]
assert len(r["drawn_repositories"]) == 3, r["drawn_repositories"]
assert len(r["image_digests"]) == 3, r["image_digests"]
assert r["serving_fingerprint"]["vllm_version"] == "0.28.0"
assert r["serving_fingerprint"]["model_revision"].startswith("e89b16eb")
assert r["after_setup_checkpoint"].startswith("deferred")
REPORTCHECK
  assert_true $? "report is well formed: 3 tasks, 3 digests, 0 runs"
) 

printf '\n──── 2. the registered exclusion is exercised, not assumed ────\n'
( export MOCK_UNIVERSE_INCLUDES_EXCLUDED=1
  run_scenario
  expect_rc 0 "still ready"
  expect_out "excluded_registered" "pytest-dev__pytest-10051 is excluded"
  grep -q "excluded_registered" "$SANDBOX/work/state/task_draw.tsv"
  assert_true $? "the exclusion is recorded in the draw log"
  grep -q "pytest-dev__pytest-10051" "$SANDBOX/work/state/drawn.txt"
  assert_false $? "the excluded instance is not drawn"
)

printf '\n──── 3. host checks stop the run ────\n'
( export MOCK_GPU_NAME="NVIDIA A100-SXM4-80GB"; run_scenario
  expect_rc 65 "wrong GPU stops"; expect_out "not an H100" "says which card it found" )
( export MOCK_DISK_GB=40; run_scenario
  expect_rc 65 "small disk stops"; expect_out "need >= 100" "states the requirement" )
( export MOCK_DRIVER="614.195.03"; run_scenario
  expect_rc 65 "old driver stops"; expect_out "< 580" "states the requirement" )

printf '\n──── 4. docker group: stop, never bypass ────\n'
( export MOCK_DOCKER_DENIED=1; run_scenario
  expect_rc 75 "asks for a re-login"
  expect_out "RE-LOGIN REQUIRED" "says so plainly"
  expect_out "pilot_runs = 0" "still reports zero runs"
  grep -q "usermod -aG docker" "$SANDBOX/sudo.log"
  assert_true $? "adds the user to the group" )

printf '\n──── 5. arguments ────\n'
( kill_mock_servers
  SANDBOX="$(mktemp -d)"; build_mock_host "$SANDBOX" "$REAL_PYTHON"
  OUT="$(cd "$ROOT" && env PATH="$SANDBOX/bin:$PATH" WORK="$SANDBOX/work" \
        REPO_URL="$ROOT" BRANCH="$BRANCH_UNDER_TEST" EXPECTED_COMMIT="$COMMIT" \
        bash "$SCRIPT" 2>&1)"; RC=$?
  expect_rc 64 "missing READING1_USD is a usage error"
  expect_out "do not compute it from hours x rate" "says what a reading is" )
( export SCENARIO_READING="about twenty dollars"; run_scenario
  expect_rc 64 "a non-numeric reading is refused" )
( export SCENARIO_COMMIT="0000000000000000000000000000000000000000"; run_scenario
  expect_rc 65 "an unknown commit stops" )
# A short sha is what a human copies out of `git log`, and it must be accepted:
# the first real host run failed here against a tree that was correct.
( SCENARIO_COMMIT="$(git -C "$ROOT" rev-parse --short HEAD)"; export SCENARIO_COMMIT
  export MOCK_PYTEST_PASSED=614
  run_scenario
  expect_rc 0 "a short commit sha is accepted"
  expect_out "$COMMIT" "the record carries the resolved full sha" )

printf '\n──── 6. the frozen counts ────\n'
( export MOCK_PYTEST_PASSED=503; run_scenario
  expect_rc 65 "613 passed is not 614"
  expect_out "expected exactly 614" "says what it wanted" )
( export MOCK_PYTEST_PASSED=614 MOCK_UNIVERSE_N=499; run_scenario
  expect_rc 65 "a changed candidate universe stops"
  expect_out "the draw is not the registered one" "explains why" )

printf '\n──── 6a. a missing runner must not report READY ────\n'
# Host 2's defect, as a scenario. run_cell exists now, so the gate is provoked
# by a dependency the backend needs being unimportable -- which is the general
# case, not the one absence that happened to occur that day.
( export MOCK_PYTEST_PASSED=614 MOCK_BACKEND_BROKEN=1
  run_scenario
  expect_rc 65 "preflight fails when the backend is not constructible"
  expect_out "real backend is not constructible" "says why"
  expect_out "BackendUnavailable" "names the failure"
  expect_out "minisweagent" "names the missing piece"
  expect_not_out "READY_FOR_MANUAL_PILOT_CONFIRMATION" "never reports READY"
  expect_out "pilot_runs = 0" "zero runs"
  if [ -f "$SANDBOX/work/state/drawn.txt" ]; then
    bad "it drew tasks despite having no runner"
  else
    ok "it stops before the expensive steps -- no draw, no weights"
  fi )

printf '\n──── 6b. repository diversity (amendment P.3) ────\n'
( run_scenario
  expect_rc 0 "draws across repositories"
  expect_out "distinct repositories              ok  3" "three distinct repositories"
  TSV="$SANDBOX/work/state/task_draw.tsv"
  DRAWN="$SANDBOX/work/state/drawn.txt"
  # The head of the universe is 200 astropy instances: under the version-1
  # rule all three slots were astropy.
  if [ "$(cut -f2 "$DRAWN" | sed -E 's/-[0-9]+$//' | sort -u | wc -l | tr -d ' ')" -eq 3 ]; then
    ok "the drawn ids span three repositories"
  else
    bad "the drawn ids do not span three repositories: $(tr '\n' ' ' < "$DRAWN")"
  fi
  if [ "$(head -1 "$DRAWN")" = "astropy__astropy-00001" ]; then
    ok "the first pullable id of the first repository is taken"
  else
    bad "first drawn is $(head -1 "$DRAWN"), expected astropy__astropy-00001"
  fi
  if [ "$(sed -n 2p "$DRAWN")" = "django__django-00001" ]; then
    ok "it keeps scanning past the whole first repository"
  else
    bad "second drawn is $(sed -n 2p "$DRAWN"), expected django__django-00001"
  fi
  DUP="$(awk -F'\t' '$4=="duplicate_repository"' "$TSV" | wc -l | tr -d ' ')"
  # 199 astropy after the first, then 99 django after the first, then the
  # matplotlib head completes the draw.
  if [ "$DUP" -eq 298 ]; then
    ok "every duplicate is written to the record ($DUP rows)"
  else
    bad "expected 298 duplicate_repository rows, found $DUP"
  fi
  expect_out "duplicate_repository" "the skip reasons are reported"
  # Nothing but order, exclusion, repository and pull success may move a draw.
  if [ "$(awk -F'\t' '$4=="selected"{print $1}' "$TSV" | tr '\n' ' ')" \
     = "$(tr '\n' ' ' < "$DRAWN")" ]; then
    ok "the record and the draw agree, in order"
  else
    bad "the selected rows do not match drawn.txt"
  fi )

( export MOCK_UNIVERSE_SINGLE_REPO=1; run_scenario
  expect_rc 65 "one repository is not three"
  expect_out "not relaxed" "refuses to relax the rule"
  expect_out "pilot_runs = 0" "zero runs"
  if [ -s "$SANDBOX/work/state/task_draw.tsv" ]; then
    ok "the failed draw is still recorded"
  else
    bad "nothing was written for the failed draw"
  fi
  if [ -s "$SANDBOX/work/state/drawn.txt" ]; then
    bad "a partial draw was written"
  else
    ok "no partial draw is written"
  fi )

printf '\n──── 7. image pulls are recorded, not retried ────\n'
( export MOCK_PYTEST_PASSED=614 MOCK_PULL_FAIL_ALL=1; run_scenario
  expect_rc 65 "no images means no run"
  expect_out "0 of 3 distinct repositories" "reports the shortfall"
  n="$(grep -c "pull_failed" "$SANDBOX/work/state/task_draw.tsv")"
  if [ "$n" -eq 500 ]; then ok "every failed attempt is recorded ($n)"; else bad "expected 500 pull_failed rows, found $n"; fi )
( export MOCK_PYTEST_PASSED=614 MOCK_PULL_FAIL_GLOB="*astropy_1776_astropy-0000[12]*"; run_scenario
  expect_rc 0 "walks past failures to the next candidates"
  grep -q "astropy__astropy-00001" "$SANDBOX/work/state/drawn.txt"
  assert_false $? "failed candidates are skipped, in order"
  head -1 "$SANDBOX/work/state/drawn.txt" | grep -q "astropy__astropy-00003"
  assert_true $? "the first success is the first drawn" )

printf '\n──── 8. vLLM refuses the KV pool: stop, do not shrink ────\n'
( export MOCK_PYTEST_PASSED=614 MOCK_VLLM_OOM=1; run_scenario
  expect_rc 65 "an OOM at 131072 stops"
  expect_out "Not retrying at a smaller length" "refuses the automatic fallback"
  expect_not_out "65536" "never tries the smaller length"
  expect_out "pilot_runs = 0" "zero runs" )
( export MOCK_PYTEST_PASSED=614 MOCK_GPU_USED_MIB=40000; run_scenario
  expect_rc 65 "a busy card stops before vLLM starts"
  expect_out "leftover process" "names the likely cause" )

printf '\n──── 9. resume is idempotent ────\n'
( kill_mock_servers
  SANDBOX="$(mktemp -d)"; build_mock_host "$SANDBOX" "$REAL_PYTHON"
  runit() { (cd "$ROOT" && env PATH="$SANDBOX/bin:$PATH" WORK="$SANDBOX/work" \
      REPO_URL="$ROOT" BRANCH="$BRANCH_UNDER_TEST" EXPECTED_COMMIT="$COMMIT" \
      READING1_USD=7.16 MOCK_PYTEST_PASSED=614 MOCK_PULLED="$SANDBOX/pulled.txt" \
      bash "$SCRIPT" 2>&1); }
  runit >/dev/null; rc1=$?
  pulls1="$(wc -l < "$SANDBOX/pulled.txt")"
  # A live server from the first run would be reused; kill it so the second
  # run is the resume path and not a no-op.
  [ -f "$SANDBOX/work/state/vllm.pid" ] && kill "$(cat "$SANDBOX/work/state/vllm.pid")" 2>/dev/null
  rm -f "$SANDBOX/work/state/vllm.pid"
  second="$(runit)"; rc2=$?
  pulls2="$(wc -l < "$SANDBOX/pulled.txt")"
  if [ "$rc1" -eq 0 ] && [ "$rc2" -eq 0 ]; then ok "both runs reach ready (rc1=$rc1 rc2=$rc2)"; else bad "both runs reach ready (rc1=$rc1 rc2=$rc2)"; fi
  printf '%s' "$second" | grep -q "already done -- skipping"
  assert_true $? "skips completed steps"
  if [ "$pulls1" -eq "$pulls2" ]; then ok "no image is pulled twice ($pulls1 -> $pulls2)"; else bad "no image is pulled twice ($pulls1 -> $pulls2)"; fi
  printf '%s' "$second" | grep -q "resumed, baseline not re-entered"
  assert_true $? "the baseline is not re-entered"
  printf '%s' "$second" | grep -q "reading already recorded"
  assert_true $? "reading #1 is not entered twice"
  printf '%s' "$second" | grep -q "11. serving fingerprint"
  assert_true $? "the fingerprint is regenerated on every run"
  if [ -f "$SANDBOX/work/state/vllm.pid" ]; then ok "a restart produces a new session"; else bad "a restart produces a new session"; fi
  if [ -f "$SANDBOX/work/state/vllm.pid" ]; then
    kill "$(cat "$SANDBOX/work/state/vllm.pid")" 2>/dev/null || true
  fi )

printf '\n──── 10. the frozen tree is left clean ────\n'
if [ -z "$(git -C "$ROOT" status --porcelain data/runs/pilot)" ]; then ok "data/runs/pilot is untouched by the tests"; else bad "data/runs/pilot is untouched by the tests"; fi

PASS="$(grep -c PASS "$RESULTS" || true)"
FAIL="$(grep -c FAIL "$RESULTS" || true)"
printf '\n════════════════════════════════════════════\n'
printf '  %s passed, %s failed\n' "$PASS" "$FAIL"
printf '════════════════════════════════════════════\n'
[ "$FAIL" -eq 0 ]

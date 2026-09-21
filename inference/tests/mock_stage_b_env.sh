#!/usr/bin/env bash
# Builds a fake host for inference/stage_b_preflight.sh: shim binaries on PATH
# and two shim interpreters. Sourced by test_stage_b_preflight.sh.
#
# The shims answer with whatever the scenario sets, so a scenario can make the
# card an A100, every pull fail, the suite report 482, or vLLM refuse the KV
# pool -- and the assertion is that the script stops rather than adapts.
# Sourced, so it sets no shell options: `set -e` here would leak into the test
# runner, where a failing grep is an expected outcome rather than an abort. The
# builder body is a ( ) subshell so it can be strict without leaking.

build_mock_host() (
  set -euo pipefail
  local root="$1" real_python="$2"
  local bin="$root/bin"
  mkdir -p "$bin" "$root/work/state/steps" "$root/work/.venv-eval/bin" \
           "$root/work/.venv-vllm/bin"

  cat > "$bin/nvidia-smi" <<'EOF'
#!/usr/bin/env bash
name="${MOCK_GPU_NAME:-NVIDIA H100 PCIe}"
total="${MOCK_GPU_MIB:-81559}"
used="${MOCK_GPU_USED_MIB:-0}"
drv="${MOCK_DRIVER:-580.105.08}"
case "${1:-}" in
  --query-gpu=name) echo "$name" ;;
  --query-gpu=memory.total) echo "$total" ;;
  --query-gpu=memory.used) echo "$used" ;;
  --query-gpu=driver_version) echo "$drv" ;;
  --query-gpu=uuid,name,driver_version,memory.total)
      echo "GPU-mock-0000-0000, $name, $drv, $total MiB" ;;
  --query-gpu=name,memory.total,driver_version) echo "$name, $total MiB, $drv" ;;
  *) echo "| NVIDIA-SMI $drv   Driver Version: $drv   CUDA Version: ${MOCK_CUDA:-13.0} |" ;;
esac
EOF

  # The test host is an arm64 Mac; the script checks for x86_64 because the
  # frozen SWE-bench images are x86_64, so uname is a shim too.
  cat > "$bin/uname" <<'EOF'
#!/usr/bin/env bash
case "${1:-}" in
  -m) echo "${MOCK_ARCH:-x86_64}" ;;
  -a) echo "Linux mock 6.8.0-1046-nvidia #49~22.04.1-Ubuntu SMP x86_64 GNU/Linux" ;;
  *)  echo "Linux" ;;
esac
EOF

  cat > "$bin/docker" <<'EOF'
#!/usr/bin/env bash
case "${1:-}" in
  --version) echo "Docker version 29.2.1, build a5c7197" ;;
  info) [ -n "${MOCK_DOCKER_DENIED:-}" ] && { echo "permission denied" >&2; exit 1; }; echo "Server Version: 29.2.1" ;;
  version) echo "29.2.1" ;;
  pull)
    img="${*: -1}"
    [ -n "${MOCK_PULL_FAIL_ALL:-}" ] && exit 1
    case "$img" in ${MOCK_PULL_FAIL_GLOB:-__never__}) exit 1 ;; esac
    echo "$img" >> "${MOCK_PULLED:-/dev/null}"; exit 0 ;;
  image)
    # image inspect <img> --format ...
    img="$3"
    [ -n "${MOCK_NO_DIGEST:-}" ] && exit 1
    short="${img##*/}"; echo "docker.io/swebench/${short%%:*}@sha256:$(printf '%s' "$img" | cksum | cut -d' ' -f1)0000" ;;
  run) exit 0 ;;
  *) exit 0 ;;
esac
EOF

  cat > "$bin/df" <<'EOF'
#!/usr/bin/env bash
echo "Avail"
echo "${MOCK_DISK_GB:-968}G"
EOF

  cat > "$bin/sha256sum" <<'EOF'
#!/usr/bin/env bash
if [ "$#" -eq 0 ]; then shasum -a 256 | cut -d' ' -f1 | sed 's/$/  -/'; else
for f in "$@"; do printf '%s  %s\n' "$(shasum -a 256 "$f" | cut -d' ' -f1)" "$f"; done; fi
EOF

  # Readiness follows the process, not a timer: answering "ready" before the
  # server has exec'd let the fingerprint read the wrapper's command line
  # instead of the server's, which is a bug this mock has to be able to show.
  cat > "$bin/curl" <<'EOF'
#!/usr/bin/env bash
case "$*" in
  *v1/models*)
    [ -n "${MOCK_VLLM_NEVER_READY:-}" ] && exit 7
    /usr/bin/pgrep -f 'vllm.entrypoints.openai.api_server' >/dev/null 2>&1 || exit 7
    exit 0 ;;
  *) exit 0 ;;
esac
EOF

  cat > "$bin/sudo" <<'EOF'
#!/usr/bin/env bash
echo "[mock sudo] $*" >> "${MOCK_SUDO_LOG:-/dev/null}"
exit 0
EOF

  # No pgrep shim: the script's fallback search must find (or fail to find) a
  # real process.

  # The eval interpreter is the real local venv, except that a scenario can
  # dictate the pytest count without paying 20 seconds for a real run.
  # A dependency the backend needs, made unimportable. This is how the
  # missing-backend scenario is provoked now that run_cell exists: the gate
  # must refuse for any reason the backend cannot be constructed, not only
  # for the one absence that happened to occur on host 2.
  mkdir -p "$root/broken/minisweagent"
  printf '%s\n' 'raise ImportError("mock: minisweagent unavailable")' \
    > "$root/broken/minisweagent/__init__.py"

  cat > "$root/work/.venv-eval/bin/python" <<EOF
#!/usr/bin/env bash
REAL="$real_python"
BROKEN="$root/broken"
if [ "\${1:-}" = "-m" ] && [ "\${2:-}" = "pytest" ] && [ -n "\${MOCK_PYTEST_PASSED:-}" ]; then
  echo "\${MOCK_PYTEST_PASSED} passed in 1.00s"
  [ -n "\${MOCK_PYTEST_FAIL:-}" ] && exit 1
  exit 0
fi
if [ -n "\${MOCK_BACKEND_BROKEN:-}" ]; then
  export PYTHONPATH="\$BROKEN:\${PYTHONPATH:-}"
fi
exec "\$REAL" "\$@"
EOF

  # The vLLM interpreter answers version probes and, for `-m`, becomes a
  # long-lived process whose argv still carries the serving flags -- which is
  # what the fingerprint reads.
  cat > "$root/work/.venv-vllm/bin/python" <<EOF
#!/usr/bin/env bash
REAL="$real_python"
EOF
  cat >> "$root/work/.venv-vllm/bin/python" <<'EOF'
case "${1:-}" in
  -V|--version) echo "Python 3.10.12" ;;
  -c) case "$2" in
        # start_vllm.sh reads every serving parameter out of the YAML through
        # `python3 -c`, so that one has to be a real interpreter.
        *yaml*)  exec "$REAL" "$@" ;;
        *vllm*)  [ -n "${MOCK_NO_VLLM:-}" ] && exit 1; echo "${MOCK_VLLM_VERSION:-0.28.0}" ;;
        *torch*) echo "2.13.0" ;;
        *ninja*) [ -n "${MOCK_NO_NINJA:-}" ] && exit 1; exit 0 ;;
        *) exit 0 ;;
      esac ;;
  -) cat >/dev/null; echo "  snapshot /mock/hf/snapshot"; exit 0 ;;
  -m) shift
      if [ -n "${MOCK_VLLM_OOM:-}" ]; then
        echo "ValueError: Free memory on device cuda:0 (7.06/79.18 GiB) on startup is less than desired GPU memory utilization (0.9, 71.26 GiB)."
        exit 1
      fi
      # A loop body, not `sleep`: `sh -c 'sleep 600'` is exec-optimised into
      # sleep itself and the argv the fingerprint reads would be lost.
      exec /bin/sh -c 'while :; do sleep 1; done' "$@" ;;
  *) exit 0 ;;
esac
EOF
  ln -sf python "$root/work/.venv-eval/bin/python3"
  ln -sf python "$root/work/.venv-vllm/bin/python3"
  chmod +x "$bin"/* "$root/work/.venv-eval/bin/python" "$root/work/.venv-vllm/bin/python"

  # Environments and the instance universe are pre-marked: building a real
  # vLLM env or downloading a dataset is not what these scenarios test, and
  # skipping them exercises the resume path at the same time.
  date -u +%FT%TZ > "$root/work/state/steps/env_eval.done"
  date -u +%FT%TZ > "$root/work/state/steps/env_vllm.done"
  date -u +%FT%TZ > "$root/work/state/steps/universe.done"
  # A universe shaped like the real one: ascending, and with one repository
  # large enough at the head to have filled the whole draw under the version-1
  # rule. MOCK_UNIVERSE_SINGLE_REPO collapses it to one repository, which the
  # P.3 rule must refuse rather than relax.
  : > "$root/work/state/universe.txt"
  local want="${MOCK_UNIVERSE_N:-500}" i n
  if [ -n "${MOCK_UNIVERSE_SINGLE_REPO:-}" ]; then
    for i in $(seq 1 "$want"); do
      printf 'astropy__astropy-%05d\n' "$i" >> "$root/work/state/universe.txt"
    done
  else
    n=$(( want * 2 / 5 ))          # astropy holds the head of the list
    local rest=$(( want - n )) each
    each=$(( rest / 3 ))
    {
      for i in $(seq 1 "$n");                    do printf 'astropy__astropy-%05d\n' "$i"; done
      for i in $(seq 1 "$each");                 do printf 'django__django-%05d\n' "$i"; done
      for i in $(seq 1 "$each");                 do printf 'matplotlib__matplotlib-%05d\n' "$i"; done
      for i in $(seq 1 $(( rest - 2 * each ))); do printf 'sympy__sympy-%05d\n' "$i"; done
    } >> "$root/work/state/universe.txt"
  fi
  if [ -n "${MOCK_UNIVERSE_INCLUDES_EXCLUDED:-}" ]; then
    # The excluded instance goes first so the exclusion is actually exercised.
    { echo "pytest-dev__pytest-10051"; cat "$root/work/state/universe.txt"; } \
      | head -n "$want" > "$root/work/state/universe.txt.new"
    mv "$root/work/state/universe.txt.new" "$root/work/state/universe.txt"
  fi
)

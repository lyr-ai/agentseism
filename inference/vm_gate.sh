#!/usr/bin/env bash
# The gate for a colocated GPU VM. Run it on the VM, before any flask data.
#
# The migration this gate belongs to removes an experimental variable rather
# than chasing a better one. Two RunPod network paths failed in two different
# ways -- HTTP proxy: Cloudflare 524 on any non-streaming call past ~120 s;
# direct TCP: long streams dying 2 times in 3, once as a silent ReadTimeout and
# once as a RemoteProtocolError, with a healthy run in between proving the
# endpoint itself was fine. A third region would be a bet on the next path.
#
# Colocating the agent, the SWE-bench containers and vLLM on one host deletes
# the path instead of hardening it.
set -uo pipefail

BASE="${BASE:-http://127.0.0.1:8000/v1}"
KEY="${VLLM_API_KEY:-not-needed}"
FAIL=0
note() { printf '%-34s %s\n' "$1" "$2"; }

echo "──── 1. the card ────"
nvidia-smi --query-gpu=name,memory.total,driver_version --format=csv,noheader || FAIL=1

echo
echo "──── 2. docker, on this host ────"
# The reason for the whole migration: SWE-bench containers have to run here.
if docker run --rm hello-world >/dev/null 2>&1; then
  note "docker run hello-world" "ok"
else
  note "docker run hello-world" "FAIL -- SWE-bench containers cannot run here"; FAIL=1
fi
DISK=$(df -BG --output=avail / | tail -1 | tr -dc '0-9')
note "free disk" "${DISK} GB $([ "${DISK:-0}" -ge 100 ] && echo ok || { echo 'FAIL -- want >= 100'; FAIL=1; })"

echo
echo "──── 3-6. the endpoint, over localhost ────"
python3 inference/transport_gate.py --base "$BASE" --key "$KEY" --long-tokens 8000 || FAIL=1

echo
echo "──── 7. the realistic worst case, three times ────"
# 4954 tokens was the largest single completion anywhere in the H2 data. This is
# that observed worst case, not a bound: the agent sets no max_tokens, so a
# longer completion is possible and this gate does not rule one out.
python3 - "$BASE" "$KEY" <<'PY' || FAIL=1
import sys, time, httpx
base, key = sys.argv[1], sys.argv[2]
headers = {"Authorization": f"Bearer {key}", "Content-Type": "application/json"}
body = {"model": None, "messages": [{"role": "user", "content": "Count from 1 to 20000, one per line."}],
        "temperature": 0, "max_tokens": 5000, "ignore_eos": True, "stream": True,
        "stream_options": {"include_usage": True}}
with httpx.Client(timeout=httpx.Timeout(connect=15.0, read=90.0, write=30.0, pool=15.0)) as c:
    body["model"] = c.get(f"{base}/models", headers=headers).json()["data"][0]["id"]
    bad = 0
    for i in range(3):
        t, first, got, worst, last = time.time(), None, 0, 0.0, time.time()
        try:
            with c.stream("POST", f"{base}/chat/completions", headers=headers, json=body) as r:
                for chunk in r.iter_bytes():
                    now = time.time()
                    if first is None: first = now - t
                    worst = max(worst, now - last); last = now
                    got += len(chunk)
            print(f"  run {i}: ok   ttfb {first:.1f}s  {got/1024:.0f} KB  "
                  f"worst gap {worst:.1f}s  total {time.time()-t:.1f}s")
        except Exception as e:
            bad += 1
            print(f"  run {i}: FAIL after {time.time()-t:.1f}s  {type(e).__name__}  "
                  f"{got/1024:.0f} KB in  worst gap {worst:.1f}s")
    sys.exit(1 if bad else 0)
PY

echo
if [ "$FAIL" -ne 0 ]; then
  echo "──── GATE FAILED — no flask data is collected ────"
  echo "If the 8000-token localhost run is what failed, the earlier diagnosis was"
  echo "wrong: the collapse would not be the network, and blaming transport for"
  echo "all of it would have been a mistake worth catching here rather than in"
  echo "the confirmatory batch."
  exit 1
fi
echo "──── GATE PASSED — run only the frozen flask batch ────"

"""One real cell, driven through the **public CLI**.

Host 5 stopped because `agentseism.pilot --backend real` could not invoke the
backend, and nothing had ever executed that entry point: the smoke test calls
`run_cell` directly. This probe calls `pilot.main()` and nothing else, against
a real container and the real SWE-bench evaluator, with only the model stubbed.

    python tests/_cli_cell_probe.py <workdir> [pilot|f3]

Parameterised rather than copied. F3 is a different registration on the *same*
runner, so a second probe would be a second way in -- and "a path nothing ever
executed" is precisely what stopped the pilot.
"""
from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

os.environ["MSWEA_MODEL_RETRY_STOP_AFTER_ATTEMPT"] = "1"
os.environ["MSWEA_COST_TRACKING"] = "ignore_errors"

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "src"))

WORK = Path(sys.argv[1])
EXPERIMENT = sys.argv[2] if len(sys.argv) > 2 else "pilot"
# The form `docker image inspect` reports, which is what the draw records in
# image_digests.tsv -- not the `docker.io/` form `image_for` builds for pulls.
IMAGE = ("swebench/sweb.eval.x86_64.pytest-dev_1776_pytest-10051"
         "@sha256:e38365e835d4ba57f3e7331778894f51ac20bf6c5893827065da8657525e123f")
MODEL = "Qwen/Qwen3.6-27B-FP8"
REVISION = "e89b16ebf1988b3d6befa7de50abc2d76f26eb09"

SCRIPT = [
    "cd /testbed && printf '\\nSUPPRESSED_SHOULD_NOT_APPEAR\\n' >> CHANGELOG.rst",
    "cd /testbed && printf '\\nagentseism cli probe\\n' >> CHANGELOG.rst",
    "cd /testbed && git diff > patch.txt && wc -c patch.txt",
    "cd /testbed && echo COMPLETE_TASK_AND_SUBMIT_FINAL_OUTPUT && cat patch.txt",
]
REQUESTS: list[float] = []
LOCK = threading.Lock()


class Stub(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.0"

    def _handle(self):
        with LOCK:
            n = len(REQUESTS)
            REQUESTS.append(time.monotonic())
        cmd = SCRIPT[min(n % len(SCRIPT), len(SCRIPT) - 1)]
        body = json.dumps({
            "id": "c", "object": "chat.completion", "created": 0,
            "model": f"openai/{MODEL}",
            "choices": [{"index": 0, "finish_reason": "tool_calls", "message": {
                "role": "assistant", "content": "",
                "tool_calls": [{"id": "t", "type": "function", "function": {
                    "name": "bash",
                    "arguments": json.dumps({"command": cmd})}}]}}],
            "usage": {"prompt_tokens": 9, "completion_tokens": 5,
                      "total_tokens": 14},
        }).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Connection", "close")
        self.end_headers()
        self.wfile.write(body)

    do_POST = do_GET = do_PUT = do_HEAD = _handle

    def log_message(self, *a):
        pass


def write_verified(path: Path, obj) -> None:
    body = json.dumps(obj, indent=2, sort_keys=True) + "\n"
    path.write_text(body)
    Path(str(path) + ".sha256").write_text(
        hashlib.sha256(body.encode()).hexdigest() + "\n")


def main() -> int:
    from agentseism import f3_protocol, pilot, pilot_protocol as P
    from agentseism.budget import Budget, RunLog

    WORK.mkdir(parents=True, exist_ok=True)
    srv = ThreadingHTTPServer(("127.0.0.1", 0), Stub)
    port = srv.server_address[1]
    threading.Thread(target=srv.serve_forever, daemon=True).start()

    # A process standing in for vLLM: the fingerprint names it, and the CLI
    # checks its command line carries the model and revision.
    fake_vllm = subprocess.Popen(
        ["/bin/sh", "-c", "while :; do sleep 1; done",
         "vllm.entrypoints.openai.api_server", "--model", MODEL,
         "--revision", REVISION])
    time.sleep(1)

    commit = subprocess.run(["git", "rev-parse", "HEAD"], cwd=ROOT,
                            capture_output=True, text=True).stdout.strip()
    # Three distinct names, because a block is keyed on (replicate, task):
    # the same id three times collapses all nine rep-0 cells into one block,
    # which is how an intended one-block run became nine.
    #
    # Only block 0 executes, and block 0 is names[0]. The other two names get
    # the same image digest so `_check_images` can verify them without pulling
    # images for cells that will never run. This is a plumbing fixture, not a
    # draw: the real draw is P.3's and produces three different images.
    if EXPERIMENT == "f3":
        # F3 registers its one task rather than drawing it, so there is no
        # multi-name fixture to arrange: three arms over a single task are a
        # single block, which is the whole experiment.
        tasks = [f3_protocol.TASK]
    else:
        tasks = ["pytest-dev__pytest-10051", "django__django-10097",
                 "matplotlib__matplotlib-13989"]
    serving = {"model_base_url": f"http://127.0.0.1:{port}/v1",
               "model_name": MODEL, "model_revision": REVISION,
               "vllm_pid": str(fake_vllm.pid),
               "dependency_lock_sha256": "lock", "serving_config_sha256": "cfg"}
    report = {
        "status": "READY_FOR_MANUAL_PILOT_CONFIRMATION",
        "repo_commit": commit, "pilot_runs": 0,
        "drawn_tasks": tasks,
        "image_digests": {t: IMAGE for t in tasks},
        "smoke": {"passed": True, "pilot_evidence": False, "serving": serving},
        "serving_fingerprint": {"model": MODEL, "model_revision": REVISION,
                                "vllm_pid": str(fake_vllm.pid),
                                "dependency_lock_sha256": "lock",
                                "serving_config_sha256": "cfg"},
    }
    rp = WORK / "preflight_report.json"
    write_verified(rp, report)

    out = WORK / "pilot"
    out.mkdir(parents=True, exist_ok=True)
    log = RunLog(out / "run.jsonl")
    spec = pilot.SPECS[EXPERIMENT]
    b = Budget(log, spec.thresholds)
    b.record_baseline(0.0, billing_period="t", currency="USD")
    b.record_reading(0.0, billing_period="t", currency="USD")
    b.check("after_setup")                      # taken by the caller
    b.record_reading(0.0, billing_period="t", currency="USD")  # for block 0

    t0 = time.monotonic()
    err = None
    rc = None
    try:
        rc = pilot.main(["--backend", "real", "--execute-registered-pilot",
                         "--experiment", EXPERIMENT,
                         "--preflight-report", str(rp), "--out", str(out)])
    except BaseException as e:                              # noqa: BLE001
        err = f"{type(e).__name__}: {str(e)[:200]}"
    elapsed = round(time.monotonic() - t0, 1)
    srv.shutdown()
    fake_vllm.kill()

    cells = spec.verify(tasks)
    block0 = [c for c in cells
              if (c["replicate"], c["task"]) == (cells[0]["replicate"],
                                                 cells[0]["task"])]
    artifacts = sorted((out / "runs").glob("run_*.json")) if (out / "runs").exists() else []
    verified = []
    for a in artifacts:
        d = Path(str(a) + ".sha256")
        ok = d.exists() and hashlib.sha256(a.read_text().encode()).hexdigest() \
            == d.read_text().split()[0]
        body = json.loads(a.read_text())
        verified.append({"file": a.name, "digest_ok": ok,
                         "synthetic": body.get("synthetic"),
                         "protocol_hash": body.get("protocol_hash"),
                         "order_hash": body.get("order_hash"),
                         "termination": body.get("termination"),
                         "outcome_state": body.get("outcome_state"),
                         "evaluator_resolved": body.get("evaluator_resolved"),
                         "enters_pilot_outcome": body.get("enters_pilot_outcome"),
                         "transport_attempts": body.get("transport_attempts"),
                         "challenge_injections": body.get("challenge_injections")})
    stops = [r for r in log.read() if r["kind"] == "stopped"]
    rep_path = out / "report.json"
    report_out = json.loads(rep_path.read_text()) if rep_path.is_file() else None
    print(json.dumps({"rc": rc, "exception": err, "elapsed_seconds": elapsed,
                      "experiment": EXPERIMENT, "report": report_out,
                      "http_requests": len(REQUESTS),
                      "cells_in_block_0": len(block0),
                      "registered_cells": len(cells),
                      "artifacts": verified,
                      "stopped": stops[-1] if stops else None}, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

"""The chain against a **real container**, with only the model stubbed.

The one thing that genuinely needs a GPU is whether the pinned Qwen model,
through vLLM's parser, emits a usable tool call. Everything else -- a real
task image, a real `/testbed`, the challenge, recovery, patch extraction, the
real SWE-bench evaluator, the artifact, and the wall-clock cap -- runs on CPU
and Docker, and is exercised here so that Host 5 carries exactly one unknown.

    python tests/_docker_integration_probe.py [full|timeout]

`full`     first tool call -> challenge -> recovery -> real patch -> real
           evaluator -> artifact.
`timeout`  a short wall-clock cap against a sleeping command, to prove the
           same code path yields INFRA_TIMEOUT_1200S and never grades.

Run as a subprocess: MSWEA_COST_TRACKING is read at import time.
"""
from __future__ import annotations

import json
import os
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

MODE = sys.argv[1] if len(sys.argv) > 1 else "full"
os.environ["MSWEA_MODEL_RETRY_STOP_AFTER_ATTEMPT"] = "1"
os.environ["MSWEA_COST_TRACKING"] = "ignore_errors"

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "src"))

IMAGE = ("docker.io/swebench/sweb.eval.x86_64.pytest-dev_1776_pytest-10051"
         "@sha256:e38365e835d4ba57f3e7331778894f51ac20bf6c5893827065da8657525e123f")
TASK = "pytest-dev__pytest-10051"

REQUESTS: list[float] = []
LOCK = threading.Lock()

# The first command is the one the challenge suppresses: if it ever runs, it
# leaves a file in the real workspace and the test can see it.
# The suppressed command edits a **tracked** file, so if it ever executed the
# change would appear in `git diff` and therefore in the submitted patch. Its
# absence there is positive evidence, not the absence of evidence that an
# untracked marker file would give.
SUPPRESSED = ("cd /testbed && printf '\\nSUPPRESSED_SHOULD_NOT_APPEAR\\n' "
              ">> CHANGELOG.rst")
# The recovery action makes a real, extractable change to tracked source.
# A change to a non-imported file: it yields a real, extractable patch
# without any chance of disturbing test collection, so a definite verdict is
# attributable to the harness rather than to the probe's edit.
RECOVERY = ("cd /testbed && printf '\\nagentseism integration probe\\n' "
            ">> CHANGELOG.rst")
FULL_SCRIPT = [
    SUPPRESSED,
    RECOVERY,
    "cd /testbed && git diff > patch.txt && wc -c patch.txt",
    "cd /testbed && echo COMPLETE_TASK_AND_SUBMIT_FINAL_OUTPUT && cat patch.txt",
]
TIMEOUT_SCRIPT = [SUPPRESSED, "sleep 600", "sleep 600"]


def tool_call(command: str) -> bytes:
    return json.dumps({
        "id": "c", "object": "chat.completion", "created": 0,
        "model": "openai/Qwen/Qwen3.6-27B-FP8",
        "choices": [{"index": 0, "finish_reason": "tool_calls", "message": {
            "role": "assistant", "content": "",
            "tool_calls": [{"id": "t", "type": "function", "function": {
                "name": "bash", "arguments": json.dumps({"command": command})}}],
        }}],
        "usage": {"prompt_tokens": 9, "completion_tokens": 5, "total_tokens": 14},
    }).encode()


class Stub(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.0"

    def _handle(self):
        with LOCK:
            n = len(REQUESTS)
            REQUESTS.append(time.monotonic())
        script = FULL_SCRIPT if MODE == "full" else TIMEOUT_SCRIPT
        body = tool_call(script[min(n, len(script) - 1)])
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Connection", "close")
        self.end_headers()
        self.wfile.write(body)

    do_POST = do_GET = do_PUT = do_HEAD = _handle

    def log_message(self, *a):
        pass


def main() -> int:
    srv = ThreadingHTTPServer(("127.0.0.1", 0), Stub)
    port = srv.server_address[1]
    threading.Thread(target=srv.serve_forever, daemon=True).start()

    from agentseism import pilot_protocol as P
    from agentseism import real_backend as RB

    work = Path(os.environ.get("PROBE_WORK", "/tmp/agentseism-docker-probe"))
    work.mkdir(parents=True, exist_ok=True)
    cfg = RB.BackendConfig(
        image_digests={TASK: IMAGE}, work_dir=work,
        model_base_url=f"http://127.0.0.1:{port}/v1",
        model_name="Qwen/Qwen3.6-27B-FP8",
        model_revision="e89b16ebf1988b3d6befa7de50abc2d76f26eb09",
        timeout_seconds=(P.RUN_TIMEOUT_SECONDS if MODE == "full" else 25))
    cell = {"order_index": -1, "task": TASK, "arm": "baseline", "replicate": 0,
            "step_limit": len(FULL_SCRIPT) + 2, "hint": "full",
            "challenge": True}

    t0 = time.monotonic()
    err = None
    result = None
    try:
        # The real pilot entry point. Nothing here is a re-implementation.
        result = RB.run_cell(cell, cfg)
    except BaseException as e:                              # noqa: BLE001
        err = f"{type(e).__name__}: {str(e)[:200]}"
    elapsed = round(time.monotonic() - t0, 1)
    srv.shutdown()

    # The patch belonging to **this** run, found beside its own evaluator
    # report. Globbing for the newest patch.diff anywhere under logs/ picked
    # up another probe's run and reported its patch as this one's.
    patch_text = ""
    rp = (result or {}).get("evaluator_report_path") or ""
    if rp:
        cand = Path(rp).parent / "patch.diff"
        if cand.is_file():
            patch_text = cand.read_text()
    out = {"mode": MODE, "exception": err, "elapsed_seconds": elapsed,
           "http_requests": len(REQUESTS),
           "patch_bytes": len(patch_text),
           "patch_has_recovery": "agentseism integration probe" in patch_text,
           "patch_has_suppressed": "SUPPRESSED_SHOULD_NOT_APPEAR" in patch_text}
    if result:
        rec = result.get("challenge_record") or {}
        out.update({
            "agent_termination_code": result["agent_termination_code"],
            "infrastructure_status": result["infrastructure_status"],
            "evaluator_resolved": result["evaluator_resolved"],
            "outcome_state": result["outcome_state"],
            "enters_pilot_outcome": result["enters_pilot_outcome"],
            "termination": result["termination"],
            "challenge_status": result["challenge_status"],
            "challenge_injections": result.get("challenge_injections"),
            "suppressed_actions": [a.get("command") for a in
                                   (rec.get("suppressed_actions") or [])],
            "recovered": result["recovered"],
            "n_calls": result["n_calls"],
            "transport_attempts": result["transport_attempts"],
            "cost_tracking": result.get("cost_tracking"),
            "evaluator_report_path": result["evaluator_report_path"],
            "image_digest": result["image_digest"],
            "backend_error": str(result.get("backend_error", ""))[:200],
        })
    print(json.dumps(out))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

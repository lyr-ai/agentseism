"""Count the HTTP requests one logical model query actually makes.

Run as a subprocess so LiteLLM's global state and mini-swe-agent's global
config cannot leak between parametrisations. Prints one JSON line.

    python tests/_transport_probe.py <attempts>

`attempts` is the value for MSWEA_MODEL_RETRY_STOP_AFTER_ATTEMPT: the
registered run passes 1, the control passes 2 to prove the probe can see a
retry when one happens.
"""
from __future__ import annotations

import json
import os
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

HITS: list[float] = []
LOCK = threading.Lock()
MODE = "fail"


class Stub(BaseHTTPRequestHandler):
    """A retryable failure. 500 is chosen over 400 because most clients do not
    retry a 400 at all -- seeing one request then would prove nothing -- and
    over 429, whose Retry-After would introduce waiting of its own."""

    # HTTP/1.0 so every request is its own connection. Under keep-alive a
    # retried request landed on the handler's default HTML error page, and the
    # client then reported a BadRequestError that the stub had never sent --
    # the probe was measuring its own server, not the retry policy.
    protocol_version = "HTTP/1.0"

    def _respond(self, code: int, body: bytes):
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Connection", "close")
        self.end_headers()
        self.wfile.write(body)

    def _handle(self):
        with LOCK:
            HITS.append(time.monotonic())
        if MODE == "success":
            # A valid OpenAI tool call, so the client runs its whole success
            # path: parse the response, price it, parse the actions. Host 4
            # died in that path -- after a successful generation -- and no
            # failure-returning stub can reach it.
            self._respond(200, json.dumps({
                "id": "chatcmpl-stub", "object": "chat.completion",
                "created": 0, "model": "openai/Qwen/Qwen3.6-27B-FP8",
                "choices": [{
                    "index": 0, "finish_reason": "tool_calls",
                    "message": {
                        "role": "assistant", "content": "",
                        "tool_calls": [{
                            "id": "call_stub", "type": "function",
                            "function": {"name": "bash", "arguments":
                                         json.dumps({"command": "ls /testbed"})},
                        }],
                    },
                }],
                "usage": {"prompt_tokens": 11, "completion_tokens": 7,
                          "total_tokens": 18},
            }).encode())
            return
        body = b'{"error":{"message":"stub: upstream failure",' \
               b'"type":"server_error","code":500}}'
        self._respond(500, body)

    # Every method, so nothing the client tries reaches a default error page.
    do_POST = do_GET = do_PUT = do_HEAD = _handle

    def log_message(self, *a):
        pass


def main() -> int:
    global MODE
    attempts = sys.argv[1]
    when = sys.argv[2] if len(sys.argv) > 2 else "before"
    MODE = sys.argv[3] if len(sys.argv) > 3 else "fail"
    # The value that made host 4 fail is read at import time, so the probe
    # must set it before anything imports mini-swe-agent -- and a mode that
    # omits it reproduces host 4 exactly.
    if MODE == "success":
        os.environ["MSWEA_COST_TRACKING"] = "ignore_errors"
    elif MODE == "success_without_cost_env":
        os.environ.pop("MSWEA_COST_TRACKING", None)
        MODE = "success"
    elif MODE == "success_without_fix":
        # Neither mechanism: the control that proves this probe can see the
        # defect. Without it, "no exception" might only mean the probe cannot
        # reach the code that raised on host 4.
        os.environ.pop("MSWEA_COST_TRACKING", None)
        MODE = "success"
    os.environ.setdefault("MSWEA_GLOBAL_CONFIG_FILE", "/dev/null")

    if when == "before":
        os.environ["MSWEA_MODEL_RETRY_STOP_AFTER_ATTEMPT"] = attempts
    elif when == "after":
        # Import the retry layer *first*, then set the variable. If the
        # `os.getenv` were evaluated at import or decoration time this would
        # be too late and the default of ten would stand.
        os.environ.pop("MSWEA_MODEL_RETRY_STOP_AFTER_ATTEMPT", None)
        import minisweagent.models.utils  # noqa: F401
        import minisweagent.models.litellm_model  # noqa: F401
        os.environ["MSWEA_MODEL_RETRY_STOP_AFTER_ATTEMPT"] = attempts
    else:
        raise SystemExit(f"unknown mode {when!r}")

    srv = ThreadingHTTPServer(("127.0.0.1", 0), Stub)
    port = srv.server_address[1]
    threading.Thread(target=srv.serve_forever, daemon=True).start()

    from agentseism import pilot_protocol as P
    from agentseism.real_backend import BackendConfig, model_config

    cfg = BackendConfig(image_digests={}, work_dir=Path("."),
                        model_base_url=f"http://127.0.0.1:{port}/v1",
                        model_name="Qwen/Qwen3.6-27B-FP8",
                        model_revision="probe")
    mc = model_config(cfg, P.HINTS["full"])
    if sys.argv[3:4] == ["success_without_fix"]:
        mc.pop("cost_tracking", None)

    from minisweagent.models import get_model
    model = get_model(mc["model_name"], config=mc)

    t0 = time.monotonic()
    err = None
    actions = None
    cost = None
    try:
        out = model.query([{"role": "user", "content": "probe"}])
        extra = (out or {}).get("extra") or {}
        actions = [a.get("command") for a in (extra.get("actions") or [])]
        cost = extra.get("cost")
    except BaseException as e:                              # noqa: BLE001
        err = f"{type(e).__name__}: {str(e)[:120]}"
    elapsed = time.monotonic() - t0
    srv.shutdown()

    gaps = [round(b - a, 3) for a, b in zip(HITS, HITS[1:])]
    print(json.dumps({
        "requested_attempts": int(attempts),
        "env_set": when,
        "http_requests": len(HITS),
        "elapsed_seconds": round(elapsed, 3),
        "gaps_between_requests": gaps,
        "exception": err,
        "mode": MODE,
        "actions": actions,
        "cost": cost,
        "cost_tracking_config": mc.get("cost_tracking"),
        "cost_env": os.environ.get("MSWEA_COST_TRACKING"),
        "model_name": mc["model_name"],
        "num_retries": mc["model_kwargs"].get("num_retries"),
        "max_retries": mc["model_kwargs"].get("max_retries"),
    }))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

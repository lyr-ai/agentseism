"""The full success path, end to end, against a local stub.

Hosts 2, 3 and 4 each died on this path: no runner, a bare model id, and cost
accounting discarding a generation that had already arrived. Every failure-mode
test in the suite passed throughout. A stub that only returns errors cannot
reach the code that raised on host 4, so this one answers successfully.

    python tests/_success_path_probe.py [with_fix|without_fix]

`without_fix` removes the P.9 cost policy and must reproduce host 4 exactly.
Run as a subprocess: MSWEA_COST_TRACKING is read at import time, so the mode
has to be chosen before anything imports mini-swe-agent.
"""
from __future__ import annotations

import json
import os
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

MODE = sys.argv[1] if len(sys.argv) > 1 else "with_fix"
# Chosen before any import below. This is the whole reason for the subprocess.
os.environ["MSWEA_MODEL_RETRY_STOP_AFTER_ATTEMPT"] = "1"
if MODE == "with_fix":
    os.environ["MSWEA_COST_TRACKING"] = "ignore_errors"
else:
    os.environ.pop("MSWEA_COST_TRACKING", None)

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "src"))

REQUESTS: list[dict] = []
LOCK = threading.Lock()


def tool_call(command: str) -> bytes:
    return json.dumps({
        "id": "chatcmpl-stub", "object": "chat.completion", "created": 0,
        "model": "openai/Qwen/Qwen3.6-27B-FP8",
        "choices": [{"index": 0, "finish_reason": "tool_calls", "message": {
            "role": "assistant", "content": "",
            "tool_calls": [{"id": "call_stub", "type": "function", "function": {
                "name": "bash", "arguments": json.dumps({"command": command})}}],
        }}],
        "usage": {"prompt_tokens": 11, "completion_tokens": 7, "total_tokens": 18},
    }).encode()


class Stub(BaseHTTPRequestHandler):
    """First answer is the one the challenge suppresses; second is recovery."""

    protocol_version = "HTTP/1.0"
    COMMANDS = ["echo SUPPRESSED_SHOULD_NEVER_RUN", "echo RECOVERED", "echo THIRD"]

    def _handle(self):
        with LOCK:
            n = len(REQUESTS)
            REQUESTS.append({"n": n, "t": time.monotonic()})
        body = tool_call(self.COMMANDS[min(n, len(self.COMMANDS) - 1)])
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Connection", "close")
        self.end_headers()
        self.wfile.write(body)

    do_POST = do_GET = do_PUT = do_HEAD = _handle

    def log_message(self, *a):
        pass


class RecordingEnv:
    """Records what is executed. Nothing reaches a container."""

    def __init__(self):
        self.executed: list[str] = []
        self.config = type("C", (), {"cwd": "/testbed"})()

    def execute(self, action: dict, cwd: str = "") -> dict:
        self.executed.append(action.get("command", ""))
        # `exception_info` is required: the observation template renders under
        # StrictUndefined and the real Docker environment always supplies it.
        return {"output": "ok", "returncode": 0, "exception_info": ""}

    def get_template_vars(self, **kw):
        return {"cwd": "/testbed"}

    def serialize(self):
        return {"env": "recording"}


def main() -> int:
    srv = ThreadingHTTPServer(("127.0.0.1", 0), Stub)
    port = srv.server_address[1]
    threading.Thread(target=srv.serve_forever, daemon=True).start()

    from agentseism import pilot_protocol as P
    from agentseism.real_backend import BackendConfig, _swebench_base, model_config

    cfg = BackendConfig(image_digests={}, work_dir=Path("."),
                        model_base_url=f"http://127.0.0.1:{port}/v1",
                        model_name="Qwen/Qwen3.6-27B-FP8",
                        model_revision="probe")
    mc = model_config(cfg, P.HINTS["full"])
    if MODE != "with_fix":
        mc.pop("cost_tracking", None)

    from minisweagent.agents.default import DefaultAgent
    from minisweagent.models import get_model

    from experiments.coding.recovery_challenge import challenging

    model = get_model(mc["model_name"], config=mc)
    env = RecordingEnv()
    Agent = challenging(DefaultAgent)
    # The real agent section, as `_agent_result` builds it: the templates are
    # required fields and a hand-made config would not be the pilot's agent.
    agent_cfg = dict(_swebench_base()["agent"])
    agent_cfg["step_limit"] = 3
    agent_cfg["cost_limit"] = P.COST_LIMIT_DISABLED
    agent_cfg["wall_time_limit_seconds"] = 60
    agent = Agent(model, env, **agent_cfg)

    err = None
    try:
        agent.run(task="probe task")
    except BaseException as e:                              # noqa: BLE001
        err = f"{type(e).__name__}: {str(e)[:160]}"

    rec = getattr(agent, "challenge_record", None) or {}
    print(json.dumps({
        "mode": MODE,
        "exception": err,
        "http_requests": len(REQUESTS),
        "executed": env.executed,
        "challenge_fired": bool(getattr(agent, "challenge_fired", False)),
        "challenge_injections": 1 if getattr(agent, "challenge_fired", False) else 0,
        "injected_at_call": rec.get("injected_at_call"),
        "suppressed_actions": [a.get("command") for a in
                               (rec.get("suppressed_actions") or [])],
        "n_calls": int(getattr(agent, "n_calls", 0)),
        "cost": float(getattr(agent, "cost", 0.0)),
        "cost_tracking_config": mc.get("cost_tracking"),
        "model_name": mc["model_name"],
    }))
    srv.shutdown()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

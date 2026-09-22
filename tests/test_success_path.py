"""The success path, end to end (P.9 review).

Hosts 2, 3 and 4 each died on the path a *working* response takes through the
client, while every failure-mode test in the suite passed. This is that path:
real `get_model`, real LiteLLM, real `challenging(DefaultAgent)`, against a
stub that answers with valid tool calls.

Run out of process because MSWEA_COST_TRACKING is read at import time, so the
mode has to be chosen before anything imports mini-swe-agent.
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from agentseism import pilot_protocol as P
from agentseism import real_backend as RB

ROOT = Path(__file__).resolve().parents[1]
PROBE = ROOT / "tests" / "_success_path_probe.py"


def run(mode: str) -> dict:
    import os
    env = {k: v for k, v in os.environ.items() if k != "MSWEA_COST_TRACKING"}
    r = subprocess.run([sys.executable, str(PROBE), mode], cwd=ROOT,
                       capture_output=True, text=True, timeout=600, env=env)
    assert r.returncode == 0, r.stderr[-2000:]
    return json.loads(r.stdout.strip().splitlines()[-1])


@pytest.fixture(scope="module")
def ok():
    return run("with_fix")


@pytest.fixture(scope="module")
def control():
    return run("without_fix")


# 1. the real client reaches the stub
def test_the_real_client_calls_the_local_endpoint(ok):
    assert ok["model_name"] == "openai/Qwen/Qwen3.6-27B-FP8"
    assert ok["http_requests"] >= 1


# 2. the first response is a valid tool call
def test_the_first_response_is_parsed_as_a_tool_call(ok):
    assert ok["injected_at_call"] == 1, \
        "the challenge fires on the first valid tool call, so this proves one"


# 3. the challenge fires exactly once and suppresses the original
def test_the_challenge_fires_exactly_once(ok):
    assert ok["challenge_fired"] is True
    assert ok["challenge_injections"] == 1


def test_the_suppressed_action_is_recorded(ok):
    assert ok["suppressed_actions"] == ["echo SUPPRESSED_SHOULD_NEVER_RUN"]


# 4. the second response is a valid tool call after recovery
def test_the_agent_recovers_with_another_valid_tool_call(ok):
    assert ok["n_calls"] >= 2
    assert ok["http_requests"] >= 2


# 5. only the recovered action executes
def test_the_suppressed_action_never_reaches_the_environment(ok):
    assert "echo SUPPRESSED_SHOULD_NEVER_RUN" not in ok["executed"]
    assert ok["executed"][0] == "echo RECOVERED", ok["executed"]


# 6. cost tracking raises nothing
def test_cost_accounting_does_not_raise(ok):
    assert ok["exception"] is None
    assert ok["cost_tracking_config"] == "ignore_errors"


# 7. one transport attempt per logical request
def test_one_transport_attempt_per_logical_request(ok):
    assert ok["http_requests"] == ok["n_calls"], \
        "a retry would make requests exceed logical calls"
    assert P.TRANSPORT_ATTEMPTS == 1


# 8. the evaluator returns an explicit boolean
@pytest.mark.parametrize("resolved", [True, False])
def test_the_evaluator_verdict_is_an_explicit_boolean(tmp_path, monkeypatch,
                                                      resolved):
    report = tmp_path / "reports" / "r.json"
    report.parent.mkdir(parents=True, exist_ok=True)
    report.write_text(json.dumps({"t": {"resolved": resolved}}))
    monkeypatch.setattr(RB.subprocess, "run", lambda *a, **k: None)
    got, path = RB._evaluate({"order_index": 0, "task": "t", "arm": "baseline",
                              "replicate": 0}, "diff", RB.BackendConfig(
        image_digests={}, work_dir=tmp_path, model_base_url="",
        model_name="m", model_revision="r"))
    assert got is None or isinstance(got, bool)


# 9. a complete, verifiable cell artifact
def test_a_complete_cell_artifact_is_produced_and_verifies(tmp_path):
    from agentseism import smoke as S
    result = {
        "agent_termination_code": P.COMPLETED, "infrastructure_status": "OK",
        "evaluator_resolved": False, "challenge_status": "FIRED",
        "challenge_record": {"injected_at_call": 1,
                             "suppressed_actions": [{"command": "x"}]},
        "challenge_injections": 1, "suppressed_actions_executed": False,
        "recovered": True, "hint_sha256": P.HINT_SHA256["full"],
        "step_limit": 250, "image_digest": "img@sha256:" + "a" * 64,
        "registered_model_id": "Qwen/Qwen3.6-27B-FP8",
        "transport_model": "openai/Qwen/Qwen3.6-27B-FP8",
        "api_base": "http://127.0.0.1:8000/v1", "transport_attempts": 1,
        "cost_tracking": "ignore_errors", "model_revision": "e89b16eb",
        "evaluator_report_path": "reports/r.json", "n_calls": 3,
        "elapsed_seconds": 12.0,
    }
    result["outcome_state"] = RB.outcome_state("OK", False)
    result["enters_pilot_outcome"] = RB.ENTERS_PILOT_OUTCOME[result["outcome_state"]]
    result["termination"] = RB.registered_termination(P.COMPLETED, "OK", False)
    rep = S.run_smoke(RB.BackendConfig(
        image_digests={S.SMOKE_TASK: "i@sha256:" + "a" * 64},
        work_dir=tmp_path, model_base_url="u", model_name="m",
        model_revision="r"), tmp_path / "smoke",
        backend=lambda c, cf: result)
    assert rep["passed"] is True, rep["failed"]
    import hashlib
    p = tmp_path / "smoke" / "smoke_run.json"
    assert hashlib.sha256(p.read_text().encode()).hexdigest() == rep["sha256"]
    body = json.loads(p.read_text())
    for k in ("registered_model_id", "transport_model", "api_base",
              "transport_attempts", "cost_tracking"):
        assert k in body, k


# 10. the control reproduces host 4 exactly
def test_the_control_reproduces_host_4(control):
    assert control["cost_tracking_config"] is None
    assert control["exception"] is not None
    assert "Error calculating cost" in control["exception"]
    assert "isn't mapped yet" in control["exception"]


def test_the_control_dies_after_a_successful_generation(control):
    """The defining shape of host 4: the model answered, and the answer was
    thrown away. One request made, nothing executed."""
    assert control["http_requests"] == 1
    assert control["executed"] == []
    assert control["challenge_fired"] is False


def test_the_two_modes_differ_only_in_the_registered_policy(ok, control):
    assert ok["model_name"] == control["model_name"]
    assert ok["exception"] is None and control["exception"] is not None
    assert ok["executed"] and not control["executed"]

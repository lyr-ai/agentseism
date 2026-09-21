"""The registered smoke test (amendment P.4).

Its job is to prove the chain is connected, and nothing else. The reverse
test is the important one: a run that fails its task must still pass, and if
anyone ever adds task success to the gate, these fail.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from agentseism import pilot_protocol as P
from agentseism import real_backend as RB
from agentseism import smoke as S


def cfg(tmp_path):
    return RB.BackendConfig(
        image_digests={S.SMOKE_TASK: "img@sha256:" + "a" * 64},
        work_dir=tmp_path, model_base_url="http://127.0.0.1:8000/v1",
        model_name="Qwen/Qwen3.6-27B-FP8", model_revision="e89b16eb")


def result(**over):
    r = {
        "agent_termination_code": P.COMPLETED,
        "infrastructure_status": "OK",
        "evaluator_resolved": False,
        "challenge_status": "FIRED",
        "challenge_record": {"injected_at_call": 2,
                             "suppressed_actions": [{"command": "x"}]},
        "challenge_injections": 1,
        "suppressed_actions_executed": False,
        "recovered": True,
        "hint_sha256": P.HINT_SHA256["full"],
        "step_limit": 250,
        "image_digest": "img@sha256:" + "a" * 64,
        "model_revision": "e89b16eb",
        "registered_model_id": "Qwen/Qwen3.6-27B-FP8",
        "transport_model": "openai/Qwen/Qwen3.6-27B-FP8",
        "api_base": "http://127.0.0.1:8000/v1",
        "transport_attempts": 1,
        "evaluator_report_path": "reports/x.json",
        "n_calls": 11,
        "elapsed_seconds": 240.0,
    }
    r.update(over)
    r["outcome_state"] = RB.outcome_state(r["infrastructure_status"],
                                          r["evaluator_resolved"])
    r["enters_pilot_outcome"] = RB.ENTERS_PILOT_OUTCOME[r["outcome_state"]]
    r["termination"] = RB.registered_termination(
        r["agent_termination_code"], r["infrastructure_status"],
        r["evaluator_resolved"])
    return r


def smoke(tmp_path, **over):
    return S.run_smoke(cfg(tmp_path), tmp_path / "smoke",
                       backend=lambda c, cf: result(**over))


# ── the registered shape ──
def test_one_task_one_arm_one_run(tmp_path):
    c = S.smoke_cell()
    assert c["task"] == "pytest-dev__pytest-10051"
    assert c["arm"] == "baseline"
    rep = smoke(tmp_path)
    assert rep["runs"] == 1


def test_the_task_is_the_one_p3_excludes():
    assert S.SMOKE_TASK in P.EXCLUDED_INSTANCES


def test_the_arm_is_baseline_verbatim():
    c = S.smoke_cell()
    for k in ("step_limit", "hint", "challenge"):
        assert c[k] == P.ARMS["baseline"][k]


def test_it_occupies_no_registered_cell():
    cells = P.verify(["a-1", "b-1", "c-1"])
    assert len(cells) == P.CELLS == 18
    assert S.ORDER_INDEX not in [c["order_index"] for c in cells]
    assert S.ORDER_INDEX < 0


def test_it_does_not_move_the_order_hash():
    before = P.order_hash(P.build_order())
    S.smoke_cell()
    assert P.order_hash(P.build_order()) == before == "cfe8856c9c9167b5"


def test_the_cap_is_the_registered_one(tmp_path):
    c = cfg(tmp_path)
    assert c.timeout_seconds == P.RUN_TIMEOUT_SECONDS == 1200


def test_output_may_only_go_to_a_smoke_directory(tmp_path):
    with pytest.raises(S.SmokeStop) as e:
        S.run_smoke(cfg(tmp_path), tmp_path / "pilot",
                    backend=lambda c, cf: result())
    assert "indistinguishable from pilot evidence" in str(e.value)


def test_every_artifact_is_marked_not_pilot_evidence(tmp_path):
    rep = smoke(tmp_path)
    assert rep["pilot_evidence"] is False and rep["smoke"] is True
    body = json.loads((tmp_path / "smoke" / "smoke_run.json").read_text())
    assert body["pilot_evidence"] is False and body["smoke"] is True


def test_the_artifact_is_frozen_atomically_and_verifies(tmp_path):
    rep = smoke(tmp_path)
    p = tmp_path / "smoke" / "smoke_run.json"
    assert p.exists() and Path(str(p) + ".sha256").exists()
    import hashlib
    assert hashlib.sha256(p.read_text().encode()).hexdigest() == rep["sha256"]
    assert rep["artifact_verified"] is True
    assert rep["criteria"]["artifact_frozen"] is True


def test_one_execution_no_retry(tmp_path):
    calls = []
    S.run_smoke(cfg(tmp_path), tmp_path / "smoke",
                backend=lambda c, cf: (calls.append(c), result())[1])
    assert len(calls) == 1


# ── the reverse test: the verdict must not reach the gate ──
def test_a_failed_task_with_an_intact_chain_passes(tmp_path):
    rep = smoke(tmp_path, evaluator_resolved=False)
    assert rep["evaluator_resolved"] is False
    assert rep["outcome_state"] == RB.RESOLVED_FALSE
    assert rep["passed"] is True, rep["failed"]


def test_a_solved_task_passes_the_same_way(tmp_path):
    rep = smoke(tmp_path, evaluator_resolved=True)
    assert rep["passed"] is True


def test_the_verdict_value_cannot_affect_the_gate(tmp_path):
    """If anyone adds task success to the smoke gate, this fails."""
    a = S.evaluate_chain({**result(evaluator_resolved=True),
                          "_artifact_verified": True})
    b = S.evaluate_chain({**result(evaluator_resolved=False),
                          "_artifact_verified": True})
    assert a["criteria"] == b["criteria"]
    assert a["passed"] == b["passed"] is True


def test_no_criterion_reads_the_verdicts_value():
    """Structural, not behavioural: a criterion may ask whether `resolved` is
    a boolean, never which boolean it is."""
    import inspect
    for name, fn, _ in S.CRITERIA:
        for line in inspect.getsource(fn).splitlines():
            if "evaluator_resolved" not in line:
                continue
            # The only admissible question about the verdict is whether it is
            # a boolean. Anything that reads which boolean it is would make
            # task success a pass criterion.
            assert "isinstance" in line, \
                f"{name} consults the verdict's value: {line.strip()!r}"


# ── each criterion fails for its own reason ──
def test_an_undecided_evaluator_fails_the_gate(tmp_path):
    rep = smoke(tmp_path, evaluator_resolved=None)
    assert rep["passed"] is False
    assert rep["failed"] == ["evaluator_decided"]


def test_a_non_boolean_verdict_fails_the_gate(tmp_path):
    chain = S.evaluate_chain({**result(), "evaluator_resolved": "true",
                              "_artifact_verified": True})
    assert chain["criteria"]["evaluator_decided"] is False


def test_a_challenge_that_never_fired_fails_the_gate(tmp_path):
    rep = smoke(tmp_path, challenge_status=P.NOT_ELIGIBLE,
                challenge_record=None, challenge_injections=0,
                agent_termination_code=P.NOT_ELIGIBLE, recovered=None)
    assert rep["passed"] is False
    assert "valid_tool_call" in rep["failed"]
    assert "challenge_injected_once" in rep["failed"]


def test_a_twice_injected_challenge_fails_the_gate():
    chain = S.evaluate_chain({**result(), "challenge_injections": 2,
                              "_artifact_verified": True})
    assert chain["criteria"]["challenge_injected_once"] is False


def test_an_executed_suppressed_action_fails_the_gate():
    chain = S.evaluate_chain({**result(), "suppressed_actions_executed": True,
                              "_artifact_verified": True})
    assert chain["criteria"]["challenge_injected_once"] is False


def test_a_backend_error_fails_the_gate(tmp_path):
    r = result(infrastructure_status=RB.BACKEND_ERROR, evaluator_resolved=None)
    chain = S.evaluate_chain({**r, "n_calls": 0, "_artifact_verified": True})
    assert chain["passed"] is False
    assert "image_started" in chain["failed"]


def test_a_censored_run_fails_the_gate():
    """1200 s is a pass criterion for the pilot's accounting, not for the
    chain: a run that never reached the evaluator has not demonstrated it."""
    r = result(infrastructure_status=RB.INFRA_TIMEOUT_1200S,
               evaluator_resolved=None)
    chain = S.evaluate_chain({**r, "_artifact_verified": True})
    assert chain["criteria"]["evaluator_decided"] is False
    assert chain["passed"] is False


def test_an_unverified_artifact_fails_the_gate():
    chain = S.evaluate_chain({**result(), "_artifact_verified": False})
    assert chain["criteria"]["artifact_frozen"] is False


def test_the_step_limit_and_the_cap_stay_distinguishable():
    assert P.STEP_LIMIT_REACHED != P.INFRA_TIMEOUT_1200S
    assert P.STEP_LIMIT_REACHED in P.SCORABLE
    assert P.INFRA_TIMEOUT_1200S not in P.SCORABLE


def test_the_report_states_that_resolved_is_not_gated_on(tmp_path):
    rep = smoke(tmp_path, evaluator_resolved=False)
    assert "never gated on" in rep["note"]
    assert set(rep["criteria"]) == {n for n, _, _ in S.CRITERIA}


# ── the stack the smoke test ran against is recorded ──
SERVING = {"model_base_url": "http://127.0.0.1:8000/v1",
           "model_name": "Qwen/Qwen3.6-27B-FP8",
           "model_revision": "e89b16eb", "vllm_pid": "6262",
           "dependency_lock_sha256": "ba6a0fee", "serving_config_sha256": "c0ffee"}


def test_the_report_records_the_stack_that_answered_it(tmp_path):
    rep = S.run_smoke(cfg(tmp_path), tmp_path / "smoke",
                      backend=lambda c, cf: result(), serving=SERVING)
    assert rep["serving"] == SERVING
    body = json.loads((tmp_path / "smoke" / "smoke_run.json").read_text())
    assert body["serving"] == SERVING


def test_without_a_recorded_stack_nothing_can_be_cross_checked(tmp_path):
    """A smoke test that proved some *other* stack works proves nothing about
    the one that will serve the pilot, and an empty record says so."""
    rep = S.run_smoke(cfg(tmp_path), tmp_path / "smoke",
                      backend=lambda c, cf: result())
    assert rep["serving"] == {}


def test_the_serving_record_carries_what_the_fingerprint_binds(tmp_path):
    rep = S.run_smoke(cfg(tmp_path), tmp_path / "smoke",
                      backend=lambda c, cf: result(), serving=SERVING)
    for field in ("model_revision", "vllm_pid", "dependency_lock_sha256",
                  "serving_config_sha256"):
        assert rep["serving"][field], f"{field} is not recorded"

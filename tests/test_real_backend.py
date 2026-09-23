"""The backend interface, its result schema, and constructibility.

Host 2 reported READY with no runner. `build(dry_run=True)` is the check that
was missing, and `test_the_missing_execution_path_is_detected` is the
regression test for that day.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from agentseism import pilot_protocol as P
from agentseism import real_backend as RB


# ── the three axes stay apart ──
def test_a_single_success_field_is_refused():
    r = _ok_result()
    r["success"] = 1
    with pytest.raises(ValueError) as e:
        RB.validate_result(r)
    assert "merges the three axes" in str(e.value)


def _ok_result(**over):
    r = {
        "agent_termination_code": P.COMPLETED,
        "infrastructure_status": "OK",
        "evaluator_resolved": True,
        "challenge_status": "FIRED",
        "challenge_record": {"injected_at_call": 3, "suppressed_actions": []},
        "recovered": True,
        "hint_sha256": P.HINT_SHA256["full"],
        "step_limit": 250,
        "image_digest": "swebench/x@sha256:" + "a" * 64,
        "model_revision": "e89b16eb",
        "registered_model_id": "Qwen/Qwen3.6-27B-FP8",
        "transport_model": "openai/Qwen/Qwen3.6-27B-FP8",
        "api_base": "http://127.0.0.1:8000/v1",
        "transport_attempts": 1,
        "evaluator_report_path": "reports/x.json",
        "evaluator_report": "evaluator_reports/r.report.json",
        "evaluator_report_sha256": "a" * 64,
        "n_calls": 12,
        "elapsed_seconds": 314.0,
    }
    r.update(over)
    r["outcome_state"] = RB.outcome_state(r["infrastructure_status"],
                                          r["evaluator_resolved"])
    r["enters_pilot_outcome"] = RB.ENTERS_PILOT_OUTCOME[r["outcome_state"]]
    r["termination"] = RB.registered_termination(
        r["agent_termination_code"], r["infrastructure_status"],
        r["evaluator_resolved"])
    return r


@pytest.mark.parametrize("infra,resolved,state,enters", [
    ("OK", True, RB.RESOLVED_TRUE, True),
    ("OK", False, RB.RESOLVED_FALSE, True),
    ("OK", None, RB.EVALUATOR_UNDECIDED, False),
    (RB.INFRA_TIMEOUT_1200S, None, RB.INFRA_TIMEOUT_1200S, False),
    (RB.BACKEND_ERROR, None, RB.BACKEND_ERROR, False),
])
def test_the_registered_state_table(infra, resolved, state, enters):
    assert RB.outcome_state(infra, resolved) == state
    assert RB.ENTERS_PILOT_OUTCOME[state] is enters


def test_a_timeout_never_becomes_a_resolved_verdict():
    """A budget cap must not be able to manufacture a regression."""
    s = RB.outcome_state(RB.INFRA_TIMEOUT_1200S, None)
    assert s == RB.INFRA_TIMEOUT_1200S and not RB.ENTERS_PILOT_OUTCOME[s]
    assert RB.registered_termination(P.COMPLETED, RB.INFRA_TIMEOUT_1200S,
                                     None) == P.INFRA_TIMEOUT_1200S


def test_step_limit_reached_is_scored_not_discarded():
    """M1's mechanism. It stays an agent termination and keeps its verdict."""
    r = _ok_result(agent_termination_code=P.STEP_LIMIT_REACHED,
                   evaluator_resolved=False)
    RB.validate_result(r)
    assert r["outcome_state"] == RB.RESOLVED_FALSE
    assert r["enters_pilot_outcome"] is True
    assert r["termination"] == P.STEP_LIMIT_REACHED
    assert P.STEP_LIMIT_REACHED in P.SCORABLE
    assert P.STEP_LIMIT_REACHED not in RB.OUTCOME_STATES


def test_an_undecided_evaluator_is_an_integrity_stop_not_a_failure():
    r = _ok_result(evaluator_resolved=None)
    RB.validate_result(r)
    assert r["outcome_state"] == RB.EVALUATOR_UNDECIDED
    assert r["enters_pilot_outcome"] is False
    assert r["termination"] == P.INVALID


def test_a_non_boolean_verdict_has_not_decided():
    assert RB.outcome_state("OK", "true") == RB.EVALUATOR_UNDECIDED
    assert RB.outcome_state("OK", 1) == RB.EVALUATOR_UNDECIDED


def test_validate_refuses_a_state_that_does_not_follow():
    r = _ok_result()
    r["outcome_state"] = RB.RESOLVED_FALSE
    with pytest.raises(ValueError):
        RB.validate_result(r)


def test_validate_refuses_a_contradicted_enters_flag():
    r = _ok_result(infrastructure_status=RB.BACKEND_ERROR,
                   evaluator_resolved=None)
    r["enters_pilot_outcome"] = True
    with pytest.raises(ValueError):
        RB.validate_result(r)


def test_every_required_field_is_required():
    for k in RB.REQUIRED_RESULT_FIELDS:
        r = _ok_result()
        del r[k]
        with pytest.raises(ValueError):
            RB.validate_result(r)


# ── constructibility ──
def test_the_missing_execution_path_is_detected(monkeypatch):
    """Host 2's defect, kept as a test now that run_cell exists."""
    monkeypatch.delitem(RB.__dict__, "run_cell")
    with pytest.raises(RB.BackendUnavailable) as e:
        RB.build(dry_run=True)
    assert "run_cell" in str(e.value)


def test_the_gate_passes_now_that_a_runner_exists():
    r = RB.build(dry_run=True)
    assert r["execution_path"] == {"run_cell": "present"}
    assert (r["containers_created"], r["images_pulled"], r["model_requests"],
            r["evaluator_invocations"]) == (0, 0, 0, 0)


def test_a_placeholder_execution_path_is_rejected(monkeypatch):
    def run_cell(cell, config):
        raise NotImplementedError
    run_cell.placeholder = True
    monkeypatch.setitem(RB.__dict__, "run_cell", run_cell)
    with pytest.raises(RB.BackendUnavailable) as e:
        RB.build(dry_run=True)
    assert "placeholder" in str(e.value)


def test_a_wrong_signature_is_rejected(monkeypatch):
    monkeypatch.setitem(RB.__dict__, "run_cell", lambda c: None)
    with pytest.raises(RB.BackendUnavailable) as e:
        RB.build(dry_run=True)
    assert "(cell, config)" in str(e.value)


def _with_runner(monkeypatch):
    """The real run_cell is present; these only assert the gate's report."""


def test_the_dry_run_checks_pass_once_a_runner_exists():
    r = RB.build(dry_run=True)
    assert r["dry_run"] is True
    assert r["agent"]["wrapped"].startswith("Challenged")
    assert r["evaluator"]["invoked"] is False


def test_the_dry_run_creates_nothing_and_calls_nothing():
    r = RB.build(dry_run=True)
    assert r["containers_created"] == 0
    assert r["images_pulled"] == 0
    assert r["model_requests"] == 0
    assert r["evaluator_invocations"] == 0


def test_the_evaluator_is_inspected_but_never_invoked(monkeypatch):
    """Invoking it would make preflight an unregistered execution; the
    SWE-bench harness starts containers."""
    import swebench.harness.run_evaluation as re_mod
    monkeypatch.setattr(re_mod, "main",
                        lambda *a, **k: pytest.fail("evaluator was invoked"))
    with pytest.raises(RB.BackendUnavailable):
        RB._check_evaluator()      # a lambda has none of the named parameters


def test_an_unimportable_agent_fails_closed(monkeypatch):
    monkeypatch.setitem(sys.modules, "minisweagent.agents.default", None)
    with pytest.raises(RB.BackendUnavailable) as e:
        RB._check_agent()
    assert "mini-swe-agent" in str(e.value)


def test_an_unfrozen_hint_fails_closed(monkeypatch):
    monkeypatch.setitem(P.ARMS, "M2", {**P.ARMS["M2"], "hint": "half"})
    with pytest.raises(RB.BackendUnavailable) as e:
        RB._check_hints()
    assert "unfrozen hint" in str(e.value)


# ── images: verified locally, never pulled ──
def _cfg(tmp_path, digests):
    return RB.BackendConfig(image_digests=digests, work_dir=tmp_path,
                            model_base_url="http://127.0.0.1:8000/v1",
                            model_name="Qwen/Qwen3.6-27B-FP8",
                            model_revision="e89b16eb")


def test_a_missing_image_fails_and_is_not_pulled(tmp_path, monkeypatch):
    calls = []

    class R:
        returncode = 1
        stdout = ""

    def fake_run(argv, **kw):
        calls.append(argv)
        return R()
    monkeypatch.setattr(RB.subprocess, "run", fake_run)
    monkeypatch.setattr(RB.shutil, "which", lambda x: "/usr/bin/docker")
    with pytest.raises(RB.BackendUnavailable) as e:
        RB._check_images(_cfg(tmp_path, {"t": "img@sha256:" + "a" * 64}))
    assert "does not pull" in str(e.value)
    assert all("pull" not in c for argv in calls for c in argv)


def test_a_digest_mismatch_fails(tmp_path, monkeypatch):
    class R:
        returncode = 0
        stdout = '["img@sha256:' + "b" * 64 + '"]'
    monkeypatch.setattr(RB.subprocess, "run", lambda *a, **k: R())
    monkeypatch.setattr(RB.shutil, "which", lambda x: "/usr/bin/docker")
    with pytest.raises(RB.BackendUnavailable) as e:
        RB._check_images(_cfg(tmp_path, {"t": "img@sha256:" + "a" * 64}))
    assert "do not include the frozen" in str(e.value)


def test_a_matching_local_digest_passes_without_pulling(tmp_path, monkeypatch):
    want = "img@sha256:" + "a" * 64
    argvs = []

    class R:
        returncode = 0
        stdout = '["' + want + '"]'

    def fake_run(argv, **kw):
        argvs.append(argv)
        return R()
    monkeypatch.setattr(RB.subprocess, "run", fake_run)
    monkeypatch.setattr(RB.shutil, "which", lambda x: "/usr/bin/docker")
    out = RB._check_images(_cfg(tmp_path, {"t": want}))
    assert out == {"images": {"t": want}, "pulled": False}
    assert argvs and argvs[0][:3] == ["docker", "image", "inspect"]


def test_no_digests_supplied_is_a_failure(tmp_path, monkeypatch):
    monkeypatch.setattr(RB.shutil, "which", lambda x: "/usr/bin/docker")
    with pytest.raises(RB.BackendUnavailable):
        RB._check_images(_cfg(tmp_path, {}))


# ── the four invariants ──
def test_a_resolved_state_needs_a_real_boolean():
    """Two lines of defence: the derivation never produces RESOLVED_* from a
    non-boolean, and validate_result refuses one that arrives anyway."""
    assert RB.outcome_state("OK", "true") == RB.EVALUATOR_UNDECIDED
    r = _ok_result()
    r["evaluator_resolved"] = "true"
    r["outcome_state"] = RB.RESOLVED_TRUE
    r["enters_pilot_outcome"] = True
    with pytest.raises(ValueError):
        RB.validate_result(r)
    # and with the derivation bypassed entirely, invariant 1 still fires
    import unittest.mock as m
    with m.patch.object(RB, "outcome_state", lambda *a: RB.RESOLVED_TRUE):
        with pytest.raises(ValueError) as e:
            RB.validate_result(r)
    assert "true or false" in str(e.value)


def test_a_censored_run_may_not_carry_a_verdict():
    r = _ok_result(infrastructure_status=RB.INFRA_TIMEOUT_1200S,
                   evaluator_resolved=None)
    r["evaluator_resolved"] = False          # smuggled back in
    with pytest.raises(ValueError) as e:
        RB.validate_result(r)
    assert "manufacture an outcome" in str(e.value)


def test_a_step_limited_run_must_have_been_graded():
    r = _ok_result(agent_termination_code=P.STEP_LIMIT_REACHED,
                   evaluator_resolved=False)
    r["evaluator_report"] = ""
    r["evaluator_report_sha256"] = ""
    with pytest.raises(ValueError) as e:
        RB.validate_result(r)
    assert "graded like any other" in str(e.value)


def test_step_limit_reached_with_a_true_verdict_is_legal():
    """The fix lands on the last step and the budget runs out before the
    submission signal. A termination code may not overrule the grader."""
    r = _ok_result(agent_termination_code=P.STEP_LIMIT_REACHED,
                   evaluator_resolved=True)
    RB.validate_result(r)
    assert r["outcome_state"] == RB.RESOLVED_TRUE
    assert r["enters_pilot_outcome"] is True
    assert r["termination"] == P.STEP_LIMIT_REACHED


def test_broken_machinery_carries_no_verdict():
    r = _ok_result(infrastructure_status=RB.BACKEND_ERROR,
                   evaluator_resolved=None)
    r["evaluator_resolved"] = True
    with pytest.raises(ValueError) as e:
        RB.validate_result(r)
    assert "no verdict to report" in str(e.value)

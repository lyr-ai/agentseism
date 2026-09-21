"""`run_cell`: one agent execution, one evaluator execution, no retry.

Exercised with fakes. No container starts, no model is called and the
SWE-bench harness is never spawned -- those belong to the registered smoke
test (P.4), which is the only place the dynamic chain may be demonstrated.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from agentseism import pilot_protocol as P
from agentseism import real_backend as RB

DIGEST = "docker.io/swebench/sweb.eval.x86_64.astropy_1776_astropy-12907@sha256:" + "a" * 64


def cell(**over):
    c = {"order_index": 0, "task": "astropy__astropy-12907", "arm": "baseline",
         "replicate": 0, "step_limit": 250, "hint": "full", "challenge": True}
    c.update(over)
    return c


def cfg(tmp_path):
    return RB.BackendConfig(
        image_digests={"astropy__astropy-12907": DIGEST}, work_dir=tmp_path,
        model_base_url="http://127.0.0.1:8000/v1",
        model_name="Qwen/Qwen3.6-27B-FP8", model_revision="e89b16eb")


class FakeAgent:
    def __init__(self, *, exit_status="Submitted", submission="diff --git a b",
                 fired=True, injected_at=1, n_calls=7, actions_after=2):
        self.challenge_fired = fired
        self.challenge_record = ({"injected_at_call": injected_at,
                                  "suppressed_actions": [{"command": "x"}]}
                                 if fired else None)
        self.n_calls = n_calls
        self.cost = 0.0
        self.messages = [{"extra": {"actions": [{"command": f"c{i}"}]}}
                         for i in range(injected_at + actions_after)]
        self._info = {"exit_status": exit_status, "submission": submission}


def wire(monkeypatch, agent, *, resolved=True, report="r.json", boom=None,
         eval_boom=None):
    def _agent_result(c, config, hint, image):
        if boom:
            raise boom
        agent.seen = {"hint": hint, "image": image}
        return agent, agent._info
    def _evaluate(c, submission, config):
        if eval_boom:
            raise eval_boom
        agent.graded = submission
        return resolved, report
    monkeypatch.setattr(RB, "_agent_result", _agent_result)
    monkeypatch.setattr(RB, "_evaluate", _evaluate)


# ── the frozen inputs ──
def test_the_hint_is_indexed_exactly(tmp_path, monkeypatch):
    a = FakeAgent()
    wire(monkeypatch, a)
    RB.run_cell(cell(hint="error_only"), cfg(tmp_path))
    assert a.seen["hint"] == P.HINTS["error_only"]


def test_an_unknown_hint_stops_immediately(tmp_path, monkeypatch):
    wire(monkeypatch, FakeAgent())
    with pytest.raises(RB.CellError) as e:
        RB.run_cell(cell(hint="half"), cfg(tmp_path))
    assert "does not invent a template" in str(e.value)


def test_the_image_is_the_frozen_digest(tmp_path, monkeypatch):
    a = FakeAgent()
    wire(monkeypatch, a)
    RB.run_cell(cell(), cfg(tmp_path))
    assert a.seen["image"] == DIGEST and "@sha256:" in a.seen["image"]


def test_a_tag_is_refused(tmp_path, monkeypatch):
    wire(monkeypatch, FakeAgent())
    c = RB.BackendConfig(image_digests={"astropy__astropy-12907": "img:latest"},
                         work_dir=tmp_path, model_base_url="", model_name="",
                         model_revision="")
    with pytest.raises(RB.CellError) as e:
        RB.run_cell(cell(), c)
    assert "not digest-pinned" in str(e.value)


def test_an_undrawn_task_stops(tmp_path, monkeypatch):
    wire(monkeypatch, FakeAgent())
    with pytest.raises(RB.CellError):
        RB.run_cell(cell(task="django__django-1"), cfg(tmp_path))


# ── the exit mapping ──
@pytest.mark.parametrize("status,code", list(P.EXIT_STATUS_MAP.items()))
def test_each_registered_exit_maps(tmp_path, monkeypatch, status, code):
    a = FakeAgent(exit_status=status, n_calls=250)
    wire(monkeypatch, a, resolved=False)
    r = RB.run_cell(cell(), cfg(tmp_path))
    if code == P.INFRA_TIMEOUT_1200S:
        assert r["outcome_state"] == RB.INFRA_TIMEOUT_1200S
        assert r["evaluator_resolved"] is None
        assert r["enters_pilot_outcome"] is False
    else:
        assert r["agent_termination_code"] == code
        assert r["enters_pilot_outcome"] is True


def test_an_unmapped_exit_stops(tmp_path, monkeypatch):
    wire(monkeypatch, FakeAgent(exit_status="Exploded"))
    with pytest.raises(RB.CellError) as e:
        RB.run_cell(cell(), cfg(tmp_path))
    assert "unmapped agent exit status" in str(e.value)


def test_limits_exceeded_below_the_step_limit_is_a_misclassification(
        tmp_path, monkeypatch):
    """P.6's assertion: the exception names no limit, so the counter must
    agree. When it does not, that is BACKEND_ERROR, not a step limit."""
    wire(monkeypatch, FakeAgent(exit_status="LimitsExceeded", n_calls=3))
    with pytest.raises(RB.CellError) as e:
        RB.run_cell(cell(step_limit=250), cfg(tmp_path))
    assert "the mapping does not hold" in str(e.value)


def test_a_censored_run_is_never_graded(tmp_path, monkeypatch):
    a = FakeAgent(exit_status="TimeExceeded")
    wire(monkeypatch, a, resolved=True)
    r = RB.run_cell(cell(), cfg(tmp_path))
    assert r["outcome_state"] == RB.INFRA_TIMEOUT_1200S
    assert not hasattr(a, "graded"), "the evaluator ran on a censored run"
    assert r["evaluator_report_path"] == ""


# ── the challenge ──
def test_the_challenge_is_recorded_as_fired_once(tmp_path, monkeypatch):
    wire(monkeypatch, FakeAgent(fired=True, injected_at=2))
    r = RB.run_cell(cell(), cfg(tmp_path))
    assert r["challenge_status"] == "FIRED"
    assert r["challenge_injections"] == 1
    assert r["challenge_record"]["injected_at_call"] == 2


def test_the_suppressed_action_is_recorded_and_not_executed(tmp_path, monkeypatch):
    wire(monkeypatch, FakeAgent())
    r = RB.run_cell(cell(), cfg(tmp_path))
    assert r["suppressed_actions_executed"] is False
    assert r["challenge_record"]["suppressed_actions"] == [{"command": "x"}]


def test_a_challenge_that_never_fired_is_not_eligible(tmp_path, monkeypatch):
    wire(monkeypatch, FakeAgent(fired=False))
    r = RB.run_cell(cell(), cfg(tmp_path))
    assert r["challenge_status"] == P.NOT_ELIGIBLE
    assert r["agent_termination_code"] == P.NOT_ELIGIBLE
    assert r["recovered"] is None
    assert r["termination"] not in P.SCORABLE


def test_a_fired_challenge_with_no_record_is_a_backend_error(tmp_path, monkeypatch):
    a = FakeAgent()
    a.challenge_record = None
    wire(monkeypatch, a)
    r = RB.run_cell(cell(), cfg(tmp_path))
    assert r["outcome_state"] == RB.BACKEND_ERROR
    assert "left no record" in r["backend_error"]


def test_recovery_is_read_from_the_transcript(tmp_path, monkeypatch):
    wire(monkeypatch, FakeAgent(injected_at=1, actions_after=3))
    assert RB.run_cell(cell(), cfg(tmp_path))["recovered"] is True
    wire(monkeypatch, FakeAgent(injected_at=4, actions_after=0))
    assert RB.run_cell(cell(), cfg(tmp_path))["recovered"] is False


def test_format_limit_after_a_fired_challenge_is_scored(tmp_path, monkeypatch):
    """M2's interpretable mechanism, not an invalid run."""
    wire(monkeypatch, FakeAgent(exit_status="RepeatedFormatError",
                                injected_at=3, actions_after=0),
         resolved=False)
    r = RB.run_cell(cell(arm="M2", hint="error_only"), cfg(tmp_path))
    assert r["agent_termination_code"] == P.FORMAT_ERROR_LIMIT_REACHED
    assert r["termination"] in P.SCORABLE
    assert r["outcome_state"] == RB.RESOLVED_FALSE
    assert r["enters_pilot_outcome"] is True
    assert r["recovered"] is False


# ── the evaluator ──
def test_it_grades_this_cells_own_patch(tmp_path, monkeypatch):
    a = FakeAgent(submission="diff --git this-cell")
    wire(monkeypatch, a)
    RB.run_cell(cell(), cfg(tmp_path))
    assert a.graded == "diff --git this-cell"


def test_an_undecided_evaluator_is_not_a_failure(tmp_path, monkeypatch):
    wire(monkeypatch, FakeAgent(), resolved=None, report="r.json")
    r = RB.run_cell(cell(), cfg(tmp_path))
    assert r["outcome_state"] == RB.EVALUATOR_UNDECIDED
    assert r["enters_pilot_outcome"] is False
    assert r["termination"] == P.INVALID


# ── infrastructure never becomes a verdict ──
def test_an_agent_crash_is_a_backend_error(tmp_path, monkeypatch):
    wire(monkeypatch, FakeAgent(), boom=RuntimeError("container refused"))
    r = RB.run_cell(cell(), cfg(tmp_path))
    assert r["outcome_state"] == RB.BACKEND_ERROR
    assert r["evaluator_resolved"] is None
    assert r["enters_pilot_outcome"] is False
    assert "container refused" in r["backend_error"]


def test_an_evaluator_crash_is_a_backend_error(tmp_path, monkeypatch):
    wire(monkeypatch, FakeAgent(), eval_boom=OSError("harness died"))
    r = RB.run_cell(cell(), cfg(tmp_path))
    assert r["outcome_state"] == RB.BACKEND_ERROR
    assert r["evaluator_resolved"] is None
    assert "harness died" in r["backend_error"]


def test_no_infrastructure_failure_becomes_resolved_false(tmp_path, monkeypatch):
    for boom in (RuntimeError("x"), OSError("y"), ValueError("z")):
        wire(monkeypatch, FakeAgent(), boom=boom)
        r = RB.run_cell(cell(), cfg(tmp_path))
        assert r["outcome_state"] != RB.RESOLVED_FALSE


# ── one execution each ──
def test_one_agent_execution_and_one_evaluator_execution(tmp_path, monkeypatch):
    runs = {"agent": 0, "eval": 0}
    a = FakeAgent()

    def _agent_result(c, config, hint, image):
        runs["agent"] += 1
        return a, a._info

    def _evaluate(c, submission, config):
        runs["eval"] += 1
        return True, "r.json"
    monkeypatch.setattr(RB, "_agent_result", _agent_result)
    monkeypatch.setattr(RB, "_evaluate", _evaluate)
    RB.run_cell(cell(), cfg(tmp_path))
    assert runs == {"agent": 1, "eval": 1}


def test_the_result_validates_and_keeps_the_axes(tmp_path, monkeypatch):
    wire(monkeypatch, FakeAgent(), resolved=True)
    r = RB.run_cell(cell(), cfg(tmp_path))
    RB.validate_result(r)
    assert "success" not in r
    assert r["hint_sha256"] == P.HINT_SHA256["full"]
    assert r["image_digest"] == DIGEST
    assert r["model_revision"] == "e89b16eb"

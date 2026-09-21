"""The agent's exit statuses, mapped once and frozen (amendment P.6).

`RepeatedFormatError` is M2's predicted failure mode: an agent told nothing
about how to fix a malformed call is the agent that repeats one until the
limit. Mapping it to INVALID would have deleted M2's own mechanism from the
denominator, so the harder the mutation bit the less of it would be
measurable.
"""
from __future__ import annotations

import inspect
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from agentseism import pilot_protocol as P
from agentseism import real_backend as RB


def test_the_registered_mapping():
    assert P.EXIT_STATUS_MAP == {
        "Submitted": P.COMPLETED,
        "LimitsExceeded": P.STEP_LIMIT_REACHED,
        "TimeExceeded": P.INFRA_TIMEOUT_1200S,
        "RepeatedFormatError": P.FORMAT_ERROR_LIMIT_REACHED,
    }


def test_three_of_the_four_are_scored_and_the_cap_is_not():
    for status, term in P.EXIT_STATUS_MAP.items():
        scored = term in P.SCORABLE
        assert scored is (status != "TimeExceeded"), status


def test_format_error_limit_is_structurally_a_step_limit():
    """Same kind of thing: an agent-behaviour budget, not a fault."""
    assert P.FORMAT_ERROR_LIMIT_REACHED in P.TERMINATIONS
    assert P.FORMAT_ERROR_LIMIT_REACHED in P.SCORABLE
    assert P.FORMAT_ERROR_LIMIT_REACHED not in RB.OUTCOME_STATES


def test_every_mapped_termination_is_registered():
    for term in P.EXIT_STATUS_MAP.values():
        assert term in P.TERMINATIONS


def test_the_mapping_is_inside_the_protocol_hash():
    before = P.protocol_hash()
    P.EXIT_STATUS_MAP["RepeatedFormatError"] = P.INVALID
    try:
        assert P.protocol_hash() != before
    finally:
        P.EXIT_STATUS_MAP["RepeatedFormatError"] = P.FORMAT_ERROR_LIMIT_REACHED
    assert P.protocol_hash() == before


def test_the_order_hash_is_unmoved_by_p6():
    assert P.ORDER_HASH == "cfe8856c9c9167b5"
    assert P.order_hash(P.build_order()) == P.ORDER_HASH


# ── the claims P.6 rests on, checked against the pinned source ──
def test_cost_limit_zero_really_disables_the_cost_branch():
    """Not asserted from the docs: read out of mini-swe-agent 2.4.6."""
    from minisweagent.agents.default import DefaultAgent
    src = inspect.getsource(DefaultAgent.query)
    assert "0 < self.config.cost_limit <= self.cost" in src, \
        "the guard this rests on is gone; re-register the mapping"
    # `0 < 0` is false, so with cost_limit == 0 the branch cannot fire
    assert P.COST_LIMIT_DISABLED == 0
    cost_limit, cost = P.COST_LIMIT_DISABLED, 10_000.0
    assert not (0 < cost_limit <= cost)


def test_limits_exceeded_still_carries_no_structured_reason():
    """The dependency P.6 registers. If upstream ever adds one, this fails and
    the mapping is revisited rather than silently kept."""
    from minisweagent.agents.default import DefaultAgent
    src = inspect.getsource(DefaultAgent.query)
    block = src[src.index("LimitsExceeded("):src.index("wall_time_limit_seconds")]
    assert '"exit_status": "LimitsExceeded"' in block
    for word in ("step_limit_exceeded", "cost_limit_exceeded", "reason"):
        assert word not in block, f"upstream now reports {word!r}; revisit P.6"
    assert "LimitsExceeded" in P.EXIT_STATUS_DEPENDENCIES


def test_the_dependency_is_registered_in_words():
    note = P.EXIT_STATUS_DEPENDENCIES["LimitsExceeded"]
    assert "cost_limit is 0" in note
    assert "n_calls >= step_limit" in note
    assert "BACKEND_ERROR" in note


def test_the_upstream_statuses_we_map_still_exist():
    import minisweagent.exceptions as X
    for name in ("Submitted", "LimitsExceeded", "TimeExceeded", "FormatError"):
        assert hasattr(X, name), f"{name} is gone from the pinned package"


# ── the boundaries P.6 fixes ──
def test_a_challenge_that_never_fired_is_not_eligible():
    r = _result(agent_termination_code=P.NOT_ELIGIBLE,
                challenge_status=P.NOT_ELIGIBLE, recovered=None)
    RB.validate_result(r)
    assert r["termination"] == P.NOT_ELIGIBLE
    assert P.NOT_ELIGIBLE not in P.SCORABLE


@pytest.mark.parametrize("resolved,state", [
    (True, RB.RESOLVED_TRUE), (False, RB.RESOLVED_FALSE)])
def test_challenge_fired_then_format_limit_is_scored(resolved, state):
    """Injected once, then the agent never recovered. That is M2's
    interpretable mechanism, not an invalid run."""
    r = _result(agent_termination_code=P.FORMAT_ERROR_LIMIT_REACHED,
                challenge_status="FIRED", recovered=False,
                evaluator_resolved=resolved)
    RB.validate_result(r)
    assert r["outcome_state"] == state
    assert r["enters_pilot_outcome"] is True
    assert r["termination"] == P.FORMAT_ERROR_LIMIT_REACHED
    assert r["termination"] in P.SCORABLE


def test_a_format_limited_run_must_still_be_graded():
    r = _result(agent_termination_code=P.FORMAT_ERROR_LIMIT_REACHED,
                challenge_status="FIRED", recovered=False,
                evaluator_resolved=False)
    r["evaluator_report_path"] = ""
    with pytest.raises(ValueError) as e:
        RB.validate_result(r)
    assert "may not be ungraded" in str(e.value)


def _result(**over):
    r = {
        "agent_termination_code": P.COMPLETED,
        "infrastructure_status": "OK",
        "evaluator_resolved": False,
        "challenge_status": "FIRED",
        "challenge_record": None,
        "recovered": None,
        "hint_sha256": P.HINT_SHA256["error_only"],
        "step_limit": 250,
        "image_digest": "img@sha256:" + "a" * 64,
        "model_revision": "e89b16eb",
        "evaluator_report_path": "reports/x.json",
        "n_calls": 40,
        "elapsed_seconds": 900.0,
    }
    r.update(over)
    r["outcome_state"] = RB.outcome_state(r["infrastructure_status"],
                                          r["evaluator_resolved"])
    r["enters_pilot_outcome"] = RB.ENTERS_PILOT_OUTCOME[r["outcome_state"]]
    r["termination"] = RB.registered_termination(
        r["agent_termination_code"], r["infrastructure_status"],
        r["evaluator_resolved"])
    return r

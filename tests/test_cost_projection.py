"""The post-block cost check (amendment P.7).

Registered before Host 3 and before any block cost exists. Its decision
boundary is the already-registered $30 absolute stop, not a number anyone said
in conversation: `$3.50` is a reported expectation, never a threshold.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from agentseism import pilot_protocol as P
from agentseism.budget import Budget, RunLog
from agentseism.pilot import PILOT_THRESHOLDS
from agentseism.pilot_budget import main


def proj(before=2.09, cost=3.31, cells=3, remaining=15):
    return P.project_after_block(before, before + cost, cells, remaining)


def test_a_block_at_the_model_rate_does_not_halt():
    r = proj(cost=3.31)
    assert r["marginal_cost_per_run"] == pytest.approx(1.1033, abs=1e-3)
    assert r["projected_cumulative_spend"] < 30.0
    assert r["halt"] is False


def test_a_block_over_the_expectation_but_within_the_limit_does_not_halt():
    """The case that motivated anchoring to $30: $3.60 is above the ~$3.50
    sanity number and changes nothing, because the projection still fits."""
    r = proj(cost=3.60)
    assert r["within_expectation"] is False
    assert r["projected_cumulative_spend"] == 23.69
    assert r["halt"] is False


def test_a_block_whose_rate_would_breach_the_registered_stop_halts():
    r = proj(cost=6.00)
    assert r["projected_cumulative_spend"] == 38.09
    assert r["halt"] is True


def test_the_boundary_is_strictly_greater_than_the_limit():
    limit = P.ABSOLUTE_LIMIT_USD
    # choose a cost that projects to exactly the limit
    before, remaining, cells = 0.0, 15, 3
    cost = limit / (1 + remaining / cells)
    r = P.project_after_block(before, before + cost, cells, remaining)
    assert r["projected_cumulative_spend"] == pytest.approx(limit, abs=0.01)
    assert r["halt"] is False, "exactly at the stop is not past it"
    r2 = P.project_after_block(before, before + cost + 0.5, cells, remaining)
    assert r2["halt"] is True


def test_the_anchor_is_the_registered_limit_not_a_new_number():
    assert proj()["absolute_limit"] == P.ABSOLUTE_LIMIT_USD == 30.0
    assert P.COST_EXPECTATION_PER_RUN == 1.17


def test_the_expectation_is_reported_and_never_decides():
    """If `$3.50` ever becomes a stop, these disagree."""
    over = proj(cost=3.60)
    assert over["within_expectation"] is False and over["halt"] is False
    under = proj(cost=6.00)
    assert under["halt"] is True
    # halting is a function of the projection alone
    assert over["projected_cumulative_spend"] < over["absolute_limit"]
    assert under["projected_cumulative_spend"] > under["absolute_limit"]


def test_the_projection_is_optimistic_by_construction():
    """It charges the remaining runs at the marginal rate and adds nothing for
    idle time or teardown, so exceeding it cannot be argued away."""
    r = proj(cost=3.31)
    naive = r["spend_after_block"] + r["marginal_cost_per_run"] * r["cells_remaining"]
    assert r["projected_cumulative_spend"] == pytest.approx(naive, abs=0.01)
    assert "optimistic" in r["basis"]


def test_a_block_that_cost_nothing_is_still_arithmetic_not_an_error():
    r = proj(cost=0.0)
    assert r["marginal_cost_per_run"] == 0.0 and r["halt"] is False


def test_falling_spend_and_empty_blocks_are_refused():
    with pytest.raises(ValueError):
        P.project_after_block(5.0, 4.0, 3, 15)
    with pytest.raises(ValueError):
        P.project_after_block(1.0, 2.0, 0, 15)


def test_the_rule_is_inside_the_protocol_hash():
    before = P.protocol_hash()
    P.COST_EXPECTATION_PER_RUN = 99.0
    try:
        assert P.protocol_hash() != before
    finally:
        P.COST_EXPECTATION_PER_RUN = 1.17
    assert P.protocol_hash() == before


def test_the_order_hash_is_unmoved_by_p7():
    assert P.ORDER_HASH == "cfe8856c9c9167b5"
    assert P.order_hash(P.build_order()) == P.ORDER_HASH


# ── the CLI ──
def _log_with_block0(tmp_path, after_total):
    log = RunLog(tmp_path / "run.jsonl")
    b = Budget(log, PILOT_THRESHOLDS)
    b.record_baseline(7.16, billing_period="t", currency="USD")
    b.record_reading(9.25, billing_period="t", currency="USD")
    b.check("before_block", 0)
    for i in range(3):
        log.append("run", order_index=i, task="t", arm="baseline", replicate=0,
                   termination=P.COMPLETED)
    b.record_reading(after_total, billing_period="t", currency="USD")
    return log


def test_the_cli_reports_a_healthy_projection(tmp_path, capsys):
    _log_with_block0(tmp_path, 12.56)          # block 0 cost $3.31
    rc = main(["--log", str(tmp_path / "run.jsonl"), "--project-after-block", "0"])
    assert rc == 0
    assert "within the registered $30 stop" in capsys.readouterr().out


def test_the_cli_halts_on_a_projection_past_the_stop(tmp_path):
    log = _log_with_block0(tmp_path, 15.25)    # block 0 cost $6.00
    rc = main(["--log", str(tmp_path / "run.jsonl"), "--project-after-block", "0"])
    assert rc == 1
    rec = [r for r in log.read() if r["kind"] == "cost_projection"]
    assert rec and rec[-1]["halt"] is True


def test_the_projection_is_recorded_either_way(tmp_path):
    log = _log_with_block0(tmp_path, 12.56)
    main(["--log", str(tmp_path / "run.jsonl"), "--project-after-block", "0"])
    rec = [r for r in log.read() if r["kind"] == "cost_projection"]
    assert rec and rec[-1]["block_index"] == 0
    assert rec[-1]["halt"] is False


def test_the_cli_refuses_without_the_bracketing_authorisation(tmp_path):
    log = RunLog(tmp_path / "run.jsonl")
    b = Budget(log, PILOT_THRESHOLDS)
    b.record_baseline(7.16, billing_period="t", currency="USD")
    b.record_reading(9.25, billing_period="t", currency="USD")
    assert main(["--log", str(tmp_path / "run.jsonl"),
                 "--project-after-block", "0"]) == 2

"""C2-H: the frozen rules, and the conditions under which the runner refuses.

No model call, no vLLM, no network.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from experiments.coding import c2h_protocol as P
from experiments.coding.c2h_budget import Budget, BudgetStop, RunLog
from experiments.coding.run_c2h import (
    FailClosed, acquire_donors, bind_session, plan, verdict_for,
)


def donors(n_fail=4, n_pass=4):
    d = [{"arm": "FAIL", "donor_id": f"f{i}", "seed": i, "run_id": f"f{i}"}
         for i in range(n_fail)]
    d += [{"arm": "PASS", "donor_id": f"p{i}", "seed": 50 + i, "run_id": f"p{i}"}
          for i in range(n_pass)]
    return d


# ── the registered shape ──
def test_72_specs_full_cartesian_product():
    s = P.expand(donors())
    assert len(s) == 72 == P.total_specs()
    assert sum(1 for x in s if x["arm"] == "FAIL") == 48
    assert sum(1 for x in s if x["arm"] == "PASS") == 24


def test_expand_refuses_a_short_arm():
    with pytest.raises(ValueError, match="need 4 donors"):
        P.expand(donors(n_fail=3))


def test_36_is_a_strict_nested_subset_by_replicate_index():
    s = P.expand(donors()); sub = P.subset_36(s)
    assert len(sub) == 36
    assert {x["run_id"] for x in sub} < {x["run_id"] for x in s}
    for x in s:
        assert x["in_subset_36"] == (x["replicate"] in P.SUBSET_36[x["arm"]])
    # nested means it drops replicates, never a donor, horizon or arm
    for key in ("donor_id", "horizon", "arm"):
        assert {x[key] for x in sub} == {x[key] for x in s}


def test_completing_only_the_36_gives_no_verdict():
    s = P.expand(donors())
    v = verdict_for(P.subset_36(s), s)
    assert v["verdict"] is None and "censored" in v["classification"]


def test_completing_all_72_gives_a_verdict():
    s = P.expand(donors())
    assert verdict_for(s, s)["verdict"] == "recoverability"


def test_any_truncation_is_censored():
    s = P.expand(donors())
    assert verdict_for(s[:-1], s)["verdict"] is None


# ── blocks and order ──
def test_24_blocks_partition_the_specs_in_a_fixed_order():
    s = P.expand(donors()); b = P.blocks(s)
    assert len(b) == 24
    assert sorted(r for x in b for r in x["specs"]) == sorted(x["run_id"] for x in s)
    assert [x["arm"] for x in b] == ["FAIL"] * 12 + ["PASS"] * 12
    assert P.order_hash(P.blocks(s)) == P.order_hash(b)


def test_block_is_the_unit_that_runs_to_completion():
    """§6.1 — a cost re-estimate can never land inside a block, so a block
    must be a whole replicate group and never a partial one."""
    for b in P.blocks(P.expand(donors())):
        assert b["size"] == P.ARMS[b["arm"]]["replicates"]


# ── donor acquisition, §4 ──
def test_stops_at_the_registered_counts_and_takes_the_earliest(tmp_path):
    log = RunLog(tmp_path / "l.jsonl")
    seq = ["PASS", "FAIL", "PASS", "PASS", "FAIL", "PASS", "PASS", "FAIL",
           "FAIL", "FAIL", "PASS"]          # a 5th FAIL that must not be taken
    got = acquire_donors(log, Budget(log), lambda s, r: seq[s])
    assert len(got) == 8
    assert [d["seed"] for d in got if d["arm"] == "FAIL"] == [1, 4, 7, 8]
    assert [d["seed"] for d in got if d["arm"] == "PASS"] == [0, 2, 3, 5]


def test_donor_yield_stop_when_the_cap_is_reached(tmp_path):
    log = RunLog(tmp_path / "l.jsonl")
    with pytest.raises(BudgetStop) as e:
        acquire_donors(log, Budget(log), lambda s, r: "PASS")
    assert e.value.kind == "donor_yield_feasibility_stop"
    assert any(x["kind"] == "donor_yield_stop" for x in log.read())


def test_donor_acquisition_never_exceeds_the_cap(tmp_path):
    log = RunLog(tmp_path / "l.jsonl")
    with pytest.raises(BudgetStop):
        acquire_donors(log, Budget(log), lambda s, r: "PASS")
    assert sum(1 for x in log.read() if x["kind"] == "donor") == P.DONOR_CAP


# ── budget, §6.2 ──
def test_billing_must_be_entered_not_estimated(tmp_path):
    b = Budget(RunLog(tmp_path / "l.jsonl"))
    with pytest.raises(BudgetStop) as e:
        b.check("after_setup")
    assert e.value.kind == "no_billing_reading"


@pytest.mark.parametrize("usd,cp,kind", [
    (10.0, "after_setup", None),
    (84.9, "before_block", None),
    (85.0, "before_block", "no_new_block"),
    (85.0, "after_setup", None),          # gates blocks only
    (90.0, "after_donors", "stop_stage"),
    (100.0, "after_setup", "absolute"),
])
def test_threshold_state_machine(tmp_path, usd, cp, kind):
    b = Budget(RunLog(tmp_path / "l.jsonl"))
    b.record_reading(usd)
    if kind is None:
        assert b.check(cp, 0)["usd"] == usd
    else:
        with pytest.raises(BudgetStop) as e:
            b.check(cp, 0)
        assert e.value.kind == kind


def test_forecast_only_at_registered_checkpoints(tmp_path):
    b = Budget(RunLog(tmp_path / "l.jsonl"))
    b.record_reading(1.0)
    with pytest.raises(ValueError, match="fixes when a forecast"):
        b.check("mid_block")


def test_an_estimate_warns_but_never_authorises(tmp_path):
    """It is logged, and it is refused as authority — for any checkpoint."""
    log = RunLog(tmp_path / "l.jsonl"); b = Budget(log)
    b.record_reading(5.0, source="estimate")
    for cp in P.CHECKPOINTS:
        with pytest.raises(BudgetStop) as e:
            b.check(cp, 0)
        assert e.value.kind == "estimate_only"
    refusals = [r for r in log.read() if r["kind"] == "budget_refused"]
    assert refusals and all(r["reason"] == "estimate_only" for r in refusals)


def test_one_reading_authorises_one_block(tmp_path):
    log = RunLog(tmp_path / "l.jsonl"); b = Budget(log)
    b.record_reading(5.0)
    assert b.check("before_block", 0)["usd"] == 5.0
    with pytest.raises(BudgetStop) as e:
        b.check("before_block", 1)
    assert e.value.kind == "stale_reading"
    b.record_reading(6.0)
    assert b.check("before_block", 1)["usd"] == 6.0


def test_log_is_append_only(tmp_path):
    log = RunLog(tmp_path / "l.jsonl")
    log.append("a", v=1); log.append("b", v=2)
    assert [r["kind"] for r in log.read()] == ["a", "b"]
    assert len(log.path.read_text().strip().splitlines()) == 2


# ── fail-closed session binding, §1 ──
def fp(**over):
    base = {"hostname": "h1", "boot_id": "b1", "machine": "x86_64",
            "gpu": "GPU-1", "vllm_pid": "42"}
    return base | over


@pytest.mark.parametrize("field", ["hostname", "boot_id", "gpu", "vllm_pid", "machine"])
def test_refuses_to_resume_a_different_session(tmp_path, field):
    log = RunLog(tmp_path / "l.jsonl")
    bind_session(log, fp())
    with pytest.raises(FailClosed, match="not the session"):
        bind_session(log, fp(**{field: "other"}))


def test_resumes_the_same_session(tmp_path):
    log = RunLog(tmp_path / "l.jsonl")
    bind_session(log, fp())
    bind_session(log, fp())          # no raise
    assert sum(1 for r in log.read() if r["kind"] == "session") == 1


def test_refuses_when_the_protocol_hash_changed(tmp_path, monkeypatch):
    log = RunLog(tmp_path / "l.jsonl")
    bind_session(log, fp())
    monkeypatch.setattr(P, "protocol_hash", lambda: "deadbeefdeadbeef")
    with pytest.raises(FailClosed, match="protocol hash changed"):
        bind_session(log, fp())


# ── hashes ──
def test_hashes_are_stable_and_donor_order_is_part_of_the_manifest():
    a, b = plan(donors()), plan(donors())
    assert a["manifest_hash"] == b["manifest_hash"]
    assert a["protocol_hash"] == P.protocol_hash()
    d = donors(); d[0], d[1] = d[1], d[0]
    assert plan(d)["manifest_hash"] != a["manifest_hash"]


def test_protocol_hash_tracks_the_registered_values(monkeypatch):
    before = P.protocol_hash()
    monkeypatch.setattr(P, "HORIZONS", (16, 24, 32))
    assert P.protocol_hash() != before

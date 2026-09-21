"""Gate 2 pilot: frozen protocol, execution order, terminations and stops.

Fake backend only. No model, no container, no network.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from agentseism import pilot_protocol as P
from agentseism.budget import Budget, BudgetStop, RunLog
from agentseism.pilot import (
    PilotStop, cell_validity, completed_cells, fake_backend, main, run_pilot,
    verify_artifact,
)


def _budget(out: Path):
    from agentseism.pilot import PILOT_THRESHOLDS
    log = RunLog(out / "run.jsonl")
    b = Budget(log, PILOT_THRESHOLDS)
    b.record_baseline(0.0, billing_period="t")
    b.record_reading(0.0, billing_period="t")     # the after-setup reading
    b.check("after_setup")                        # taken by the caller, not the runner
    return log, b


def _run(out: Path, backend=fake_backend, tasks=None):
    log, b = _budget(out)
    return run_pilot(out, backend, tasks, True, log, b,
                     on_block=lambda blk: b.record_reading(0.0,
                                                           billing_period="t"))


# ── the registered plan ──
def test_eighteen_cells_each_exactly_once():
    cells = P.verify()
    assert len(cells) == P.CELLS == 18
    keys = [(c["replicate"], c["task"], c["arm"]) for c in cells]
    assert len(set(keys)) == 18


def test_the_order_hash_matches_the_frozen_value():
    assert P.order_hash(P.build_order()) == P.ORDER_HASH == "cfe8856c9c9167b5"


def test_a_changed_seed_fails_closed(monkeypatch):
    monkeypatch.setattr(P, "ORDER_SEED", 1)
    with pytest.raises(P.ProtocolMismatch, match="not the registered plan"):
        P.verify()


def test_the_hash_is_over_positions_so_drawn_task_ids_do_not_break_it():
    """Task ids are drawn on the instance and cannot be known at registration."""
    a = P.verify(["django__x", "flask__y", "sympy__z"])
    b = P.verify(["numpy__1", "scipy__2", "pandas__3"])
    assert [c["arm"] for c in a] == [c["arm"] for c in b]


def test_the_order_is_interleaved_not_grouped_by_arm():
    arms = [c["arm"] for c in P.verify()]
    assert arms[:3] != arms[3:6]          # blocks differ
    assert len(set(arms[:6])) == 3        # all three appear early


# ── the arms differ on exactly the registered axis ──
def test_m1_differs_from_baseline_only_in_step_limit():
    b, m = P.ARMS["baseline"], P.ARMS["M1"]
    assert {k for k in b if b[k] != m[k]} == {"step_limit"}
    assert m["step_limit"] == 40 and b["step_limit"] == 250


def test_m2_differs_from_baseline_only_in_the_hint():
    b, m = P.ARMS["baseline"], P.ARMS["M2"]
    assert {k for k in b if b[k] != m[k]} == {"hint"}
    assert m["hint"] == "error_only"


def test_every_arm_carries_the_shared_challenge():
    assert all(a["challenge"] for a in P.ARMS.values())


# ── terminations are separate meanings ──
def test_step_limit_and_infrastructure_timeout_are_distinct_codes():
    assert P.STEP_LIMIT_REACHED != P.INFRA_TIMEOUT_1200S
    assert P.STEP_LIMIT_REACHED in P.SCORABLE
    assert P.INFRA_TIMEOUT_1200S not in P.SCORABLE


def test_a_censored_run_cannot_enter_a_success_rate():
    """The budget cap must never be able to manufacture a regression."""
    for code in (P.INFRA_TIMEOUT_1200S, P.INVALID, P.NOT_ELIGIBLE):
        assert code not in P.SCORABLE


def test_not_eligible_is_outside_the_recovery_denominator():
    assert P.NOT_ELIGIBLE not in P.RECOVERY_DENOMINATOR


def test_an_unknown_termination_stops_the_run(tmp_path):
    with pytest.raises(PilotStop, match="unknown termination"):
        _run(tmp_path, backend=lambda c: {"termination": "SORT_OF_OK"})


# ── cells need 2 of 2 ──
def test_a_cell_needs_two_valid_runs_to_be_interpretable():
    runs = [{"task": "t", "arm": "M1", "termination": P.COMPLETED},
            {"task": "t", "arm": "M1", "termination": P.NOT_ELIGIBLE}]
    v = cell_validity(runs)[("t", "M1")]
    assert v["valid"] == 1 and v["interpretable"] is False


def test_two_valid_runs_are_interpretable():
    runs = [{"task": "t", "arm": "M1", "termination": P.COMPLETED},
            {"task": "t", "arm": "M1", "termination": P.STEP_LIMIT_REACHED}]
    assert cell_validity(runs)[("t", "M1")]["interpretable"] is True


def test_no_third_replicate_is_ever_attempted(tmp_path):
    seen = []
    _run(tmp_path, backend=lambda c: (seen.append((c["task"], c["arm"])),
                                      {"termination": P.NOT_ELIGIBLE})[1])
    from collections import Counter
    assert set(Counter(seen).values()) == {P.REPLICATES}


# ── budget ──
@pytest.mark.parametrize("usd,kind", [(19.0, None), (25.0, "no_new_block"),
                                      (30.0, "absolute")])
def test_budget_thresholds_on_pilot_spend(tmp_path, usd, kind):
    log = RunLog(tmp_path / "l.jsonl")
    b = Budget(log, __import__("agentseism.pilot", fromlist=["x"]).PILOT_THRESHOLDS)
    b.record_baseline(500.0, billing_period="t")       # account history
    b.record_reading(500.0 + usd, billing_period="t")
    if kind is None:
        assert b.check("before_block", 0)["usd"] == usd
    else:
        with pytest.raises(BudgetStop) as e:
            b.check("before_block", 0)
        assert e.value.kind == kind


# The registration says $20 warning / $25 no new block / $30 absolute, and $20
# was registered and then left out of the code, so a run crossing it said
# nothing. These three pin the boundary and, more importantly, pin that the
# warning refuses nothing: $20.00 must still return a state, not raise.
@pytest.mark.parametrize("usd,warn,kind", [(19.99, False, None),
                                           (20.00, True, None),
                                           (24.99, True, None),
                                           (25.00, True, "no_new_block")])
def test_warning_reports_without_stopping(tmp_path, usd, warn, kind):
    from agentseism.pilot import PILOT_THRESHOLDS
    log = RunLog(tmp_path / "l.jsonl"); b = Budget(log, PILOT_THRESHOLDS)
    b.record_baseline(500.0, billing_period="t")       # account history
    b.record_reading(500.0 + usd, billing_period="t")
    if kind is None:
        state = b.check("before_block", 0)
        assert state["usd"] == usd
        assert state["warning"] is warn
        assert state["warning_at"] == P.WARNING_USD
        logged = [r for r in log.read() if r["kind"] == "budget_warning"]
        assert len(logged) == (1 if warn else 0)
        assert [r for r in log.read() if r["kind"] == "budget_ok"]
    else:
        with pytest.raises(BudgetStop) as e:
            b.check("before_block", 0)
        assert e.value.kind == kind


def test_warning_is_optional_and_absent_for_c2h(tmp_path):
    """C2-H registered no warning level, and an absent one must not read as 0."""
    log = RunLog(tmp_path / "l.jsonl"); b = Budget(log)     # falls back to P.BUDGET
    b.record_baseline(0.0, billing_period="t")
    b.record_reading(50.0, billing_period="t")
    state = b.check("before_block", 0)
    assert state["warning"] is False and state["warning_at"] is None
    assert not [r for r in log.read() if r["kind"] == "budget_warning"]


def test_the_protocol_hash_is_the_registered_one():
    """Pinned so a registered value cannot move without this line moving too.

    `3ee68b88bb99894d` was the value through amendment P.2; wiring up the $20
    warning did not move it, because WARNING_USD was already inside the hash.
    Amendment P.3 moved it to `e1f786939faeb9ea` by putting the task-selection
    rule inside, which is the point of P.3: how the tasks are drawn is part of
    the design. P.5 moved it again to `a23ff8975a04f627` by putting the two
    recovery-hint templates inside: the hint text *is* M2's mutation. P.6 moved
    it again by registering the exit-status mapping and the scorable set.
    """
    assert P.protocol_hash() == "5f4b95c9a250fccf"


def test_no_new_block_after_the_threshold(tmp_path):
    from agentseism.pilot import PILOT_THRESHOLDS
    log = RunLog(tmp_path / "l.jsonl"); b = Budget(log, PILOT_THRESHOLDS)
    b.record_baseline(0.0, billing_period="t")
    with pytest.raises(BudgetStop):
        b.record_reading(P.NO_NEW_BLOCK_USD, billing_period="t")
        b.check("before_block", 5)


def test_resume_never_resets_the_baseline(tmp_path):
    log = RunLog(tmp_path / "l.jsonl"); b = Budget(log)
    b.record_baseline(120.0, billing_period="t")
    with pytest.raises(BudgetStop, match="not re-entered"):
        b.record_baseline(0.0, billing_period="t")


def test_an_estimate_cannot_authorise_a_block(tmp_path):
    log = RunLog(tmp_path / "l.jsonl"); b = Budget(log)
    b.record_baseline(0.0, billing_period="t")
    b.record_reading(1.0, source="estimate", billing_period="t")
    with pytest.raises(BudgetStop) as e:
        b.check("before_block", 0)
    assert e.value.kind == "estimate_only"


@pytest.mark.parametrize("field,value", [("billing_period", "other"),
                                         ("currency", "EUR")])
def test_a_changed_billing_period_or_currency_stops(tmp_path, field, value):
    log = RunLog(tmp_path / "l.jsonl"); b = Budget(log)
    b.record_baseline(10.0, billing_period="t", currency="USD")
    b.record_reading(11.0, **{field: value})
    with pytest.raises(BudgetStop):
        b.check("after_setup")


# ── artifacts, resume, and synthetic isolation ──
def test_all_eighteen_artifacts_are_frozen_with_digests(tmp_path):
    rep = _run(tmp_path)
    files = sorted((tmp_path / "runs").glob("run_*.json"))
    assert len(files) == 18
    assert all(verify_artifact(f) for f in files)
    assert rep["cells_done"] == 18


def test_a_tampered_artifact_is_not_a_completed_cell(tmp_path):
    _run(tmp_path)
    f = sorted((tmp_path / "runs").glob("run_*.json"))[0]
    f.write_text(json.dumps({"order_index": 0, "tampered": True}))
    assert not verify_artifact(f)
    assert 0 not in completed_cells(tmp_path)


def test_resume_reruns_only_the_missing_cells(tmp_path):
    _run(tmp_path)
    f = sorted((tmp_path / "runs").glob("run_*.json"))[3]
    f.unlink(); Path(str(f) + ".sha256").unlink()
    assert len(completed_cells(tmp_path)) == 17
    ran = []
    log = RunLog(tmp_path / "run.jsonl")
    b = Budget(log)
    b.record_reading(0.0, billing_period="t")
    run_pilot(tmp_path, lambda c: (ran.append(c["order_index"]),
                                   fake_backend(c))[1], None, True, log, b,
              on_block=lambda blk: b.record_reading(0.0, billing_period="t"))
    assert ran == [3]


def test_the_pilot_never_claims_a_release_verdict(tmp_path):
    assert _run(tmp_path)["verdict_allowed"] is False


def test_every_artifact_is_marked_synthetic(tmp_path):
    _run(tmp_path)
    for f in (tmp_path / "runs").glob("run_*.json"):
        d = json.loads(f.read_text())
        assert d["synthetic"] is True
        assert d["protocol_hash"] == P.protocol_hash()


def test_fake_output_goes_to_a_synthetic_directory(tmp_path, capsys):
    main(["--backend", "fake", "--out", str(tmp_path)])
    assert (tmp_path / "synthetic" / "runs").is_dir()
    assert not (tmp_path / "runs").exists()
    assert "not pilot evidence" in capsys.readouterr().out


# ── CLI gates ──
def test_real_backend_needs_the_confirmation_flag():
    with pytest.raises(SystemExit) as e:
        main(["--backend", "real", "--out", "/tmp/nope"])
    assert "--execute-registered-pilot" in str(e.value)


def test_real_backend_is_not_wired_locally():
    with pytest.raises(SystemExit) as e:
        main(["--backend", "real", "--execute-registered-pilot",
              "--out", "/tmp/nope"])
    assert "six deployment checks" in str(e.value)


def test_resolve_only_writes_nothing(tmp_path, capsys):
    assert main(["--resolve-only", "--out", str(tmp_path)]) == 0
    assert not any(tmp_path.iterdir())
    out = capsys.readouterr().out
    assert P.ORDER_HASH in out and "RESOLVE-ONLY: PASS" in out


def test_no_frozen_parameter_is_a_cli_flag():
    import argparse
    import inspect
    src = inspect.getsource(main)
    for forbidden in ("--step-limit", "--trials", "--replicates", "--timeout",
                      "--budget", "--arms", "--seed", "--order"):
        assert forbidden not in src
    del argparse

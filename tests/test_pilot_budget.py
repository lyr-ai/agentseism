"""A checkpoint is a reading, not a moment.

The launch reading satisfied `after_setup` while dependency installs, image
pulls and 31 GB of weights were still absent from the billing page: the state
machine passed and missed the entire cost of setup. These pin the guard.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from agentseism.budget import Budget, BudgetStop, RunLog
from agentseism.pilot import PILOT_THRESHOLDS
from agentseism.pilot_budget import main, phase_ts

LAUNCH = "2026-09-21T17:20:00Z"
SETUP = "2026-09-21T17:30:00Z"
LATER = "2026-09-21T19:05:00Z"


def _log(tmp_path, reading=7.34, reading_ts=LAUNCH):
    log = RunLog(tmp_path / "run.jsonl")
    b = Budget(log, PILOT_THRESHOLDS)
    b.record_baseline(7.16, billing_period="September 2026", currency="USD")
    b.record_reading(reading, billing_period="September 2026", currency="USD")
    # The log stamps its own ts; rewrite the reading's to the moment under test.
    rows = [l for l in (tmp_path / "run.jsonl").read_text().splitlines()]
    rows[-1] = rows[-1].replace(_ts_of(rows[-1]), reading_ts)
    (tmp_path / "run.jsonl").write_text("\n".join(rows) + "\n")
    return log, Budget(log, PILOT_THRESHOLDS)


def _ts_of(row: str) -> str:
    import json
    return json.loads(row)["ts"]


def test_a_reading_older_than_the_work_authorises_nothing(tmp_path):
    log, b = _log(tmp_path)
    with pytest.raises(BudgetStop) as e:
        b.check("after_setup", not_before=SETUP)
    assert e.value.kind == "reading_predates_spend"
    assert "before" in e.value.detail
    assert [r for r in log.read() if r["kind"] == "budget_refused"]


def test_the_same_reading_passes_without_the_guard(tmp_path):
    """Which is exactly the hole: the old call site passed no moment."""
    _, b = _log(tmp_path)
    assert b.check("after_setup")["usd"] == 0.18


def test_a_reading_taken_after_the_work_is_accepted(tmp_path):
    log, b = _log(tmp_path, reading=7.34, reading_ts=LATER)
    s = b.check("after_setup", not_before=SETUP)
    assert s["usd"] == 0.18 and s["checkpoint"] == "after_setup"


def test_the_guard_is_a_time_compare_not_a_sequence_compare(tmp_path):
    """A second reading entered late still fails if it was read early."""
    log, b = _log(tmp_path)
    b.record_reading(7.40, billing_period="September 2026", currency="USD")
    rows = (tmp_path / "run.jsonl").read_text().splitlines()
    rows[-1] = rows[-1].replace(_ts_of(rows[-1]), LAUNCH)
    (tmp_path / "run.jsonl").write_text("\n".join(rows) + "\n")
    with pytest.raises(BudgetStop) as e:
        Budget(log, PILOT_THRESHOLDS).check("after_setup", not_before=SETUP)
    assert e.value.kind == "reading_predates_spend"


# ── the CLI ──
def test_the_phase_marker_is_how_a_moment_enters_the_log(tmp_path):
    log, _ = _log(tmp_path)
    log.append("phase", name="setup_started")
    rc = main(["--log", str(tmp_path / "run.jsonl"), "--reading", "9.10",
               "--checkpoint", "after_setup", "--not-before", "@setup_started"])
    assert rc == 0
    ok = [r for r in log.read() if r["kind"] == "budget_ok"]
    assert ok and ok[-1]["usd"] == 1.94


def test_an_unrecorded_phase_is_refused_rather_than_ignored(tmp_path):
    _log(tmp_path)
    with pytest.raises(SystemExit):
        main(["--log", str(tmp_path / "run.jsonl"), "--reading", "9.10",
              "--checkpoint", "after_setup", "--not-before", "@never_written"])


def test_a_stale_checkpoint_is_annotated_never_rewritten(tmp_path):
    log, b = _log(tmp_path)
    b.check("after_setup")                      # the meaningless one
    before = (tmp_path / "run.jsonl").read_text()

    rc = main(["--log", str(tmp_path / "run.jsonl"),
               "--supersede-checkpoint", "after_setup",
               "--reason", "authorised by the launch reading; setup spend was "
                           "not yet on the page"])
    assert rc == 0
    after = (tmp_path / "run.jsonl").read_text()
    assert after.startswith(before), "the original bytes are untouched"
    sup = [r for r in log.read() if r["kind"] == "budget_superseded"]
    assert len(sup) == 1
    assert sup[0]["checkpoint"] == "after_setup"
    assert sup[0]["supersedes_usd"] == 0.18


def test_superseding_requires_a_reason(tmp_path):
    log, b = _log(tmp_path)
    b.check("after_setup")
    assert main(["--log", str(tmp_path / "run.jsonl"),
                 "--supersede-checkpoint", "after_setup"]) == 2


def test_superseding_a_checkpoint_that_was_never_taken_is_refused(tmp_path):
    _log(tmp_path)
    assert main(["--log", str(tmp_path / "run.jsonl"),
                 "--supersede-checkpoint", "after_setup",
                 "--reason", "x"]) == 2


def test_status_marks_the_superseded_record(tmp_path, capsys):
    log, b = _log(tmp_path)
    b.check("after_setup")
    main(["--log", str(tmp_path / "run.jsonl"),
          "--supersede-checkpoint", "after_setup", "--reason", "stale"])
    main(["--log", str(tmp_path / "run.jsonl"), "--status"])
    out = capsys.readouterr().out
    assert "SUPERSEDED" in out
    assert "$7.16" in out and "$7.34" in out


def test_a_checkpoint_past_the_ceiling_stops(tmp_path):
    log, _ = _log(tmp_path)
    log.append("phase", name="setup_started")
    rc = main(["--log", str(tmp_path / "run.jsonl"), "--reading", "40.00",
               "--checkpoint", "after_setup", "--not-before", "@setup_started"])
    assert rc == 1
    assert [r for r in log.read() if r["kind"] == "budget_stop"]


# ── the runner reads its authorisation, it does not spend it ──
def _pilot_log(tmp_path):
    log = RunLog(tmp_path / "run.jsonl")
    b = Budget(log, PILOT_THRESHOLDS)
    b.record_baseline(0.0, billing_period="t", currency="USD")
    return log, b


def test_the_runner_refuses_without_an_after_setup_authorisation(tmp_path):
    from agentseism.pilot import PilotStop, fake_backend, run_pilot
    log, b = _pilot_log(tmp_path)
    b.record_reading(0.0, billing_period="t")
    with pytest.raises(PilotStop) as e:
        run_pilot(tmp_path, fake_backend, None, True, log, b)
    assert "no un-superseded after_setup authorisation" in str(e.value)


def test_a_superseded_authorisation_does_not_authorise(tmp_path):
    from agentseism.pilot import PilotStop, fake_backend, run_pilot
    log, b = _pilot_log(tmp_path)
    b.record_reading(0.0, billing_period="t")
    b.check("after_setup")
    main(["--log", str(tmp_path / "run.jsonl"),
          "--supersede-checkpoint", "after_setup", "--reason", "stale"])
    with pytest.raises(PilotStop):
        run_pilot(tmp_path, fake_backend, None, True, RunLog(tmp_path / "run.jsonl"),
                  Budget(RunLog(tmp_path / "run.jsonl"), PILOT_THRESHOLDS))


def test_the_runner_does_not_consume_the_first_blocks_reading(tmp_path):
    """The regression. `check("after_setup")` inside the runner burned the
    reading entered for block 0, so the block then demanded another one."""
    from agentseism.pilot import fake_backend, run_pilot
    log, b = _pilot_log(tmp_path)
    b.record_reading(0.0, billing_period="t")       # seq 1, for after_setup
    b.check("after_setup")                          # consumes seq 1
    b.record_reading(0.0, billing_period="t")       # seq 2, for block 0

    # No on_block hook: block 0 must be authorised by the reading already
    # entered for it. Under the old code the runner had spent seq 2 and this
    # raised stale_reading.
    rep = run_pilot(tmp_path, fake_backend, None, True, log, b,
                    on_block=lambda blk: b.record_reading(0.0, billing_period="t")
                    if blk != (0, "task_1") else None)
    assert rep["cells_done"] == 18
    reads = [r for r in log.read() if r["kind"] == "authorisation_read"]
    assert len(reads) == 1 and reads[0]["checkpoint"] == "after_setup"
    # exactly one after_setup budget_ok: the runner added none
    assert len([r for r in log.read()
                if r["kind"] == "budget_ok"
                and r.get("checkpoint") == "after_setup"]) == 1


def test_authorisation_returns_the_latest_un_superseded(tmp_path):
    log, b = _pilot_log(tmp_path)
    b.record_reading(1.0, billing_period="t")
    b.check("after_setup")
    main(["--log", str(tmp_path / "run.jsonl"),
          "--supersede-checkpoint", "after_setup", "--reason", "first was wrong"])
    b2 = Budget(RunLog(tmp_path / "run.jsonl"), PILOT_THRESHOLDS)
    assert b2.authorisation("after_setup") is None
    b2.record_reading(2.0, billing_period="t")
    b2.check("after_setup")
    got = Budget(RunLog(tmp_path / "run.jsonl"), PILOT_THRESHOLDS).authorisation("after_setup")
    assert got is not None and got["usd"] == 2.0


def test_two_records_in_one_second_are_still_distinguishable(tmp_path):
    """`ts` has second resolution. It was the supersede key, so a checkpoint
    written in the same second as the annotation's target was swept up with
    it -- and an authorisation vanished that nobody had superseded."""
    log = RunLog(tmp_path / "run.jsonl")
    a = log.append("budget_ok", checkpoint="after_setup", usd=1.0)
    b = log.append("budget_ok", checkpoint="after_setup", usd=2.0)
    assert a["ts"] == b["ts"], "this test is only meaningful within one second"
    assert a["n"] != b["n"]
    log.append("budget_superseded", checkpoint="after_setup",
               supersedes_n=a["n"], supersedes_ts=a["ts"], reason="x")
    got = Budget(RunLog(tmp_path / "run.jsonl"), PILOT_THRESHOLDS) \
        .authorisation("after_setup")
    assert got is not None and got["usd"] == 2.0


def test_records_written_before_n_existed_are_still_honoured(tmp_path):
    """The host-2 log was written without `n`; its annotations name a ts."""
    p = tmp_path / "run.jsonl"
    p.write_text(
        '{"ts": "2026-09-21T17:45:29Z", "kind": "budget_ok", '
        '"checkpoint": "after_setup", "usd": 0.18}\n'
        '{"ts": "2026-09-21T17:47:03Z", "kind": "budget_superseded", '
        '"checkpoint": "after_setup", "supersedes_ts": "2026-09-21T17:45:29Z", '
        '"reason": "pre-setup reading"}\n')
    assert Budget(RunLog(p), PILOT_THRESHOLDS).authorisation("after_setup") is None


def test_after_setup_can_be_required_to_postdate_the_smoke_test(tmp_path):
    """P.4: the checkpoint must cover the smoke test's cost, not only setup's.
    A reading taken between setup and the smoke run is refused."""
    log, b = _log(tmp_path, reading_ts="2026-09-21T18:00:00Z")
    log.append("phase", name="setup_started")
    rows = (tmp_path / "run.jsonl").read_text().splitlines()
    rows[-1] = rows[-1].replace(_ts_of(rows[-1]), "2026-09-21T17:50:00Z")
    (tmp_path / "run.jsonl").write_text("\n".join(rows) + "\n")
    log2 = RunLog(tmp_path / "run.jsonl")
    log2.append("phase", name="smoke_completed")
    rows = (tmp_path / "run.jsonl").read_text().splitlines()
    rows[-1] = rows[-1].replace(_ts_of(rows[-1]), "2026-09-21T18:30:00Z")
    (tmp_path / "run.jsonl").write_text("\n".join(rows) + "\n")

    b2 = Budget(RunLog(tmp_path / "run.jsonl"), PILOT_THRESHOLDS)
    with pytest.raises(BudgetStop) as e:
        b2.check("after_setup", not_before=phase_ts(
            RunLog(tmp_path / "run.jsonl"), "smoke_completed"))
    assert e.value.kind == "reading_predates_spend"
    # the same reading would have satisfied the weaker marker
    assert b2.check("after_setup", not_before=phase_ts(
        RunLog(tmp_path / "run.jsonl"), "setup_started"))["usd"] == 0.18


# ── the baseline survives the host ──
REAL_LOG = Path(__file__).resolve().parents[1] / "data/runs/pilot/run.jsonl"


def test_host_3_does_not_start_the_budget_over(tmp_path):
    """The blocking case, checked against the real host-2 log.

    Host 2 spent $2.99 and that is part of the registered experiment cost. A
    host that re-based on its own start total would get a fresh $30, and the
    absolute stop would land at $37.16 + $30.
    """
    import shutil
    p = tmp_path / "run.jsonl"
    shutil.copy(REAL_LOG, p)
    b = Budget(RunLog(p), PILOT_THRESHOLDS)
    base = b.baseline()
    assert base["current_total"] == 7.16, "the origin moved"

    b.record_reading(10.15, source="manual", billing_period="September 2026",
                     currency="USD", note="host 3 launch")
    s = b.check("after_setup")
    assert s["usd"] == 2.99, "host 3 started the budget over"
    assert s["usd"] != 0.00


def test_the_baseline_cannot_be_reset_on_a_later_host(tmp_path):
    import shutil
    p = tmp_path / "run.jsonl"
    shutil.copy(REAL_LOG, p)
    b = Budget(RunLog(p), PILOT_THRESHOLDS)
    with pytest.raises(BudgetStop) as e:
        b.record_baseline(10.15, billing_period="September 2026")
    assert e.value.kind == "baseline_already_set"


@pytest.mark.parametrize("page_total,expect", [
    (27.16, "warning"), (32.16, "no_new_block"), (37.16, "absolute")])
def test_the_thresholds_sit_at_fixed_page_totals(tmp_path, page_total, expect):
    """The page totals the stops correspond to never move, whatever host is
    running."""
    import shutil
    p = tmp_path / "run.jsonl"
    shutil.copy(REAL_LOG, p)
    b = Budget(RunLog(p), PILOT_THRESHOLDS)
    b.record_reading(page_total, source="manual",
                     billing_period="September 2026", currency="USD")
    if expect == "warning":
        assert b.check("after_setup")["warning"] is True
    else:
        with pytest.raises(BudgetStop) as e:
            b.check("before_block", 0)
        assert e.value.kind == expect


def test_host_start_authorises_nothing(tmp_path):
    """It explains what a machine cost. It is not a checkpoint."""
    log, b = _pilot_log(tmp_path)
    log.append("host_start", host_id="h3", page_total=10.15)
    assert b.authorisation("after_setup") is None
    with pytest.raises(BudgetStop) as e:
        b.check("after_setup")
    assert e.value.kind == "no_billing_reading"


# ── the pre-rental observation ──
def test_observe_computes_spend_against_the_frozen_baseline(tmp_path, capsys):
    import shutil
    p = tmp_path / "run.jsonl"
    shutil.copy(REAL_LOG, p)
    assert main(["--log", str(p), "--observe", "10.15", "--period",
                 "September 2026", "--currency", "USD"]) == 0
    out = capsys.readouterr().out
    assert "cumulative_pilot_spend       $2.99" in out
    assert "$7.16" in out and "$37.16" in out


def test_observe_reflects_late_charges_rather_than_a_fixed_number(tmp_path, capsys):
    """Host 2's tail may still be landing; the figure is whatever the page
    says minus the frozen origin."""
    import shutil
    p = tmp_path / "run.jsonl"
    shutil.copy(REAL_LOG, p)
    main(["--log", str(p), "--observe", "10.62", "--period",
         "September 2026", "--currency", "USD"])
    assert "cumulative_pilot_spend       $3.46" in capsys.readouterr().out


def test_observe_authorises_nothing(tmp_path):
    import shutil
    p = tmp_path / "run.jsonl"
    shutil.copy(REAL_LOG, p)
    main(["--log", str(p), "--observe", "10.15", "--period",
         "September 2026", "--currency", "USD"])
    log = RunLog(p)
    obs = [r for r in log.read() if r["kind"] == "billing_observation"]
    assert obs and obs[-1]["instances_running"] == 0
    assert "authorises nothing" in obs[-1]["note"]
    # it is not a reading, so it cannot satisfy a checkpoint: the observation
    # adds no billing_reading, and last_billing() still returns the previous
    # host's, which the freshness guard will then refuse.
    before = [r for r in RunLog(REAL_LOG).read() if r["kind"] == "billing_reading"]
    after = [r for r in log.read() if r["kind"] == "billing_reading"]
    assert len(after) == len(before)
    assert log.last_billing()["kind"] == "billing_reading"


def test_observe_refuses_a_total_below_the_baseline(tmp_path):
    import shutil
    p = tmp_path / "run.jsonl"
    shutil.copy(REAL_LOG, p)
    assert main(["--log", str(p), "--observe", "5.00", "--period",
                 "September 2026", "--currency", "USD"]) == 2


@pytest.mark.parametrize("total,rc", [(27.16, 0), (32.16, 1), (37.16, 1)])
def test_observe_stops_before_renting_when_the_budget_is_spent(tmp_path, total, rc):
    import shutil
    p = tmp_path / "run.jsonl"
    shutil.copy(REAL_LOG, p)
    assert main(["--log", str(p), "--observe", str(total), "--period",
                 "September 2026", "--currency", "USD"]) == rc


def _real(tmp_path):
    import shutil
    p = tmp_path / "run.jsonl"
    shutil.copy(REAL_LOG, p)
    return p


def test_observe_requires_the_period_and_currency_from_the_page(tmp_path):
    """Copying them from the baseline would make the check unable to notice
    the one thing it exists to notice."""
    assert main(["--log", str(_real(tmp_path)), "--observe", "10.15"]) == 2


def test_observe_refuses_a_drifted_period(tmp_path):
    assert main(["--log", str(_real(tmp_path)), "--observe", "10.15",
                 "--period", "October 2026", "--currency", "USD"]) == 2


def test_observe_refuses_a_drifted_currency(tmp_path):
    assert main(["--log", str(_real(tmp_path)), "--observe", "10.15",
                 "--period", "September 2026", "--currency", "EUR"]) == 2


def test_observe_records_the_page_values_it_was_given(tmp_path):
    p = _real(tmp_path)
    assert main(["--log", str(p), "--observe", "10.15",
                 "--period", "September 2026", "--currency", "USD"]) == 0
    obs = [r for r in RunLog(p).read() if r["kind"] == "billing_observation"][-1]
    assert obs["billing_period"] == "September 2026"
    assert obs["currency"] == "USD"
    assert obs["observed_period_matches_baseline"] is True


def test_the_launch_reading_is_not_the_pre_launch_observation(tmp_path):
    """Two different facts. Calling the post-launch reading a 'host start
    total' would make the launch interval look uncounted."""
    p = _real(tmp_path)
    main(["--log", str(p), "--observe", "10.15",
          "--period", "September 2026", "--currency", "USD"])
    log = RunLog(p)
    log.append("host_launch_reading", host_id="h3", page_total=10.47,
               taken="after this host launched",
               note="manual page total read after launch. NOT a budget "
                    "baseline, NOT the pre-launch settled observation")
    rows = log.read()
    obs = [r for r in rows if r["kind"] == "billing_observation"][-1]
    launch = [r for r in rows if r["kind"] == "host_launch_reading"][-1]
    assert obs["current_total"] == 10.15 and obs["instances_running"] == 0
    assert launch["page_total"] == 10.47
    assert round(launch["page_total"] - obs["current_total"], 2) == 0.32
    # and neither is the origin
    assert Budget(log, PILOT_THRESHOLDS).baseline()["current_total"] == 7.16

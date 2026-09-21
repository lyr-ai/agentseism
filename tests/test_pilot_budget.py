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
from agentseism.pilot_budget import main

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

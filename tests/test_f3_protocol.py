"""F3 is a different experiment, and its evidence has to say so.

The pilot stopped on a host where `--backend real` had never been executed,
because every test verified a component and none verified the entry point. The
identity equivalent of that gap is asserting only what F3 *is* and never what
it must *not* be: `protocol_hash` and `order_hash` were module globals in
`pilot_protocol`, so a second experiment running on the same runner would have
stamped a closed experiment's name onto new evidence, and a positive-only test
would have passed throughout.

So the load-bearing test here is the negative one: run F3 end to end and assert
the closed pilot's two hashes appear nowhere in what it produced.
"""

from __future__ import annotations

import dataclasses
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from agentseism import f3_protocol as F           # noqa: E402
from agentseism import pilot_protocol as P        # noqa: E402
from agentseism import pilot                      # noqa: E402
from agentseism.budget import Budget, RunLog      # noqa: E402

PREREG = Path(__file__).resolve().parents[1] / "paper" / "PREREG_F3.md"

CLOSED_PILOT_PROTOCOL_HASH = "b7af66ca3ab783ab"
CLOSED_PILOT_ORDER_HASH = "cfe8856c9c9167b5"


def _run_f3(out: Path) -> dict:
    log = RunLog(out / "run.jsonl")
    b = Budget(log, F.SPEC.thresholds)
    b.record_baseline(0.0, billing_period="synthetic")
    b.record_reading(0.0, billing_period="synthetic")
    b.check("after_setup")
    b.record_reading(0.0, billing_period="synthetic")
    return pilot.run_pilot(out, pilot.fake_backend, [F.TASK], True, log, b,
                           spec=F.SPEC,
                           on_block=lambda blk: b.record_reading(
                               0.0, billing_period="synthetic"))


# ── the negative assertion ──
def test_no_f3_output_carries_the_closed_pilots_identity(tmp_path):
    """The check an identity claim is worthless without.

    Asserting F3's own hashes are present would pass even if the pilot's were
    printed beside them.
    """
    _run_f3(tmp_path)
    produced = [p for p in tmp_path.rglob("*") if p.is_file()]
    assert produced, "the run produced nothing to check"
    for path in produced:
        body = path.read_text(errors="replace")
        assert CLOSED_PILOT_PROTOCOL_HASH not in body, path
        assert CLOSED_PILOT_ORDER_HASH not in body, path


def test_f3_artifacts_carry_f3s_own_identity(tmp_path):
    _run_f3(tmp_path)
    runs = sorted((tmp_path / "runs").glob("run_*.json"))
    assert len(runs) == 3
    for path in runs:
        d = json.loads(path.read_text())
        assert d["protocol_hash"] == F.SPEC.protocol_hash
        assert d["order_hash"] == F.ORDER_HASH


def test_the_f3_report_names_the_experiment_and_its_cell_count(tmp_path):
    rep = _run_f3(tmp_path)
    assert rep["experiment"] == "f3"
    assert rep["cells_registered"] == 3
    assert rep["state"] == "complete_3"
    assert rep["verdict_allowed"] is False


# ── the registered plan ──
def test_f3_is_one_task_three_arms_one_replicate():
    cells = F.SPEC.verify([F.TASK])
    assert len(cells) == 3
    assert [c["arm"] for c in cells] == ["M2", "baseline", "M1"]
    assert {c["task"] for c in cells} == {F.TASK}
    assert {c["replicate"] for c in cells} == {0}


def test_f3_refuses_a_task_list_that_is_not_the_registered_shape():
    with pytest.raises(P.ProtocolMismatch, match="need 1 tasks"):
        F.SPEC.verify([F.TASK, "django__django-10097"])


def test_a_changed_f3_seed_fails_closed():
    tampered = dataclasses.replace(F.SPEC, order_seed=1)
    with pytest.raises(P.ProtocolMismatch, match="not the registered plan"):
        tampered.verify([F.TASK])


# ── the two identities are distinct, and the pilot's is untouched ──
def test_the_two_experiments_do_not_share_an_identity():
    assert F.SPEC.protocol_hash != P.SPEC.protocol_hash
    assert F.SPEC.order_hash != P.SPEC.order_hash
    assert F.SPEC.name != P.SPEC.name


def test_the_closed_pilots_identity_is_unchanged_by_the_refactor():
    """The pilot is closed. Its hashes are historical facts about recorded
    evidence, and a refactor that moved them would invalidate the record."""
    assert P.protocol_hash() == CLOSED_PILOT_PROTOCOL_HASH
    assert P.SPEC.protocol_hash == CLOSED_PILOT_PROTOCOL_HASH
    assert P.ORDER_HASH == CLOSED_PILOT_ORDER_HASH


def test_changing_a_registered_f3_value_moves_its_hash(monkeypatch):
    before = F.protocol_hash()
    monkeypatch.setattr(F, "ABSOLUTE_LIMIT_USD", 99.0)
    assert F.protocol_hash() != before


# ── the mechanism is shared, not copied ──
def test_f3_reuses_the_pilots_mechanism_objects_identically():
    """Not merely equal -- the same objects.

    Copies would drift, and the drift would be invisible until one experiment
    produced evidence the other could not.
    """
    assert F.ARMS is P.ARMS
    assert F.HINT_SHA256 is P.HINT_SHA256
    assert F.EXIT_STATUS_MAP is P.EXIT_STATUS_MAP
    assert F.RUN_TIMEOUT_SECONDS == P.RUN_TIMEOUT_SECONDS
    assert F.SCORABLE is P.SCORABLE


def test_there_is_exactly_one_runner():
    """No `f3_pilot.py`, no second backend. The injection exists so that both
    registrations execute the same code path."""
    src = Path(__file__).resolve().parents[1] / "src" / "agentseism"
    assert not list(src.glob("f3_pilot*.py"))
    assert not list(src.glob("f3_backend*.py"))
    assert not list(src.glob("f3_real_backend*.py"))
    assert pilot.SPECS == {"pilot": P.SPEC, "f3": F.SPEC}


# ── the module agrees with the registration document ──
def test_the_registered_numbers_match_the_prereg_document():
    """A constant that silently disagrees with the prose it claims to encode
    is the failure `test_preflight_constants.py` exists to prevent."""
    doc = PREREG.read_text()
    for needle in (F.TASK, F.ORDER_HASH, "20260923",
                   "**$8**", "**$10**", "**$12**", "3.5 hours",
                   "$9.72", F.PASS_CLAIM):
        assert needle in doc, needle


def test_the_budget_numbers_are_the_registered_ones():
    assert (F.WARNING_USD, F.NO_NEW_BLOCK_USD, F.ABSOLUTE_LIMIT_USD) == \
        (8.0, 10.0, 12.0)
    assert F.HOST_WALL_CLOCK_SECONDS == 3.5 * 3600
    assert F.SPEC.thresholds["stop_stage"] == float("inf")


def test_f3_thresholds_are_strictly_below_the_pilots():
    """A smaller experiment must not inherit a larger budget by omission."""
    assert F.ABSOLUTE_LIMIT_USD < P.ABSOLUTE_LIMIT_USD
    assert F.NO_NEW_BLOCK_USD < P.NO_NEW_BLOCK_USD
    assert F.WARNING_USD < P.WARNING_USD


def test_the_closed_pilots_spend_is_carried_not_erased():
    """F3 has its own baseline for its own spend; that is not a reset of the
    programme's cost history."""
    assert F.CLOSED_PILOT_SPEND_USD == 9.72
    doc = PREREG.read_text()
    assert "combined project spend" in doc


def test_f3_registers_no_separate_paid_smoke():
    assert F.NO_SEPARATE_SMOKE is True
    # Normalised: the document wraps and bolds, and neither is the point.
    flat = " ".join(PREREG.read_text().replace("*", "").split()).lower()
    assert "cell 1 is the composition test" in flat


def test_forbidden_claims_are_registered_not_left_to_tone():
    for word in ("stable", "stability", "reliable", "reliability"):
        assert word in F.FORBIDDEN_CLAIMS
    assert F.PASS_CLAIM == "one_shot_execution_feasibility_established"

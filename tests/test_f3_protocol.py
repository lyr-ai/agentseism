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
import re
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
    import agentseism.engineering_protocol as E
    assert pilot.SPECS == {"pilot": P.SPEC, "f3": F.SPEC,
                           "engineering": E.SPEC}


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


# ── the launch path: a READY report is a statement about one registration ──
def _report(**over) -> dict:
    base = {"experiment": "f3", "protocol_hash": F.SPEC.protocol_hash,
            "order_hash": F.ORDER_HASH, "expected_cells": 3}
    base.update(over)
    return base


def test_f3_refuses_a_preflight_report_that_is_the_pilots():
    """The gap found before paying for a host.

    A preflight proving the 18-cell pilot READY says nothing about a 3-cell
    run. Binding one to the other is host 5 again: components verified, the
    thing actually launched never checked.
    """
    with pytest.raises(pilot.PilotStop, match="for experiment 'pilot'"):
        pilot._check_report_identity(
            _report(experiment="pilot",
                    protocol_hash=CLOSED_PILOT_PROTOCOL_HASH,
                    order_hash=CLOSED_PILOT_ORDER_HASH,
                    expected_cells=18), F.SPEC)


def test_f3_refuses_a_legacy_report_with_no_identity_at_all():
    """Reports written before the preflight recorded an identity carry none of
    these fields. They cannot prove which registration they came from, so F3
    refuses them rather than assuming."""
    with pytest.raises(pilot.PilotStop, match="legacy pilot report"):
        pilot._check_report_identity({"status": "READY"}, F.SPEC)


def test_the_pilot_still_accepts_its_own_legacy_reports():
    """Unchanged on purpose. Rewriting a closed experiment's audit record to
    satisfy a new one would damage evidence to save a branch."""
    pilot._check_report_identity({"status": "READY"}, P.SPEC)


@pytest.mark.parametrize("field,value", [
    ("protocol_hash", CLOSED_PILOT_PROTOCOL_HASH),
    ("order_hash", CLOSED_PILOT_ORDER_HASH),
    ("expected_cells", 18),
])
def test_each_identity_field_is_checked_not_just_the_name(field, value):
    """A report could name f3 and carry the pilot's plan."""
    with pytest.raises(pilot.PilotStop, match=field):
        pilot._check_report_identity(_report(**{field: value}), F.SPEC)


def test_a_matching_f3_report_is_accepted():
    pilot._check_report_identity(_report(), F.SPEC)


# ── the preflight script selects the same identity ──
def _script() -> str:
    return (Path(__file__).resolve().parents[1]
            / "inference/stage_b_preflight.sh").read_text()


def test_the_preflight_freezes_f3s_identity_from_the_module():
    """The script's literals and `f3_protocol` must agree, or the preflight
    would prove a registration nobody registered."""
    src = _script()
    for needle in (f'F3_PROTOCOL_HASH="{F.SPEC.protocol_hash}"',
                   f'F3_ORDER_HASH="{F.ORDER_HASH}"',
                   f"F3_EXPECTED_CELLS={F.SPEC.cell_count}",
                   f'F3_TASK="{F.TASK}"'):
        assert needle in src, needle


def test_the_preflight_report_records_the_identity_it_prepared():
    src = _script()
    for field in ("experiment", "protocol_hash", "order_hash",
                  "expected_cells"):
        assert f'"{field}": os.environ[' in src or \
               f'"{field}": int(os.environ[' in src, field


def test_the_preflight_resolves_the_selected_experiment():
    """`--resolve-only` without `--experiment` resolves the pilot, so a
    preflight preparing F3 that forgot the flag would check the wrong plan."""
    assert '--resolve-only --experiment "$EXPERIMENT"' in _script()


# ── the budget origin is experiment-selected, not the pilot's ──
def _const(name: str) -> str:
    m = re.search(rf'^{name}="?([^"\n]+)"?$', _script(), re.M)
    assert m, f"{name} not found in the preflight"
    return m.group(1)


def test_the_preflight_carries_f3s_own_budget_origin():
    """The gap that aborted the first F3 launch.

    `--experiment f3` selected the plan identity but not the budget, so step
    3b would have seeded the pilot's log, matched $7.16, computed
    18.16-7.16=$11.00 and passed it against $20/$25/$30 -- never consulting
    $16.88 or $8/$10/$12. It would not have errored, which is worse than a
    refusal: a silent wrong measurement.
    """
    assert _const("F3_BASELINE_USD") == "16.88"
    assert _const("F3_BASELINE_PERIOD") == "September 2026"
    assert _const("F3_BASELINE_CURRENCY") == "USD"
    assert _const("F3_RUN_LOG") == "data/runs/f3/run.jsonl"


def test_the_frozen_f3_baseline_is_what_the_preflight_expects():
    """The literal in the script and the log it will be checked against."""
    log = Path(__file__).resolve().parents[1] / "data/runs/f3/run.jsonl"
    base = [json.loads(l) for l in log.read_text().splitlines()
            if '"billing_baseline"' in l]
    assert len(base) == 1, "a baseline is entered once and never re-entered"
    assert base[0]["current_total"] == float(_const("F3_BASELINE_USD"))
    assert base[0]["billing_period"] == _const("F3_BASELINE_PERIOD")
    assert base[0]["currency"] == _const("F3_BASELINE_CURRENCY")


def test_the_pilots_budget_origin_is_untouched():
    assert _const("BASELINE_USD") == "7.16"
    assert _const("PILOT_RUN_LOG") == "data/runs/pilot/run.jsonl"


def test_the_preflight_reads_thresholds_from_the_selected_spec():
    """`from agentseism.pilot import PILOT_THRESHOLDS` in a step that runs for
    both experiments is the budget equivalent of a module-global hash."""
    src = _script()
    assert "import PILOT_THRESHOLDS" not in src
    assert "PILOT_THRESHOLDS[" not in src
    assert 'SPECS[os.environ["EXPERIMENT"]]' in src


def test_each_experiment_gets_its_own_run_directory():
    """Neither can resume from, or overwrite, the other's log and artifacts."""
    assert 'PILOT_DIR="$WORK/$EXPERIMENT"' in _script()
    assert 'PILOT_DIR="$WORK/pilot"' not in _script()


def test_the_run_log_is_seeded_from_the_selected_experiments_tree():
    assert 'cp "$REPO/$EXP_RUN_LOG_SRC"' in _script()


# ── the smoke artifact carries the identity it was run for ──
def test_the_smoke_artifact_is_stamped_with_the_selected_experiment(tmp_path):
    """The third place the identity leaked.

    `smoke.py` stamped `P.protocol_hash()` unconditionally, so an F3 host's
    smoke evidence would have carried the closed pilot's hash.
    """
    import agentseism.smoke as smoke_mod
    assert "P.protocol_hash()" not in \
        Path(smoke_mod.__file__).read_text()
    # The *invocation*, not the `from agentseism.smoke import SMOKE_TASK`
    # that appears earlier in the file.
    invocation = _script().split("-m agentseism.smoke", 1)[1][:200]
    assert '--experiment "$EXPERIMENT"' in invocation


@pytest.mark.parametrize("name,spec_of", [("pilot", lambda: P.SPEC),
                                          ("f3", lambda: F.SPEC)])
def test_smoke_stamps_whichever_registration_it_was_run_for(name, spec_of):
    import inspect

    import agentseism.smoke as smoke_mod
    src = inspect.getsource(smoke_mod.run_smoke)
    assert "sp = spec if spec is not None else P.SPEC" in src
    assert '"protocol_hash": sp.protocol_hash' in src
    assert '"order_hash": sp.order_hash' in src
    assert spec_of().name == name


# ── the audit: every experiment-dependent value is classified ──
def test_no_unclassified_pilot_literal_survives_on_the_budget_path():
    """Category 3 of the audit -- reachable only by the pilot -- has to be
    provably unreachable for F3, not merely unlikely.

    The values below are the ones that decide what F3 measures and where it
    writes. Any of them left pilot-specific is another paid discovery.
    """
    src = _script()
    for forbidden in ('cp "$REPO/data/runs/pilot/run.jsonl"',
                      # the *use* site, not the pilot branch's assignment
                      'BASELINE_USD="$BASELINE_USD" \\',
                      "from agentseism.pilot import PILOT_THRESHOLDS"):
        assert forbidden not in src, forbidden
    # and the pilot branch still assigns its own origin
    assert 'EXP_BASELINE_USD="$BASELINE_USD"' in src


def test_the_shared_values_are_shared_on_purpose():
    """Category 2 -- intentionally common to both registrations, and proved
    here so that sharing is a decision rather than an oversight."""
    assert F.RUN_TIMEOUT_SECONDS == P.RUN_TIMEOUT_SECONDS   # the run cap
    assert F.ARMS is P.ARMS                                 # the arms
    assert F.HINT_SHA256 is P.HINT_SHA256                   # the hint texts
    assert F.EXIT_STATUS_MAP is P.EXIT_STATUS_MAP           # exit mapping
    assert _const("DATASET") == "SWE-bench/SWE-bench_Verified"
    assert _const("EXPECTED_UNIVERSE") == "500"
    # The billing period and currency are the same page, not a shared default.
    assert _const("F3_BASELINE_PERIOD") == _const("BASELINE_PERIOD")
    assert _const("F3_BASELINE_CURRENCY") == _const("BASELINE_CURRENCY")


def test_the_draw_sizing_constants_are_unreachable_under_f3():
    """Category 3. `TASKS_WANTED=3` is the pilot's draw; F3 registers its task
    and returns from `draw_tasks` before any of those checks run."""
    src = _script()
    # keyed on having a registered task now, not on being F3
    f3_branch = src.split('if [ -n "$EXP_TASK" ]; then', 1)[1]
    early_return = f3_branch.split("return 0", 1)[0]
    assert "TASKS_WANTED" not in early_return
    assert 'printf \'%s\\n\' "$EXP_TASK" > "$drawn"' in early_return

"""surface-2's capability regression gate, against its frozen specification.

The numbers asserted here are the ones in
`analysis/CI_V1_REGRESSION_SEMANTICS.md` §4. If one of these tests has to
change, the design document changes with it, dated, before any run.
"""

from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest

from agentseism import capability as cap
from agentseism.capability import TaskCounts as T
from agentseism.cli import _task_counts
from agentseism.contract import ContractError, Measurement, decide
from agentseism.resolve import resolve_and_validate

ROOT = Path(__file__).resolve().parents[1]
SPEC = cap.DEFAULTS
FP = {"model_revision": "m"}


def surface(capability=True, **task_success):
    ts = {"gate": True, "regression_threshold": 0.10} | task_success
    if capability is not None:
        ts["capability_regression"] = capability
    return {"features": {"task_success": ts}}


def contract(**kw):
    return resolve_and_validate(surface(**kw))[0]


# ── the exact test, as tabulated in the design ──
@pytest.mark.parametrize("b,c,p", [
    (8, 0, 0.0001), (8, 1, 0.0007), (8, 2, 0.0035), (8, 3, 0.0128),
    (8, 4, 0.0385), (8, 5, 0.1000),
    (7, 0, 0.0007), (7, 1, 0.0051), (7, 2, 0.0203), (7, 3, 0.0594),
    (7, 4, 0.1410), (7, 5, 0.2846),
])
def test_fisher_matches_the_design_table(b, c, p):
    assert round(cap.fisher_one_sided(b, 8, c, 8), 4) == p


def test_fisher_is_one_sided_in_the_regression_direction():
    """An improvement is never evidence of a regression."""
    assert cap.fisher_one_sided(2, 8, 8, 8) == 1.0
    assert cap.fisher_one_sided(8, 8, 8, 8) == 1.0


# ── decision boundaries for every K the confirmatory study can produce ──
BOUNDARY = {1: (4, 2), 2: (3, 2), 3: (3, 1), 4: (2, 1), 5: (2, 1),
            6: (2, 1), 7: (2, 1)}


@pytest.mark.parametrize("k", sorted(BOUNDARY))
def test_the_boundary_for_each_k_is_the_designed_one(k):
    from_8, from_7 = BOUNDARY[k]
    for base, top in ((8, from_8), (7, from_7)):
        others = {f"o{i}": T(8, 8, 8, 8) for i in range(k - 1)}
        fired = [c for c in range(9)
                 if cap.evaluate(SPEC, others | {"t": T(base, 8, c, 8)})["fired"]]
        assert max(fired) == top, (k, base, fired)


def test_at_seven_eligible_tasks_the_smallest_firing_drop_is_three_quarters():
    """The practical threshold says 0.50; the exact test binds first. This is
    the claim the report is allowed to make, and no more."""
    others = {f"o{i}": T(8, 8, 8, 8) for i in range(6)}
    drops = [(8 - c) / 8 for c in range(9)
             if cap.evaluate(SPEC, others | {"t": T(8, 8, c, 8)})["fired"]]
    assert min(drops) == 0.75


# ── eligibility, warnings, and what is not monitored ──
def test_an_unreliable_baseline_is_not_monitored_but_still_counts_in_k():
    """Revision 3: K is the declared suite. An ineligible task is not tested,
    yet it stays in the multiplicity family, which was fixed before any outcome
    was seen."""
    r = cap.evaluate(SPEC, {"a": T(8, 8, 0, 8), "b": T(6, 8, 0, 8)})
    assert r["k"] == 2 and r["alpha_per_task"] == 0.025
    assert r["fired"] == ["a"] and r["eligible"] == ["a"]
    assert r["not_monitored"] == ["b"]
    assert "baseline below" in r["detail"]["b"]["not_monitored"]


def test_a_flaky_suite_does_not_loosen_the_gate():
    """The revision-2 defect. Seven declared tasks, only one reliable: under
    eligible-K that task was tested at alpha/1, and 8/8 -> 3/8 fired. Under
    suite-K it is tested at alpha/7 and does not."""
    flaky = {f"f{i}": T(5, 8, 5, 8) for i in range(6)}
    r = cap.evaluate(SPEC, flaky | {"t": T(8, 8, 3, 8)})
    assert r["k"] == 7 and r["eligible"] == ["t"]
    assert r["fired"] == [] and r["detail"]["t"]["decision"] == "WARNING"
    assert cap.fisher_one_sided(8, 8, 3, 8) <= 0.05          # would have fired
    assert cap.fisher_one_sided(8, 8, 3, 8) > 0.05 / 7       # does not now


def test_a_task_with_any_invalid_run_is_excluded_not_scored():
    r = cap.evaluate(SPEC, {"a": T(8, 8, 0, 7, invalid=1)})
    assert r["fired"] == [] and r["not_monitored"] == ["a"]


def test_fewer_than_the_minimum_trials_is_not_monitored():
    r = cap.evaluate(SPEC, {"a": T(5, 5, 0, 5)})
    assert r["k"] == 1 and r["eligible"] == [] and r["fired"] == []
    assert r["not_monitored"] == ["a"]


@pytest.mark.parametrize("cand,decision", [(8, "PASS"), (6, "PASS"),
                                           (5, "WARNING"), (4, "WARNING")])
def test_the_warning_starts_at_three_eighths(cand, decision):
    others = {f"o{i}": T(8, 8, 8, 8) for i in range(6)}
    r = cap.evaluate(SPEC, others | {"t": T(8, 8, cand, 8)})
    assert r["detail"]["t"]["decision"] == decision


# ── contract: surface-1 is untouched, surface-2 is explicit ──
def test_a_contract_without_the_block_resolves_exactly_as_before():
    without = contract(capability=None)
    assert "capability_regression" not in without.features["task_success"]
    assert contract(capability=False).content_sha256 == without.content_sha256


def test_the_frozen_stage_a_contract_still_hashes_the_same():
    """The CI v0 evidence is tied to `6e9aa552c90a2cda`. Adding surface-2 must
    not move it. Local-only: the recorded run is not versioned."""
    bl = ROOT / ".runs/stageA/.agentseism/baselines/main.json"
    if not bl.exists():
        pytest.skip("Stage A run directory not present")
    rec = json.loads(bl.read_text())
    c, _, _ = resolve_and_validate(rec["surface_contract"])
    assert c.content_sha256 == rec["contract_sha256"] == "6e9aa552c90a2cda"


def test_true_takes_the_frozen_defaults_and_moves_the_hash():
    c = contract()
    assert c.features["task_success"]["capability_regression"] == SPEC
    assert c.content_sha256 != contract(capability=None).content_sha256


def test_a_mapping_overrides_named_fields_only():
    c = contract(capability={"alpha": 0.01})
    got = c.features["task_success"]["capability_regression"]
    assert got["alpha"] == 0.01 and got["warn_threshold"] == 0.375


@pytest.mark.parametrize("bad,msg", [
    ({"warn_threshold": 0.5}, "not a warning"),
    ({"test": "chi_square"}, "test must be one of"),
    ({"multiplicity": "none"}, "multiplicity must be one of"),
    ({"alpha": 1.5}, "alpha must be in"),
])
def test_an_invalid_block_is_refused(bad, msg):
    with pytest.raises(ContractError, match=msg):
        contract(capability=bad)


def test_the_block_is_refused_on_a_warning_gate():
    with pytest.raises(ContractError, match="requires gate true"):
        contract(gate="warning")


# ── the verdict ──
def stage_b_like():
    """Stage B's pattern at 8 trials: two tasks untouched, one partial, two
    collapsed; one collapsed task was never reliable."""
    return {"astropy": T(8, 8, 8, 8), "flask": T(8, 8, 8, 8),
            "matplotlib": T(8, 8, 5, 8), "django": T(8, 8, 0, 8),
            "seaborn": T(5, 8, 0, 8)}


def m(effect, lo, hi, per_task, invalid=0):
    return Measurement(effect, lo, hi,
                       {"scenarios": 5, "trials_per_condition": 8},
                       invalid, per_task)


def test_a_concentrated_collapse_is_a_regression_the_population_gate_misses():
    v = decide(contract(), FP, FP,
               {"task_success": m(-0.40, -0.72, -0.08, stage_b_like())})
    assert v["verdict"] == "REGRESSION"
    c = v["capability"]["task_success"]
    assert c["fired"] == ["django"] and c["warnings"] == ["matplotlib"]
    assert c["not_monitored"] == ["seaborn"] and c["k"] == 5


def test_the_same_numbers_without_the_block_still_pass():
    v = decide(contract(capability=None), FP, FP,
               {"task_success": m(-0.40, -0.72, -0.08, stage_b_like())})
    assert v["verdict"] == "PASS" and "capability" not in v


def test_a_null_candidate_passes_and_still_reports_what_is_unmonitored():
    tasks = {"a": T(8, 8, 8, 8), "b": T(8, 8, 7, 8), "c": T(4, 8, 3, 8),
             "d": T(7, 8, 7, 8), "e": T(8, 8, 8, 8)}
    v = decide(contract(), FP, FP, {"task_success": m(-0.05, -0.12, 0.0, tasks)})
    assert v["verdict"] == "PASS"
    assert v["capability"]["task_success"]["not_monitored"] == ["c"]


def test_a_fired_task_stands_when_invalid_runs_elsewhere_stop_the_population_gate():
    tasks = stage_b_like() | {"flask": T(8, 8, 7, 7, invalid=1)}
    v = decide(contract(), FP, FP,
               {"task_success": m(-0.40, -0.72, -0.08, tasks, invalid=1)})
    assert v["verdict"] == "REGRESSION"
    assert "flask" in v["capability"]["task_success"]["not_monitored"]


def test_invalid_runs_still_stop_when_nothing_fired():
    tasks = {"a": T(8, 8, 8, 7, invalid=1), **{f"o{i}": T(8, 8, 8, 8)
                                               for i in range(4)}}
    v = decide(contract(), FP, FP, {"task_success": m(0.0, 0.0, 0.0, tasks, 1)})
    assert v["verdict"] == "INSUFFICIENT_EVIDENCE" and v["invalid_stop"]


def test_the_population_gate_alone_still_fires():
    tasks = {f"t{i}": T(8, 8, 6, 8) for i in range(5)}
    v = decide(contract(), FP, FP, {"task_success": m(-0.25, -0.25, -0.25, tasks)})
    assert v["verdict"] == "REGRESSION"
    assert v["capability"]["task_success"]["fired"] == []


def test_a_declared_gate_without_counts_is_a_programming_error():
    with pytest.raises(ValueError, match="per_task"):
        decide(contract(), FP, FP, {"task_success": m(0.0, 0.0, 0.0, None)})


# ── counting from real result rows ──
def test_task_counts_separate_arms_and_count_invalid_across_both():
    def row(task, success=None, invalid=False):
        return {"task": task, "invalid": invalid,
                "outcome": {} if success is None else {"success": success}}
    base = [row("a", 1), row("a", 1), row("a", 0), row("b", 1)]
    cand = [row("a", 0), row("a", 1), row("b", invalid=True), row("b", 1)]
    got = _task_counts(base, cand, "success")
    assert got["a"] == T(2, 3, 1, 2, 0)
    assert got["b"] == T(1, 1, 1, 1, 1)


def test_a_declared_task_with_no_rows_still_counts_toward_k():
    """K is the suite that was declared, not the tasks that happened to
    produce results. A batch stopped early must not shrink the family."""
    got = _task_counts([], [], "success", ["a", "b", "c"])
    assert set(got) == {"a", "b", "c"}
    r = cap.evaluate(SPEC, got)
    assert r["k"] == 3 and r["not_monitored"] == ["a", "b", "c"]

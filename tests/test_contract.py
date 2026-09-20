"""Feature contract: schema, validator and the deterministic verdict engine.

No agent, no model, no Docker, no network. Every verdict here is computed from
supplied measurements, which is the point: the decision semantics are testable
without spending anything.
"""
from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest
import yaml

from experiments.coding.contract import (
    Contract, ContractError, Measurement, canonical_hash, decide, load, validate,
)

DEFAULT = Path("contracts/default.yaml")
PILOT = Path("contracts/pilot.yaml")

FP = {"model_revision": "e89b16eb", "serving_runtime": "vllm-0.28.0+cu130",
      "dependency_lock": "abc123", "prompt_version": "mode-b-0",
      "scaffold_version": "mini-2.4.6"}


def raw():
    return yaml.safe_load(DEFAULT.read_text())


def ok(**over):
    """Sufficient evidence, no effect."""
    base = dict(effect=0.0, ci_low=-0.02, ci_high=0.02,
                evidence={"scenarios": 8, "trials_per_condition": 5,
                          "eligible_scenarios": 6})
    base.update(over)
    return Measurement(**base)


def full(c=None):
    c = c or load(DEFAULT)
    return {n: ok() for n in c.features}


# ── 1. fingerprint mismatch: zero trials, zero RCA ──
@pytest.mark.parametrize("field", list(FP))
def test_mismatch_gives_incomparable_with_no_trials_and_no_rca(field):
    c = load(DEFAULT)
    v = decide(c, FP, FP | {field: "different"})
    assert v["verdict"] == "INCOMPARABLE"
    assert v["trials_run"] == 0 and v["rca"] is False
    assert v["mismatched"] == [field]


def test_comparability_is_decided_before_measurements_exist():
    """It must not need them — that is what 'before any trial' means."""
    c = load(DEFAULT)
    v = decide(c, FP, FP | {"model_revision": "other"}, measurements=None)
    assert v["verdict"] == "INCOMPARABLE"


# ── 2. large trace divergence, outcomes intact → not a regression ──
def test_huge_trace_divergence_with_intact_outcomes_is_not_a_regression():
    c = load(DEFAULT)
    v = decide(c, FP, FP, full(c),
               diagnostic_changed=["trace_divergence", "tool_error_profile"])
    assert v["verdict"] == "PASS_WITH_CHANGE"
    assert v["rca"] is False
    assert v["diagnostic_changed"] == ["tool_error_profile", "trace_divergence"]


def test_diagnostics_cannot_be_given_verdict_authority():
    r = raw()
    r["diagnostics"]["trace_divergence"]["verdict_authority"] = "true"
    with pytest.raises(ContractError, match="verdict_authority"):
        validate(r)


def test_a_trace_feature_may_not_gate():
    r = raw()
    r["features"]["trace_len"] = dict(r["features"]["task_success"],
                                      role="reliability", gate=True)
    with pytest.raises(ContractError, match="reserved for role 'outcome'"):
        validate(r)


# ── 3. a warning feature cannot raise REGRESSION ──
def test_a_warning_feature_that_regresses_does_not_gate():
    c = load(DEFAULT)
    m = full(c) | {"cost_per_success": ok(effect=0.80, ci_low=0.50, ci_high=1.1)}
    v = decide(c, FP, FP, m)
    assert v["verdict"] == "PASS"
    assert v["warnings"] == ["cost_per_success"] and v["rca"] is False


# ── 4. a gating outcome past its threshold raises REGRESSION and RCA ──
def test_gating_outcome_past_threshold_raises_regression_and_rca():
    c = load(DEFAULT)
    m = full(c) | {"task_success": ok(effect=-0.28, ci_low=-0.40, ci_high=-0.16)}
    v = decide(c, FP, FP, m)
    assert v["verdict"] == "REGRESSION"
    assert v["regressed"] == ["task_success"] and v["rca"] is True


def test_an_effect_below_the_practical_threshold_is_not_a_regression():
    """A real difference smaller than the declared threshold passes. That is
    the reason for declaring a threshold at all."""
    c = load(DEFAULT)
    m = full(c) | {"task_success": ok(effect=-0.06, ci_low=-0.09, ci_high=-0.03)}
    assert decide(c, FP, FP, m)["verdict"] == "PASS"


def test_an_interval_touching_the_threshold_is_not_a_regression():
    c = load(DEFAULT)
    m = full(c) | {"task_success": ok(effect=-0.14, ci_low=-0.30, ci_high=-0.02)}
    assert decide(c, FP, FP, m)["verdict"] == "PASS"


def test_aggregation_all_requires_every_gate(tmp_path):
    r = raw(); r["decision"]["aggregation"] = "all"
    c = validate(r)
    m = full(c) | {"task_success": ok(effect=-0.28, ci_low=-0.40, ci_high=-0.16)}
    assert decide(c, FP, FP, m)["verdict"] == "PASS"
    m["recovery_success"] = ok(effect=-0.40, ci_low=-0.55, ci_high=-0.25)
    assert decide(c, FP, FP, m)["verdict"] == "REGRESSION"


# ── 5. thin evidence → INSUFFICIENT_EVIDENCE ──
def test_thin_evidence_is_insufficient_not_pass():
    c = load(DEFAULT)
    m = full(c) | {"task_success": ok(evidence={"scenarios": 2,
                                                "trials_per_condition": 3})}
    v = decide(c, FP, FP, m)
    assert v["verdict"] == "INSUFFICIENT_EVIDENCE"
    assert v["insufficient"] == ["task_success"] and v["rca"] is False


def test_thin_evidence_on_a_large_apparent_effect_is_still_insufficient():
    """An effect that looks huge on two scenarios is still unmeasured."""
    c = load(DEFAULT)
    m = full(c) | {"task_success": ok(effect=-0.50, ci_low=-0.9, ci_high=-0.3,
                                      evidence={"scenarios": 1,
                                                "trials_per_condition": 1})}
    assert decide(c, FP, FP, m)["verdict"] == "INSUFFICIENT_EVIDENCE"


def test_invalid_runs_under_stop_policy_do_not_become_a_pass():
    c = load(DEFAULT)
    m = full(c) | {"task_success": ok(invalid=2)}
    v = decide(c, FP, FP, m)
    assert v["verdict"] == "INSUFFICIENT_EVIDENCE"
    assert v["invalid_stop"] == ["task_success"]


# ── 6. RCA never reaches back into the verdict ──
def test_insufficient_is_not_escalated_by_warnings():
    c = load(DEFAULT)
    m = full(c) | {"task_success": ok(evidence={"scenarios": 1}),
                   "cost_per_success": ok(effect=0.90, ci_low=0.6, ci_high=1.2)}
    v = decide(c, FP, FP, m)
    assert v["verdict"] == "INSUFFICIENT_EVIDENCE"
    assert v["warnings"] == ["cost_per_success"]


def test_rca_is_only_reachable_from_regression():
    """The engine emits rca=True for exactly one verdict, and takes no RCA
    input at all — so a finding cannot flow backwards into the decision."""
    import inspect
    assert "rca" not in inspect.signature(decide).parameters
    c = load(DEFAULT)
    cases = [
        (FP | {"model_revision": "x"}, full(c), None),
        (FP, full(c), ["trace_divergence"]),
        (FP, full(c) | {"task_success": ok(evidence={"scenarios": 1})}, None),
        (FP, full(c), None),
    ]
    for cand, m, diag in cases:
        v = decide(c, FP, cand, m, diag)
        assert v["rca"] is False, v["verdict"]
    m = full(c) | {"task_success": ok(effect=-0.3, ci_low=-0.4, ci_high=-0.2)}
    assert decide(c, FP, FP, m)["rca"] is True


def test_contract_declares_rca_runs_only_on_regression():
    r = raw(); r["rca"]["run_only_when"] = "PASS"
    with pytest.raises(ContractError, match="run_only_when"):
        validate(r)


# ── 7. fail closed on unknown features, missing thresholds, bad enums ──
def test_an_unknown_measured_feature_fails_closed():
    c = load(DEFAULT)
    with pytest.raises(ContractError, match="unknown feature"):
        decide(c, FP, FP, full(c) | {"invented_metric": ok()})


@pytest.mark.parametrize("missing", [
    "evaluator", "independent_unit", "effect", "regression_direction",
    "practical_threshold", "uncertainty", "minimum_evidence", "invalid_policy",
])
def test_a_gate_missing_any_required_field_fails_closed(missing):
    r = raw(); del r["features"]["task_success"][missing]
    with pytest.raises(ContractError, match=missing):
        validate(r)


@pytest.mark.parametrize("field,bad", [
    ("regression_direction", "sideways"), ("effect", "vibes"),
    ("uncertainty", "eyeball"), ("invalid_policy", "ignore"), ("role", "misc"),
])
def test_illegal_enum_values_fail_closed(field, bad):
    r = raw(); r["features"]["task_success"][field] = bad
    with pytest.raises(ContractError, match=field):
        validate(r)


def test_a_contract_with_no_gate_fails_closed():
    r = raw()
    for f in r["features"].values():
        f["gate"] = "warning"
    with pytest.raises(ContractError, match="nothing could ever be a REGRESSION"):
        validate(r)


def test_empty_require_same_fails_closed():
    r = raw(); r["comparability"]["require_same"] = []
    with pytest.raises(ContractError, match="ever be INCOMPARABLE"):
        validate(r)


def test_feasibility_mode_must_be_descriptive_only():
    r = raw(); r["study_mode"] = "feasibility"
    with pytest.raises(ContractError, match="descriptive_only"):
        validate(r)


def test_the_pilot_contract_cannot_emit_a_release_verdict():
    c = load(PILOT)
    assert c.descriptive_only is True
    v = decide(c, FP, FP, {"task_success": ok(effect=-0.3, ci_low=-0.4,
                                              ci_high=-0.2,
                                              evidence={"scenarios": 3,
                                                        "trials_per_condition": 3})})
    assert v["verdict"] == "REGRESSION"
    assert v["verdict_authority"] == "descriptive_only"
    assert v["study_mode"] == "feasibility"


# ── 8/9. canonical hash: stable under reordering, sensitive to content ──
def test_field_order_does_not_change_the_hash():
    r = raw()
    shuffled = json.loads(json.dumps(r))
    shuffled["features"] = dict(reversed(list(shuffled["features"].items())))
    shuffled = {k: shuffled[k] for k in reversed(list(shuffled))}
    assert canonical_hash(shuffled) == canonical_hash(r)
    assert validate(shuffled).content_sha256 == validate(r).content_sha256


@pytest.mark.parametrize("mutate", [
    lambda r: r["features"]["task_success"].update(practical_threshold=0.11),
    lambda r: r["features"]["task_success"].update(gate="warning"),
    lambda r: r["comparability"]["require_same"].append("gpu_model"),
    lambda r: r.update(contract_version="default-2"),
    lambda r: r["decision"].update(aggregation="all"),
])
def test_any_content_change_changes_the_hash(mutate):
    r = raw(); before = canonical_hash(r)
    r2 = copy.deepcopy(r); mutate(r2)
    assert canonical_hash(r2) != before


# ── 10. the report carries the contract the verdict came from ──
@pytest.mark.parametrize("scenario", ["incomparable", "regression",
                                      "insufficient", "pass_with_change", "pass"])
def test_every_verdict_carries_the_contract_hash_and_version(scenario):
    c = load(DEFAULT)
    args = {
        "incomparable": (FP | {"model_revision": "x"}, full(c), None),
        "regression": (FP, full(c) | {"task_success": ok(effect=-0.3,
                                                         ci_low=-0.4,
                                                         ci_high=-0.2)}, None),
        "insufficient": (FP, full(c) | {"task_success":
                                        ok(evidence={"scenarios": 1})}, None),
        "pass_with_change": (FP, full(c), ["trace_divergence"]),
        "pass": (FP, full(c), None),
    }[scenario]
    v = decide(c, FP, *args)
    assert v["contract_sha256"] == c.content_sha256
    assert v["contract_version"] == "default-1"
    assert v["protocol_version"] == 1
    assert v["contract_path"] == str(DEFAULT)


def test_the_shipped_contracts_validate():
    for p in (DEFAULT, PILOT):
        assert isinstance(load(p), Contract)


# ── the PR report renderer ──
from experiments.coding.report import Row, render  # noqa: E402


def _v(verdict_name, **over):
    c = load(DEFAULT)
    if verdict_name == "INCOMPARABLE":
        return decide(c, FP, FP | {"model_revision": "x"})
    m = full(c)
    if verdict_name == "REGRESSION":
        m["task_success"] = ok(effect=-0.31, ci_low=-0.42, ci_high=-0.20)
    if verdict_name == "INSUFFICIENT_EVIDENCE":
        m["task_success"] = ok(evidence={"scenarios": 1})
    diag = ["trace_divergence"] if verdict_name == "PASS_WITH_CHANGE" else None
    return decide(c, FP, FP, m, diag)


@pytest.mark.parametrize("name", ["REGRESSION", "INSUFFICIENT_EVIDENCE",
                                  "INCOMPARABLE", "PASS_WITH_CHANGE", "PASS"])
def test_every_verdict_renders_with_its_contract_footer(name):
    md = render(_v(name))
    assert md.startswith("## AgentSeism:")
    assert "1e3047d6fefbdae6" in md and "default-1" in md


def test_insufficient_is_never_rendered_as_a_pass():
    md = render(_v("INSUFFICIENT_EVIDENCE"))
    assert "not a pass" in md
    assert "do not read this as a pass" in md


def test_incomparable_says_zero_trials_were_spent():
    md = render(_v("INCOMPARABLE"))
    assert "Trials run: **0**" in md and "No regression was computed" in md


def test_rca_cannot_be_rendered_under_a_non_regression_verdict():
    """A reader would take it as a reason the merge is risky."""
    for name in ("PASS", "PASS_WITH_CHANGE", "INSUFFICIENT_EVIDENCE"):
        with pytest.raises(ValueError, match="RCA runs only on REGRESSION"):
            render(_v(name), rca=["first separation after tool handling"])


def test_rca_renders_under_regression_and_says_why_it_ran():
    md = render(_v("REGRESSION"), rca=["first separation after tool handling"],
                unaffected="runs without malformed calls show no regression")
    assert "run because the outcome regressed, not because the trace moved" in md
    assert "Unaffected:" in md


def test_a_descriptive_only_verdict_is_labelled_in_the_report():
    c = load(PILOT)
    v = decide(c, FP, FP, {"task_success": ok(effect=-0.3, ci_low=-0.4,
                                              ci_high=-0.2,
                                              evidence={"scenarios": 3,
                                                        "trials_per_condition": 3})})
    assert "descriptive only" in render(v)
    assert "not a release decision" in render(v)


def test_warnings_are_rendered_as_non_blocking():
    c = load(DEFAULT)
    m = full(c) | {"cost_per_success": ok(effect=0.9, ci_low=0.6, ci_high=1.2)}
    md = render(decide(c, FP, FP, m))
    assert "do not block a merge" in md


def test_the_demo_reports_are_reproducible_from_frozen_data():
    """The two shipped demos regenerate byte-identically, so the README cannot
    drift from the artifacts it claims to be computed from."""
    import subprocess
    before = {p: p.read_text() for p in
              [Path("docs/demo/pr-report-pass-with-change.md"),
               Path("docs/demo/pr-report-incomparable.md")]}
    r = subprocess.run([".venv-eval/bin/python",
                        "experiments/coding/make_demo_reports.py"],
                       capture_output=True, text=True,
                       env={"PYTHONPATH": ".", "PATH": "/usr/bin:/bin"})
    assert r.returncode == 0, r.stderr
    for p, text in before.items():
        assert p.read_text() == text

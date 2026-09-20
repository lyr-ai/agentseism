"""Surface contract → effective contract. No runner, no model, no container."""
from __future__ import annotations

import copy

import pytest

from experiments.coding.contract import ContractError, Measurement, decide
from experiments.coding.resolve import (
    DEFAULTS_VERSION, FEATURE_DEFAULTS, RESOLVED_SCHEMA_VERSION,
    effective_hash, provenance, resolve, resolve_and_validate,
)

FP = {"model_revision": "r", "serving_runtime": "s", "dependency_lock": "d",
      "prompt_version": "p", "scaffold_version": "c"}

# The README quick-start, verbatim.
QUICKSTART = {
    "runner": {"command": "python run_agent.py --task {task_file}"},
    "features": {
        "task_success": {"gate": True, "regression_threshold": 0.10},
        "recovery_success": {"gate": True, "regression_threshold": 0.15},
        "cost_per_success": {"gate": "warning", "regression_threshold": 0.25},
    },
}


# ── the product test: the minimal contract works, with no statistics named ──
def test_the_quickstart_contract_resolves_and_is_complete():
    c, surface, src = resolve_and_validate(copy.deepcopy(QUICKSTART))
    f = c.raw["features"]["task_success"]
    for field in ("role", "evaluator", "independent_unit", "effect",
                  "regression_direction", "practical_threshold", "uncertainty",
                  "minimum_evidence", "invalid_policy", "gate"):
        assert f.get(field) not in (None, ""), field
    assert list(c.gating) == ["task_success", "recovery_success"]


def test_the_user_names_no_statistical_method():
    """Everything statistical is inherited; only the threshold is authored."""
    _, _, src = resolve_and_validate(copy.deepcopy(QUICKSTART))
    for feat in QUICKSTART["features"]:
        for stat in ("effect", "uncertainty", "independent_unit",
                     "regression_direction", "invalid_policy", "role"):
            assert src[f"{feat}.{stat}"] == "default"
        assert src[f"{feat}.practical_threshold"] == "author"


def test_a_resolved_quickstart_can_produce_every_verdict():
    c, _, _ = resolve_and_validate(copy.deepcopy(QUICKSTART))
    enough = {"scenarios": 9, "trials_per_condition": 5, "eligible_scenarios": 6}
    m = {n: Measurement(0.0, -0.01, 0.01, enough) for n in c.features}
    assert decide(c, FP, FP, m)["verdict"] == "PASS"
    assert decide(c, FP, FP | {"model_revision": "x"})["verdict"] == "INCOMPARABLE"
    m2 = m | {"task_success": Measurement(-0.3, -0.4, -0.2, enough)}
    assert decide(c, FP, FP, m2)["verdict"] == "REGRESSION"
    m3 = m | {"task_success": Measurement(0.0, -0.01, 0.01, {"scenarios": 1})}
    assert decide(c, FP, FP, m3)["verdict"] == "INSUFFICIENT_EVIDENCE"
    assert decide(c, FP, FP, m, ["trace_divergence"])["verdict"] == "PASS_WITH_CHANGE"


# ── defaults are versioned and enter the hash ──
def test_the_hash_covers_the_defaults_and_schema_versions():
    eff, _ = resolve(copy.deepcopy(QUICKSTART))
    before = effective_hash(eff)
    assert effective_hash(eff | {"defaults_version": "9.9.9"}) != before
    assert effective_hash(eff | {"resolved_schema_version": 99}) != before


def test_the_effective_contract_records_both_versions():
    eff, _ = resolve(copy.deepcopy(QUICKSTART))
    assert eff["defaults_version"] == DEFAULTS_VERSION
    assert eff["resolved_schema_version"] == RESOLVED_SCHEMA_VERSION


def test_the_hash_is_over_the_effective_not_the_surface():
    """Two surfaces that resolve identically hash identically; a surface change
    that resolves differently does not."""
    a = copy.deepcopy(QUICKSTART)
    b = copy.deepcopy(QUICKSTART)
    b["features"]["task_success"]["effect"] = "risk_difference"   # same as default
    assert effective_hash(resolve(a)[0]) == effective_hash(resolve(b)[0])
    b["features"]["task_success"]["effect"] = "risk_ratio"
    assert effective_hash(resolve(b)[0]) != effective_hash(resolve(a)[0])


def test_field_order_does_not_change_the_effective_hash():
    a = copy.deepcopy(QUICKSTART)
    b = copy.deepcopy(QUICKSTART)
    b["features"] = dict(reversed(list(b["features"].items())))
    b = {k: b[k] for k in reversed(list(b))}
    assert effective_hash(resolve(a)[0]) == effective_hash(resolve(b)[0])


# ── both contracts, and the sources, reach the report ──
def test_provenance_carries_surface_effective_and_sources():
    c, surface, src = resolve_and_validate(copy.deepcopy(QUICKSTART))
    p = provenance(c, surface, src)
    assert p["surface_contract"] == QUICKSTART
    assert p["effective_contract"] == c.raw
    assert p["field_sources"]["task_success.uncertainty"] == "default"
    assert p["defaults_version"] == DEFAULTS_VERSION


# ── author values win; illegal combinations fail closed ──
def test_an_author_value_overrides_its_default():
    s = copy.deepcopy(QUICKSTART)
    s["features"]["task_success"]["uncertainty"] = "wilson"
    c, _, src = resolve_and_validate(s)
    assert c.raw["features"]["task_success"]["uncertainty"] == "wilson"
    assert src["task_success.uncertainty"] == "author"


@pytest.mark.parametrize("field,bad", [
    ("uncertainty", "eyeball"), ("effect", "vibes"),
    ("regression_direction", "sideways"), ("invalid_policy", "ignore"),
])
def test_an_illegal_override_fails_closed(field, bad):
    s = copy.deepcopy(QUICKSTART)
    s["features"]["task_success"][field] = bad
    with pytest.raises(ContractError, match=field):
        resolve_and_validate(s)


def test_a_gate_without_a_threshold_fails_closed():
    s = copy.deepcopy(QUICKSTART)
    del s["features"]["task_success"]["regression_threshold"]
    with pytest.raises(ContractError, match="regression_threshold is required"):
        resolve_and_validate(s)


# ── unknown names are never silently defaulted ──
def test_an_unknown_feature_fails_closed():
    s = copy.deepcopy(QUICKSTART)
    s["features"]["vibe_score"] = {"gate": True, "regression_threshold": 0.1}
    with pytest.raises(ContractError, match="not a known feature"):
        resolve(s)


def test_an_unknown_evaluator_fails_closed():
    s = copy.deepcopy(QUICKSTART)
    s["features"]["task_success"]["evaluator"] = "ask_an_llm"
    with pytest.raises(ContractError, match="is unknown"):
        resolve(s)


def test_an_explicit_command_evaluator_is_accepted():
    s = copy.deepcopy(QUICKSTART)
    s["features"]["task_success"]["evaluator"] = {
        "command": "python check_result.py {artifact_dir}"}
    c, _, _ = resolve_and_validate(s)
    assert c.raw["features"]["task_success"]["evaluator"]["command"]


def test_a_command_evaluator_without_a_command_fails_closed():
    s = copy.deepcopy(QUICKSTART)
    s["features"]["task_success"]["evaluator"] = {"script": "x.py"}
    with pytest.raises(ContractError, match="needs 'command'"):
        resolve(s)


# ── feasibility can never be release ──
def test_feasibility_forces_descriptive_only():
    s = copy.deepcopy(QUICKSTART) | {"study_mode": "feasibility"}
    c, _, src = resolve_and_validate(s)
    assert c.raw["verdict_authority"] == "descriptive_only"
    assert src["verdict_authority"] == "forced_by_study_mode"


def test_feasibility_cannot_declare_release():
    s = copy.deepcopy(QUICKSTART) | {"study_mode": "feasibility",
                                     "verdict_authority": "release"}
    with pytest.raises(ContractError, match="may not produce a release"):
        resolve(s)


def test_release_without_minimum_evidence_is_refused():
    s = copy.deepcopy(QUICKSTART)
    s["features"]["task_success"]["minimum_evidence"] = {}
    with pytest.raises(ContractError, match="needs a minimum_evidence"):
        resolve(s)


# ── comparability cannot be reached from a feature ──
def test_comparability_is_defaulted_and_precedes_trials():
    c, _, _ = resolve_and_validate(copy.deepcopy(QUICKSTART))
    assert c.require_same and "serving_runtime" in c.require_same
    v = decide(c, FP, FP | {"serving_runtime": "other"})
    assert v["verdict"] == "INCOMPARABLE" and v["trials_run"] == 0


def test_no_feature_field_can_switch_comparability_off():
    s = copy.deepcopy(QUICKSTART)
    s["features"]["task_success"]["comparability"] = {"require_same": []}
    s["features"]["task_success"]["skip_comparability"] = True
    c, _, _ = resolve_and_validate(s)
    assert c.require_same == list(
        __import__("experiments.coding.resolve", fromlist=["x"]).COMPARABILITY_DEFAULT)
    assert decide(c, FP, FP | {"model_revision": "x"})["verdict"] == "INCOMPARABLE"


# ── diagnostics never gain authority ──
def test_diagnostics_are_always_forced_to_none():
    s = copy.deepcopy(QUICKSTART)
    s["diagnostics"] = {"trace_divergence": {"verdict_authority": "true"},
                        "tool_error_profile": {"verdict_authority": "warning"}}
    c, _, src = resolve_and_validate(s)
    for d in c.diagnostics.values():
        assert d["verdict_authority"] == "none"
    assert src["diagnostics.trace_divergence.verdict_authority"] == "forced"


def test_a_diagnostic_cannot_be_promoted_into_a_gating_feature():
    s = copy.deepcopy(QUICKSTART)
    s["features"]["trace_divergence"] = {"gate": True, "regression_threshold": 0.1}
    with pytest.raises(ContractError, match="not a known feature"):
        resolve(s)


# ── every known default is itself valid ──
@pytest.mark.parametrize("name", sorted(FEATURE_DEFAULTS))
def test_every_shipped_default_resolves_and_validates(name):
    gate = "true" if FEATURE_DEFAULTS[name]["role"] == "outcome" else "warning"
    s = {"features": {name: {"gate": gate, "regression_threshold": 0.1}}}
    if gate != "true":
        s["features"]["task_success"] = {"gate": True, "regression_threshold": 0.1}
    c, _, _ = resolve_and_validate(s)
    assert name in c.features

"""Surface contract → effective contract.

A developer writes three lines per feature. The tool expands them, against
**versioned** defaults, into the complete contract that is validated, hashed
and printed. That keeps two properties that look incompatible:

* nobody has to understand risk difference or paired bootstrap to run a check;
* no metric is decided after the analysis is seen.

What makes the second true is the **ordering**: defaults are fixed in the tool,
in a released version, before anyone sees a number. A default chosen in advance
is not a metric chosen afterwards.

Four rules keep that honest rather than merely stated.

1. `DEFAULTS_VERSION` and `RESOLVED_SCHEMA_VERSION` are inputs to the hash, so
   upgrading the tool cannot make a differently-resolved contract look like the
   same one.
2. The hash is over the **effective** contract, never the surface.
3. Both contracts go into the artifact and the report, with a per-field record
   of what the author wrote and what was inherited.
4. An unknown feature or evaluator **fails closed**. Silently giving a generic
   default to a name we do not recognise would invent a measurement.

No runner, no adapter, no model, no container.
"""

from __future__ import annotations

import copy
import hashlib
import json
from typing import Any

from agentseism.contract import (
    PROTOCOL_VERSION, Contract, ContractError, canonical_hash, validate,
)

DEFAULTS_VERSION = "1.0.0"
RESOLVED_SCHEMA_VERSION = 1

KNOWN_EVALUATORS = {
    "swebench_resolved", "deterministic_recovery_check", "tokens_per_resolved",
    "steps_per_resolved", "wallclock_per_resolved", "tool_call_outcome",
}
"""A named evaluator we ship. Anything else must be an explicit command:
`{command: "python check_result.py {artifact_dir}"}`."""

FEATURE_DEFAULTS: dict[str, dict[str, Any]] = {
    "task_success": {
        "role": "outcome", "evaluator": "swebench_resolved",
        "independent_unit": "scenario", "effect": "risk_difference",
        "regression_direction": "decrease", "uncertainty": "paired_bootstrap",
        "minimum_evidence": {"scenarios": 5, "trials_per_condition": 3},
        "invalid_policy": "stop",
    },
    "recovery_success": {
        "role": "outcome", "evaluator": "deterministic_recovery_check",
        "condition": "predefined_recovery_event",
        "independent_unit": "scenario", "effect": "risk_difference",
        "regression_direction": "decrease", "uncertainty": "paired_bootstrap",
        "minimum_evidence": {"eligible_scenarios": 3},
        "invalid_policy": "insufficient",
    },
    "cost_per_success": {
        "role": "efficiency", "evaluator": "tokens_per_resolved",
        "independent_unit": "scenario", "effect": "median_ratio",
        "regression_direction": "increase", "uncertainty": "bootstrap",
        "minimum_evidence": {"scenarios": 3}, "invalid_policy": "insufficient",
    },
    "steps_per_success": {
        "role": "efficiency", "evaluator": "steps_per_resolved",
        "independent_unit": "scenario", "effect": "median_ratio",
        "regression_direction": "increase", "uncertainty": "bootstrap",
        "minimum_evidence": {"scenarios": 3}, "invalid_policy": "insufficient",
    },
    "latency_per_success": {
        "role": "efficiency", "evaluator": "wallclock_per_resolved",
        "independent_unit": "scenario", "effect": "median_ratio",
        "regression_direction": "increase", "uncertainty": "bootstrap",
        "minimum_evidence": {"scenarios": 3}, "invalid_policy": "insufficient",
    },
    "tool_reliability": {
        "role": "reliability", "evaluator": "tool_call_outcome",
        "independent_unit": "scenario", "effect": "risk_difference",
        "regression_direction": "decrease", "uncertainty": "paired_bootstrap",
        "minimum_evidence": {"scenarios": 3}, "invalid_policy": "insufficient",
    },
}

DIAGNOSTIC_DEFAULTS = {"trace_divergence", "tool_error_profile",
                       "progress_profile"}

COMPARABILITY_DEFAULT = ["model_revision", "serving_runtime", "dependency_lock",
                         "prompt_version", "scaffold_version"]
"""Checked before any trial, and not reachable from a feature. A feature that
could switch comparability off would be a feature that can authorise an invalid
comparison."""


def _threshold(name: str, f: dict) -> float:
    """`regression_threshold` is the one statistic a user must supply."""
    if "practical_threshold" in f:
        return f["practical_threshold"]
    if "regression_threshold" in f:
        return f["regression_threshold"]
    raise ContractError([f"{name}: regression_threshold is required; it is the "
                         "one number only you can choose"])


def resolve(surface: dict) -> tuple[dict, dict]:
    """Expand a surface contract. Returns `(effective, sources)`.

    `sources` maps `feature.field` to `"author"` or `"default"`, so a reviewer
    can tell what was chosen from what was inherited. It is reported alongside
    the effective contract and is deliberately **not** hashed: the hash answers
    "were these the same rules", not "who typed them".
    """
    if not isinstance(surface, dict):
        raise ContractError(["contract must be a mapping"])
    eff = copy.deepcopy(surface)
    sources: dict[str, str] = {}
    problems: list[str] = []

    eff["protocol_version"] = surface.get("protocol_version", PROTOCOL_VERSION)
    eff["contract_version"] = surface.get("contract_version", "surface-1")
    eff["defaults_version"] = DEFAULTS_VERSION
    eff["resolved_schema_version"] = RESOLVED_SCHEMA_VERSION

    # feasibility is never releasable, and the user may not override that.
    mode = surface.get("study_mode", "confirmatory")
    eff["study_mode"] = mode
    if mode == "feasibility":
        if surface.get("verdict_authority") == "release":
            problems.append("study_mode 'feasibility' cannot declare "
                            "verdict_authority 'release'; a feasibility run may "
                            "not produce a release decision")
        eff["verdict_authority"] = "descriptive_only"
        sources["verdict_authority"] = "forced_by_study_mode"
    else:
        eff["verdict_authority"] = surface.get("verdict_authority", "release")
        sources["verdict_authority"] = (
            "author" if "verdict_authority" in surface else "default")

    comp = dict(surface.get("comparability") or {})
    if not comp.get("require_same"):
        comp["require_same"] = list(COMPARABILITY_DEFAULT)
        sources["comparability.require_same"] = "default"
    else:
        sources["comparability.require_same"] = "author"
    comp["mismatch_verdict"] = comp.get("mismatch_verdict", "INCOMPARABLE")
    eff["comparability"] = comp

    dec = dict(surface.get("decision") or {})
    dec["aggregation"] = dec.get("aggregation", "any")
    eff["decision"] = dec

    rca = dict(surface.get("rca") or {})
    rca["run_only_when"] = rca.get("run_only_when", "REGRESSION")
    eff["rca"] = rca

    feats: dict[str, dict] = {}
    for name, given in (surface.get("features") or {}).items():
        given = dict(given or {})
        if name not in FEATURE_DEFAULTS:
            problems.append(
                f"{name!r} is not a known feature {sorted(FEATURE_DEFAULTS)}; "
                "an unrecognised name is not given a generic default, because "
                "that would invent a measurement")
            continue
        base = copy.deepcopy(FEATURE_DEFAULTS[name])
        gate = given.get("gate", "false")
        merged = base | {k: v for k, v in given.items()
                         if k not in ("regression_threshold",)}
        try:
            merged["practical_threshold"] = _threshold(name, given)
        except ContractError as e:
            if str(gate).lower() in ("true", "warning"):
                problems += e.problems
            merged["practical_threshold"] = None
        merged["gate"] = gate

        ev = given.get("evaluator", base["evaluator"])
        if isinstance(ev, dict):
            if "command" not in ev:
                problems.append(f"{name}: an evaluator mapping needs 'command'")
        elif ev not in KNOWN_EVALUATORS:
            problems.append(
                f"{name}: evaluator {ev!r} is unknown. Use one of "
                f"{sorted(KNOWN_EVALUATORS)} or give an explicit "
                "{command: ...}; an unknown name is not silently defaulted")
        merged["evaluator"] = ev

        # surface-2: `capability_regression: true` takes the frozen per-task
        # gate; a mapping overrides named fields of it. The expanded block,
        # with its defaults id, is part of the effective contract and so of
        # the hash. Absent or false, the feature resolves exactly as surface-1.
        cr = given.get("capability_regression")
        if cr is True or isinstance(cr, dict):
            from agentseism import capability as cap
            merged["capability_regression"] = (
                copy.deepcopy(cap.DEFAULTS) | (cr if isinstance(cr, dict) else {}))
            sources[f"{name}.capability_regression"] = (
                "author" if isinstance(cr, dict) else "default")
        elif "capability_regression" in merged:
            del merged["capability_regression"]

        for field in base:
            sources[f"{name}.{field}"] = "author" if field in given else "default"
        sources[f"{name}.practical_threshold"] = "author"
        sources[f"{name}.gate"] = "author" if "gate" in given else "default"
        feats[name] = merged
    eff["features"] = feats

    diags = {}
    for name in (surface.get("diagnostics") or DIAGNOSTIC_DEFAULTS):
        diags[name] = {"verdict_authority": "none"}   # never anything else
        sources[f"diagnostics.{name}.verdict_authority"] = "forced"
    eff["diagnostics"] = diags

    if eff["verdict_authority"] == "release":
        for name, f in feats.items():
            if str(f.get("gate", "")).lower() == "true" \
                    and not f.get("minimum_evidence"):
                problems.append(
                    f"{name}: a release-authority contract needs a "
                    "minimum_evidence rule on every gate; without one nothing "
                    "could ever be INSUFFICIENT_EVIDENCE")

    if problems:
        raise ContractError(problems)
    return eff, sources


def effective_hash(effective: dict) -> str:
    """Over the effective contract, including the versions that produced it.

    Two runs resolved by different tool versions are not the same contract even
    if the surface text is identical, and the hash says so.
    """
    payload = dict(effective)
    payload["_defaults_version"] = effective.get("defaults_version")
    payload["_resolved_schema_version"] = effective.get("resolved_schema_version")
    return canonical_hash(payload)


def resolve_and_validate(surface: dict, path: str | None = None
                         ) -> tuple[Contract, dict, dict]:
    """The whole path. Returns `(contract, surface, sources)`."""
    eff, sources = resolve(surface)
    c = validate(eff, path)
    return c, surface, sources


def provenance(c: Contract, surface: dict, sources: dict) -> dict:
    """Everything a report needs to show how the rules were arrived at."""
    return {**c.provenance(),
            "defaults_version": c.raw.get("defaults_version"),
            "resolved_schema_version": c.raw.get("resolved_schema_version"),
            "surface_contract": surface,
            "effective_contract": c.raw,
            "field_sources": sources}

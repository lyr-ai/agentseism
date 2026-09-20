"""The feature contract: schema, validator, and the verdict engine.

One contract drives the experiment, the CI verdict and the report, so a metric
cannot be chosen after the analysis has been seen.

**Frozen semantics.** Decisions, not defaults; the validator refuses a contract
that cannot express them.

* `comparability.require_same` is checked **before any trial**. A mismatch
  returns `INCOMPARABLE` and no run executes.
* Every gating feature declares all eight of: evaluator, independent unit,
  effect, regression direction, practical threshold, uncertainty, minimum
  evidence, invalid policy. A gate missing one is a gate decided at analysis
  time.
* `REGRESSION` is raised **only** by an outcome feature with `gate: true`.
* Diagnostics carry `verdict_authority: none` and never change a verdict.
* RCA runs **only** when the final verdict is `REGRESSION`.
* Aggregation across gating features is declared in advance.
* `INSUFFICIENT_EVIDENCE` is never escalated by a warning feature or an RCA
  signal. Evidence that was not sufficient does not become sufficient because
  something else looked suspicious.
* The contract version and a canonical content hash go into every report.
* `study_mode: feasibility` with `verdict_authority: descriptive_only` marks a
  contract that must not produce a release verdict — the pilot cannot
  accidentally emit one on three tasks.

Computes verdicts from supplied measurements. Runs no agent, loads no model,
starts no container.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from pathlib import Path

PROTOCOL_VERSION = 1

ROLES = ("outcome", "efficiency", "reliability")
GATES = ("true", "warning", "false")
DIRECTIONS = ("decrease", "increase")
EFFECTS = ("risk_difference", "risk_ratio", "median_difference", "median_ratio")
UNCERTAINTY = ("paired_bootstrap", "bootstrap", "wilson", "normal_approx")
INVALID_POLICY = ("stop", "insufficient", "exclude")
AGGREGATIONS = ("any", "all")
STUDY_MODES = ("confirmatory", "feasibility")
AUTHORITY = ("release", "descriptive_only")

REQUIRED_GATING = ("evaluator", "independent_unit", "effect",
                   "regression_direction", "practical_threshold",
                   "uncertainty", "minimum_evidence", "invalid_policy")

VERDICTS = ("INCOMPARABLE", "REGRESSION", "INSUFFICIENT_EVIDENCE",
            "PASS_WITH_CHANGE", "PASS")


class ContractError(ValueError):
    def __init__(self, problems: list[str]):
        self.problems = problems
        super().__init__("; ".join(problems))


def _gate(f: dict) -> str:
    """YAML `true` is a bool; normalise without letting it mean anything else."""
    g = f.get("gate")
    if g is True:
        return "true"
    if g is False:
        return "false"
    return str(g).lower() if g is not None else ""


def canonical_hash(raw: dict) -> str:
    """Stable under field reordering, sensitive to content.

    `sort_keys` is what makes a reordered YAML the same contract; anything the
    author actually changed still moves the hash.
    """
    return hashlib.sha256(
        json.dumps(raw, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()[:16]


@dataclass
class Contract:
    raw: dict
    path: str | None = None
    content_sha256: str = field(default="", init=False)

    def __post_init__(self):
        self.content_sha256 = canonical_hash(self.raw)

    @property
    def features(self) -> dict:
        return self.raw["features"]

    @property
    def gating(self) -> dict:
        return {k: v for k, v in self.features.items() if _gate(v) == "true"}

    @property
    def diagnostics(self) -> dict:
        return dict(self.raw.get("diagnostics") or {})

    @property
    def require_same(self) -> list[str]:
        return list(self.raw["comparability"]["require_same"])

    @property
    def aggregation(self) -> str:
        return (self.raw.get("decision") or {}).get("aggregation", "any")

    @property
    def descriptive_only(self) -> bool:
        return self.raw.get("verdict_authority") == "descriptive_only"

    def provenance(self) -> dict:
        return {"protocol_version": self.raw["protocol_version"],
                "contract_version": self.raw.get("contract_version"),
                "contract_sha256": self.content_sha256,
                "contract_path": self.path,
                "study_mode": self.raw.get("study_mode", "confirmatory"),
                "verdict_authority": self.raw.get("verdict_authority", "release")}


def validate(raw: dict, path: str | None = None) -> Contract:
    p: list[str] = []

    if raw.get("protocol_version") != PROTOCOL_VERSION:
        p.append(f"protocol_version must be {PROTOCOL_VERSION}, got "
                 f"{raw.get('protocol_version')!r}")
    if raw.get("study_mode", "confirmatory") not in STUDY_MODES:
        p.append(f"study_mode must be one of {STUDY_MODES}")
    if raw.get("verdict_authority", "release") not in AUTHORITY:
        p.append(f"verdict_authority must be one of {AUTHORITY}")
    if raw.get("study_mode") == "feasibility" \
            and raw.get("verdict_authority") != "descriptive_only":
        p.append("study_mode 'feasibility' requires verdict_authority "
                 "'descriptive_only'; a feasibility run must not be able to "
                 "emit a release verdict")

    comp = raw.get("comparability") or {}
    if not comp.get("require_same"):
        p.append("comparability.require_same must list at least one field; "
                 "without it nothing can ever be INCOMPARABLE")
    if comp.get("mismatch_verdict", "INCOMPARABLE") != "INCOMPARABLE":
        p.append("comparability.mismatch_verdict must be INCOMPARABLE")

    feats = raw.get("features") or {}
    if not feats:
        p.append("features is empty")
    for name, f in feats.items():
        if not isinstance(f, dict):
            p.append(f"{name}: feature must be a mapping"); continue
        gate = _gate(f)
        if gate not in GATES:
            p.append(f"{name}: gate must be one of {GATES}, got {f.get('gate')!r}")
            continue
        if f.get("role") not in ROLES:
            p.append(f"{name}: role must be one of {ROLES}, got {f.get('role')!r}")
        if gate == "false":
            continue
        for req in REQUIRED_GATING:
            if f.get(req) in (None, ""):
                p.append(f"{name}: gating feature is missing {req!r}; a gate "
                         "without it is decided at analysis time")
        for key, allowed in (("regression_direction", DIRECTIONS),
                             ("effect", EFFECTS), ("uncertainty", UNCERTAINTY),
                             ("invalid_policy", INVALID_POLICY)):
            if f.get(key) is not None and f.get(key) not in allowed:
                p.append(f"{name}: {key} must be one of {allowed}, "
                         f"got {f.get(key)!r}")
        if f.get("minimum_evidence") is not None \
                and not isinstance(f["minimum_evidence"], dict):
            p.append(f"{name}: minimum_evidence must be a mapping")
        if gate == "true" and f.get("role") != "outcome":
            p.append(f"{name}: gate 'true' is reserved for role 'outcome'; "
                     "only an outcome feature may raise REGRESSION")

    diags = raw.get("diagnostics") or {}
    for name, d in diags.items():
        if name in feats:
            p.append(f"{name}: declared both as a feature and a diagnostic")
        if (d or {}).get("verdict_authority") != "none":
            p.append(f"{name}: diagnostics must declare verdict_authority "
                     "'none'; a trace feature never decides a verdict")

    dec = raw.get("decision") or {}
    if dec.get("aggregation", "any") not in AGGREGATIONS:
        p.append(f"decision.aggregation must be one of {AGGREGATIONS}, declared "
                 "in advance rather than chosen when the numbers arrive")

    rca = raw.get("rca") or {}
    if rca.get("run_only_when", "REGRESSION") != "REGRESSION":
        p.append("rca.run_only_when must be REGRESSION")

    if not any(_gate(f) == "true" for f in feats.values() if isinstance(f, dict)):
        p.append("no feature has gate true; nothing could ever be a REGRESSION")

    if p:
        raise ContractError(p)
    return Contract(raw, path)


def load(path: str | Path) -> Contract:
    import yaml
    path = Path(path)
    return validate(yaml.safe_load(path.read_text()), str(path))


# ────────────────────────── verdict engine ──────────────────────────

@dataclass
class Measurement:
    """One feature measured on both arms. Supplied, not computed here."""
    effect: float
    ci_low: float
    ci_high: float
    evidence: dict = field(default_factory=dict)   # matches minimum_evidence keys
    invalid: int = 0


def _regressed(f: dict, m: Measurement) -> bool:
    """Past the practical threshold, with the interval agreeing.

    The interval must exclude the threshold, not merely exclude zero. A real
    difference smaller than the declared practical threshold is not a
    regression — which is the reason for declaring one.
    """
    thr = float(f["practical_threshold"])
    if f["regression_direction"] == "decrease":
        return m.effect <= -thr and m.ci_high <= -thr
    return m.effect >= thr and m.ci_low >= thr


def _sufficient(f: dict, m: Measurement) -> bool:
    need = f.get("minimum_evidence") or {}
    return all(m.evidence.get(k, 0) >= v for k, v in need.items())


def decide(contract: Contract, fingerprint_baseline: dict,
           fingerprint_candidate: dict,
           measurements: dict[str, Measurement] | None = None,
           diagnostic_changed: list[str] | None = None) -> dict:
    """The verdict, in the order the semantics fix.

    Comparability first, before any trial. Then a confirmed regression. Then
    insufficient evidence — never escalated because a warning feature or an RCA
    signal looked suspicious. Then pass, annotated if diagnostics moved.
    """
    prov = contract.provenance()

    mismatched = sorted(k for k in contract.require_same
                        if fingerprint_baseline.get(k)
                        != fingerprint_candidate.get(k))
    if mismatched:
        return {"verdict": "INCOMPARABLE", "mismatched": mismatched,
                "trials_run": 0, "rca": False,
                "reason": "serving fingerprint changed: " + ", ".join(mismatched),
                **prov}

    if measurements is None:
        raise ValueError("comparable, so measurements are required")

    unknown = sorted(set(measurements) - set(contract.features)
                     - set(contract.diagnostics))
    if unknown:
        raise ContractError([f"measurement for unknown feature {u!r}; the "
                             "contract is the list of what may be measured"
                             for u in unknown])

    regressed, insufficient, warnings, stopped = [], [], [], []
    for name, f in contract.features.items():
        gate = _gate(f)
        if gate == "false" or name not in measurements:
            continue
        m = measurements[name]
        if m.invalid and f.get("invalid_policy") == "stop":
            stopped.append(name)
        if gate == "true":
            if m.invalid and f.get("invalid_policy") == "insufficient":
                insufficient.append(name)
            elif not _sufficient(f, m):
                insufficient.append(name)
            elif _regressed(f, m):
                regressed.append(name)
        elif gate == "warning" and _sufficient(f, m) and _regressed(f, m):
            warnings.append(name)

    if stopped:
        return {"verdict": "INSUFFICIENT_EVIDENCE", "invalid_stop": stopped,
                "insufficient": insufficient, "warnings": warnings, "rca": False,
                "reason": "invalid runs on a feature whose policy is 'stop': "
                          + ", ".join(stopped), **prov}

    fires = (bool(regressed) if contract.aggregation == "any"
             else bool(regressed) and len(regressed) == len(contract.gating))

    if fires:
        return {"verdict": "REGRESSION", "regressed": regressed,
                "warnings": warnings, "insufficient": insufficient, "rca": True,
                "reason": "gating outcome feature(s) regressed: "
                          + ", ".join(regressed), **prov}
    if insufficient:
        return {"verdict": "INSUFFICIENT_EVIDENCE", "insufficient": insufficient,
                "warnings": warnings, "rca": False,
                "reason": "gating feature(s) below minimum evidence: "
                          + ", ".join(insufficient), **prov}
    changed = sorted(diagnostic_changed or [])
    if changed:
        return {"verdict": "PASS_WITH_CHANGE", "diagnostic_changed": changed,
                "warnings": warnings, "rca": False,
                "reason": "outcomes held; diagnostics moved: " + ", ".join(changed),
                **prov}
    return {"verdict": "PASS", "warnings": warnings, "rca": False,
            "reason": "no gating feature regressed", **prov}

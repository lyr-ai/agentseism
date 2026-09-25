"""Capability regression: did a task that reliably worked stop working?

The second gate of surface-2, beside the population gate in `contract.py`.
Specified in `analysis/CI_V1_REGRESSION_SEMANTICS.md`; every choice here is a
frozen value from that document, not a tuning knob.

**Estimand.** For one task, conditional on the task and the code version, the
drop in the agent's success probability, `p_base − p_cand`. No population claim.

**Unit.** An independently started run *within* the task. Here the runs are
the sample, and that rests on an assumption the caller must be able to defend:
each run starts clean (fresh container, fresh process, no shared history), so
within an arm the runs are independent Bernoulli draws with a common success
probability. The population gate makes the opposite choice for its own question
and resamples tasks, not runs. The two are different estimands, so this is not
a contradiction.

**Rule.** A task is *eligible* when its baseline success rate reaches the
eligibility bar with enough valid trials and no invalid run in either arm. On
the K eligible tasks, fixed by the baseline before any candidate run, the gate
fires on a task when the observed drop reaches the practical threshold **and**
a one-sided Fisher exact test gives `p <= alpha / K` (Bonferroni). A smaller
drop that reaches `warn_threshold` without firing is a non-blocking WARNING.
Ineligible tasks are *not monitored* and are reported as such, never silently
dropped.

At 8 trials and K >= 4 the exact-test boundary binds before the practical
threshold does: the smallest observed drop that fires is 0.75 (8/8 -> 2/8,
7/8 -> 1/8). The gate detects collapse. It is not a general severe-drop
detector, and the report must not claim otherwise.

Pure arithmetic: no runner, no model, no container.
"""

from __future__ import annotations

from dataclasses import dataclass
from math import comb

TESTS = ("fisher_exact_one_sided",)
MULTIPLICITY = ("bonferroni_over_eligible",)
INVALID_POLICY = ("exclude_task",)
REQUIRED = ("eligibility", "practical_threshold", "test", "alpha",
            "multiplicity", "minimum_evidence", "invalid_policy",
            "warn_threshold")

DEFAULTS_ID = "capability-1"
DEFAULTS = {
    "defaults": DEFAULTS_ID,
    "independent_unit": "run_within_scenario",
    "assumes": "independent_clean_runs",
    "eligibility": {"baseline_success_min": 0.875},
    "practical_threshold": 0.50,
    "test": "fisher_exact_one_sided",
    "alpha": 0.05,
    "multiplicity": "bonferroni_over_eligible",
    "minimum_evidence": {"trials_per_condition": 8},
    "invalid_policy": "exclude_task",
    "warn_threshold": 0.375,
}
"""The frozen surface-2 values. Recorded in the effective contract with their
`defaults` id, so the contract hash moves if these ever do."""


@dataclass(frozen=True)
class TaskCounts:
    """Valid-run successes and trials for one task in both arms."""
    base_successes: int
    base_trials: int
    cand_successes: int
    cand_trials: int
    invalid: int = 0          # invalid runs in either arm


def fisher_one_sided(base_successes: int, base_trials: int,
                     cand_successes: int, cand_trials: int) -> float:
    """P(candidate successes <= observed | both margins), hypergeometric.

    The one-sided exact test for "the candidate succeeds less often". Exact
    integer arithmetic, so the boundaries in the design document are
    reproduced without floating-point ties.
    """
    total = base_successes + cand_successes
    n = base_trials + cand_trials
    denom = comb(n, total)
    lo = max(0, total - base_trials)
    num = sum(comb(cand_trials, x) * comb(base_trials, total - x)
              for x in range(lo, cand_successes + 1))
    return num / denom


def _meets(value_num: int, value_den: int, threshold: float) -> bool:
    """`value_num / value_den >= threshold`, decided without float division.

    Thresholds such as 0.875 and 0.375 are exact in binary, so comparing the
    cross-multiplied integers is exact wherever it matters.
    """
    return value_num >= threshold * value_den


def evaluate(spec: dict, tasks: dict[str, TaskCounts]) -> dict:
    """Run the gate over every task. Returns the full, reportable result.

    `fired`, `warnings` and `not_monitored` are sorted lists of task names;
    `detail` holds counts, the drop, p and the Bonferroni limit per task, and
    the reason a task is not monitored.
    """
    need = int((spec.get("minimum_evidence") or {}).get("trials_per_condition", 0))
    bar = float(spec["eligibility"]["baseline_success_min"])
    thr = float(spec["practical_threshold"])
    warn = float(spec["warn_threshold"])
    alpha = float(spec["alpha"])

    detail: dict[str, dict] = {}
    eligible: list[str] = []
    for name, t in sorted(tasks.items()):
        d = {"baseline": f"{t.base_successes}/{t.base_trials}",
             "candidate": f"{t.cand_successes}/{t.cand_trials}"}
        if t.invalid:
            d["not_monitored"] = f"{t.invalid} invalid run(s); task excluded"
        elif min(t.base_trials, t.cand_trials) < need:
            d["not_monitored"] = (f"fewer than {need} valid trials per arm")
        elif not _meets(t.base_successes, t.base_trials, bar):
            d["not_monitored"] = (f"baseline below {bar:g}; a task that did "
                                  "not reliably work cannot stop working")
        else:
            eligible.append(name)
        detail[name] = d

    k = len(eligible)
    limit = alpha / k if k else None
    fired, warnings = [], []
    for name in eligible:
        t = tasks[name]
        # drop = b/nb - c/nc, compared exactly as integers over nb*nc
        drop_num = t.base_successes * t.cand_trials - t.cand_successes * t.base_trials
        den = t.base_trials * t.cand_trials
        p = fisher_one_sided(t.base_successes, t.base_trials,
                             t.cand_successes, t.cand_trials)
        d = detail[name]
        d |= {"drop": drop_num / den, "p": p, "limit": limit}
        if _meets(drop_num, den, thr) and p <= limit:
            d["decision"] = "FIRED"
            fired.append(name)
        elif _meets(drop_num, den, warn):
            d["decision"] = "WARNING"
            warnings.append(name)
        else:
            d["decision"] = "PASS"
    return {"k": k, "alpha_per_task": limit, "eligible": eligible,
            "fired": fired, "warnings": warnings,
            "not_monitored": sorted(n for n, d in detail.items()
                                    if "not_monitored" in d),
            "detail": detail}


def validate_spec(name: str, spec) -> list[str]:
    """Problems with a feature's `capability_regression` block, if any."""
    if not isinstance(spec, dict):
        return [f"{name}: capability_regression must be a mapping"]
    p = [f"{name}: capability_regression is missing {r!r}; a gate without it "
         "is decided at analysis time" for r in REQUIRED if spec.get(r) in (None, "")]
    if p:
        return p
    if spec["test"] not in TESTS:
        p.append(f"{name}: capability_regression.test must be one of {TESTS}")
    if spec["multiplicity"] not in MULTIPLICITY:
        p.append(f"{name}: capability_regression.multiplicity must be one of "
                 f"{MULTIPLICITY}")
    if spec["invalid_policy"] not in INVALID_POLICY:
        p.append(f"{name}: capability_regression.invalid_policy must be one of "
                 f"{INVALID_POLICY}")
    elig = spec["eligibility"]
    if not isinstance(elig, dict) or "baseline_success_min" not in elig:
        p.append(f"{name}: capability_regression.eligibility needs "
                 "baseline_success_min")
    if not isinstance(spec["minimum_evidence"], dict) \
            or "trials_per_condition" not in spec["minimum_evidence"]:
        p.append(f"{name}: capability_regression.minimum_evidence needs "
                 "trials_per_condition")
    try:
        a, thr, warn = (float(spec["alpha"]), float(spec["practical_threshold"]),
                        float(spec["warn_threshold"]))
        if not 0 < a < 1:
            p.append(f"{name}: capability_regression.alpha must be in (0, 1)")
        if not 0 < warn < thr <= 1:
            p.append(f"{name}: capability_regression needs 0 < warn_threshold "
                     "< practical_threshold <= 1; a warning at or above the "
                     "blocking threshold is not a warning")
    except (TypeError, ValueError):
        p.append(f"{name}: capability_regression thresholds must be numbers")
    return p

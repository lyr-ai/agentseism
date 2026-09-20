"""The frozen correctness checker C2-H binds (`PREREG_C2H.md` §4.2).

It must be the *same* deterministic rule that produced the 4-of-20 labels the
feasibility model rests on. Not an equivalent one, and not a reimplementation
that agrees on the cases anyone happened to look at:
`verify_against_frozen_labels()` replays all twenty frozen donors offline and
requires every label to match, item by item.

The rule itself is one line of SWE-bench's own output:

    resolved == True   ->  PASS
    resolved == False  ->  FAIL

Everything else is a refusal. `infra_failure`, a missing report, a patch that
did not apply, an absent `resolved` key -- none of those is a correctness
verdict, and turning one into `FAIL` would put infrastructure noise into the
arm the experiment is about. They raise `UnlabelledDonor`, which C2-H records
as `invalid`: counted towards the cap, towards neither arm, never adjudicated
by hand.

**Offline.** Reading a committed report calls no model and starts no container.
"""

from __future__ import annotations

import json
from pathlib import Path

from experiments.coding.c2h_backend import UnlabelledDonor

ROOT = Path(__file__).resolve().parents[2]
EVAL_ROOT = ROOT / "logs/run_evaluation"
FROZEN_LABELS = ROOT / "paper/manifests/correctness_labels.json"
MODEL_DIR = "agentseism"
INSTANCE = "pytest-dev__pytest-10051"


def report_path(run_key: str, eval_root: Path | None = None) -> Path:
    return (eval_root or EVAL_ROOT) / run_key / MODEL_DIR / INSTANCE / "report.json"


def label_from_report(report: dict, instance: str = INSTANCE) -> str:
    """`resolved` -> PASS / FAIL. Anything else refuses."""
    body = report.get(instance)
    if body is None:
        raise UnlabelledDonor(f"report has no entry for {instance!r}")
    if body.get("infra_failure"):
        raise UnlabelledDonor("infra_failure: not a correctness verdict")
    if not body.get("patch_exists", False):
        raise UnlabelledDonor("no patch: nothing was evaluated")
    if not body.get("patch_successfully_applied", False):
        raise UnlabelledDonor("patch did not apply: not a correctness verdict")
    if "resolved" not in body:
        raise UnlabelledDonor("report has no 'resolved' field")
    return "PASS" if body["resolved"] else "FAIL"


def checker(run_key: str, eval_root: Path | None = None):
    """Bindable as `RealBackend(checker=...)`: takes a run key, returns a label."""
    path = report_path(run_key, eval_root)
    if not path.exists():
        raise UnlabelledDonor(f"no evaluation report at {path}")
    return label_from_report(json.loads(path.read_text()))


def frozen_rows() -> list[dict]:
    return json.loads(FROZEN_LABELS.read_text())["rows"]


NAMING_EXCEPTIONS = {("a1", "r0"): "smoke_a1_r0"}
"""One frozen donor's evaluation lives under a different directory name.

`a1/r0` was evaluated first, as a smoke test, before the batch naming settled,
so its report is at `smoke_a1_r0` rather than
`h2_phase_a1__<instance>__r0`. Recorded as an explicit exception rather than
inferred by a fuzzy lookup: a checker that searches for a plausible report is a
checker that can find the wrong one. Its contents were verified to be the same
instance, `patch_successfully_applied`, no `infra_failure`, `resolved: true`.
"""


def run_key_for(row: dict) -> str:
    """The evaluation directory a frozen row corresponds to."""
    exception = NAMING_EXCEPTIONS.get((row["batch"], row["run"]))
    if exception:
        return exception
    if row["batch"] == "a1":
        return f"h2_phase_a1__{INSTANCE}__{row['run']}"
    return f"h2_phase_b__{row['run']}"


def verify_against_frozen_labels() -> dict:
    """Replay all twenty frozen donors offline; every label must match.

    This is the gate that lets C2-H claim continuity with the 4-of-20 donor
    yield its cost model and its donor-count analysis are built on. A single
    mismatch means the checker being bound is not the checker that produced
    those numbers, and the feasibility work would need redoing rather than
    reinterpreting.
    """
    rows, mismatches, unlabelled = frozen_rows(), [], []
    for row in rows:
        want = "PASS" if row["resolved"] else "FAIL"
        key = run_key_for(row)
        try:
            got = checker(key)
        except UnlabelledDonor as exc:
            unlabelled.append({"run": row["run"], "batch": row["batch"],
                               "reason": str(exc)})
            continue
        if got != want:
            mismatches.append({"run": row["run"], "batch": row["batch"],
                               "frozen": want, "replayed": got})
    n_fail = sum(1 for r in rows if not r["resolved"])
    return {"n": len(rows), "frozen_fail": n_fail,
            "frozen_pass": len(rows) - n_fail,
            "mismatches": mismatches, "unlabelled": unlabelled,
            "identical": not mismatches and not unlabelled}


if __name__ == "__main__":
    r = verify_against_frozen_labels()
    print(f"frozen donors      {r['n']}")
    print(f"frozen FAIL / PASS {r['frozen_fail']} / {r['frozen_pass']}")
    print(f"mismatches         {len(r['mismatches'])}  {r['mismatches']}")
    print(f"unlabelled         {len(r['unlabelled'])}  {r['unlabelled']}")
    print("IDENTICAL:", r["identical"])
    raise SystemExit(0 if r["identical"] else 1)

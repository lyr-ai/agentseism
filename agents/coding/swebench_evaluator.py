"""Score one artifact directory with the SWE-bench harness. Deterministic.

    swebench_evaluator.py <artifact_dir>

AgentSeism's evaluator contract: stdout is JSON, and anything else is invalid.
This prints one object with `success` — the only field the contract's
`task_success` feature reads — plus fields a human needs to trust it.

It adds **no scoring semantics**. The verdict comes from
`experiments/coding/c2h_checker.label_from_report`, which already refuses to
label an infra failure, a missing patch or a patch that did not apply. That
refusal is the point: those are not correctness outcomes, and a scorer that
turned them into `FAIL` would report an infrastructure problem as a regression.
Here a refusal becomes `invalid`, which AgentSeism counts separately and never
scores as a failure.

An empty patch is scored, not refused: an agent that submitted nothing failed
the task. Only the harness being unable to judge is invalid.
"""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from experiments.coding.c2h_checker import (  # noqa: E402
    UnlabelledDonor, label_from_report,
)

DATASET = "SWE-bench/SWE-bench_Verified"
SPLIT = "test"


def evaluate(artifact_dir: Path) -> dict:
    run = json.loads((artifact_dir / "run.json").read_text())
    instance = run["instance_id"]
    patch = (artifact_dir / "patch.diff").read_text()

    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        preds = tmp / "preds.jsonl"
        preds.write_text(json.dumps({
            "instance_id": instance,
            "model_name_or_path": "agentseism",
            "model_patch": patch,
        }) + "\n")
        run_id = f"agentseism_{instance}"
        reports = tmp / "reports"
        reports.mkdir()
        proc = subprocess.run(
            [sys.executable, "-m", "swebench.harness.run_evaluation",
             "--dataset_name", DATASET, "--split", SPLIT,
             "--predictions_path", str(preds), "--run_id", run_id,
             "--max_workers", "1", "--timeout", "1800",
             "--report_dir", str(reports)],
            capture_output=True, text=True, timeout=3600)
        found = sorted(reports.rglob("*.json"))
        if not found:
            return {"invalid": True,
                    "reason": "the harness produced no report",
                    "stderr": proc.stderr[-800:]}
        report = json.loads(found[0].read_text())

    try:
        label = label_from_report(report, instance)
    except UnlabelledDonor as exc:
        # Not a correctness verdict. Invalid, never a failure.
        return {"invalid": True, "reason": str(exc), "instance_id": instance}

    return {"success": int(label == "PASS"),
            "instance_id": instance,
            "label": label,
            "patch_bytes": len(patch),
            "exit_status": run.get("exit_status", ""),
            "step_limit": run.get("step_limit")}


def main(argv=None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    if len(argv) != 1:
        print(json.dumps({"invalid": True,
                          "reason": "usage: swebench_evaluator.py <artifact_dir>"}))
        return 2
    d = Path(argv[0])
    try:
        print(json.dumps(evaluate(d), sort_keys=True))
    except Exception as exc:                                    # noqa: BLE001
        # stdout stays JSON even on failure: the contract says anything else is
        # invalid, and a traceback on stdout would be read as a scoring result.
        print(json.dumps({"invalid": True,
                          "reason": f"{type(exc).__name__}: {exc}"}))
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

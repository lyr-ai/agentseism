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
scores as a failure. The field is `invalid_reason`, which is what `run_trials`
reads -- a diagnosis under any other key is dropped, and the operator sees an
invalid run with no explanation.

An empty patch is scored here, without the harness, and only when the agent's
own exit status shows it ran to an agent-level end: it spent its step or cost
budget (`LimitsExceeded`), or it submitted and its diff was empty
(`Submitted`). Either way the agent failed the task. The harness cannot be
asked, because it silently drops empty predictions and writes no report, and
that missing report used to come back as `invalid`. That hid exactly the
failure a step-limit cut produces.

An empty patch with any other exit status stays `invalid`: wall-clock
`TimeExceeded` (host speed, not agent budget), `RepeatedFormatError`, an
unknown status, or none at all. A run that raised never writes
`agent_run.json` and is invalid before it gets here. Only the harness being
unable to judge a real patch is invalid on the other path.
"""

from __future__ import annotations

import json
import os
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
# Exit statuses after which an empty patch is the agent's failure, not a
# measurement failure. Deliberately narrow; see the module docstring.
EMPTY_PATCH_IS_FAILURE = frozenset({"LimitsExceeded", "Submitted"})
SPLIT = "test"
MODEL_NAME = "agentseism"


def evaluate(artifact_dir: Path) -> dict:
    run = json.loads((artifact_dir / "agent_run.json").read_text())
    instance = run["instance_id"]
    patch = (artifact_dir / "patch.diff").read_text()
    status = str(run.get("exit_status") or "")

    if not patch.strip():
        if status in EMPTY_PATCH_IS_FAILURE:
            return {"success": 0,
                    "instance_id": instance,
                    "label": "FAIL",
                    "scored_by": "empty_patch",
                    "patch_bytes": len(patch),
                    "exit_status": status,
                    "step_limit": run.get("step_limit")}
        return {"invalid": True,
                "invalid_reason": f"empty patch after exit status {status!r}, "
                                  "which is not an agent-level end",
                "instance_id": instance}

    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        preds = tmp / "preds.jsonl"
        preds.write_text(json.dumps({
            "instance_id": instance,
            "model_name_or_path": MODEL_NAME,
            "model_patch": patch,
        }) + "\n")
        run_id = f"agentseism_{instance}_{os.getpid()}"
        reports = tmp / "reports"
        reports.mkdir()
        proc = subprocess.run(
            [sys.executable, "-m", "swebench.harness.run_evaluation",
             "--dataset_name", DATASET, "--split", SPLIT,
             "--predictions_path", str(preds), "--run_id", run_id,
             "--max_workers", "1", "--timeout", "1800",
             "--report_dir", str(reports)],
            capture_output=True, text=True, timeout=3600)

        # The **per-instance** report, not the run-level summary `--report_dir`
        # receives. The summary carries `resolved_ids` and has no entry keyed by
        # the instance, so reading it yields "report has no entry for ..." -- the
        # same mistake this project already made once, on a rented host.
        # The harness writes this tree relative to the working directory.
        per_instance = (Path("logs/run_evaluation") / run_id / MODEL_NAME
                        / instance / "report.json")
        if not per_instance.is_file():
            return {"invalid": True,
                    "invalid_reason": f"no per-instance report at {per_instance}",
                    "stderr": proc.stderr[-800:]}
        report = json.loads(per_instance.read_text())

    try:
        label = label_from_report(report, instance)
    except UnlabelledDonor as exc:
        # Not a correctness verdict. Invalid, never a failure.
        return {"invalid": True, "invalid_reason": str(exc),
                "instance_id": instance}

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
                          "invalid_reason": "usage: swebench_evaluator.py <dir>"}))
        return 2
    d = Path(argv[0])
    try:
        print(json.dumps(evaluate(d), sort_keys=True))
    except Exception as exc:                                    # noqa: BLE001
        # stdout stays JSON even on failure: the contract says anything else is
        # invalid, and a traceback on stdout would be read as a scoring result.
        print(json.dumps({"invalid": True,
                          "invalid_reason": f"{type(exc).__name__}: {exc}"}))
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

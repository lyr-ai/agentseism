"""Attach SWE-bench correctness labels to recorded trajectories.

This is the step that turns "the runs ended differently" into "the runs ended
differently and some of them were wrong". Until it exists, every topology result
in this project describes variation without saying whether the variation
mattered.

**Exploratory by construction.** No pre-registration covers correctness: it was
never part of the coding experiment, H2 or H3. Any relationship found here
between topology, divergence and correctness is hypothesis-generating, and
saying so is cheaper now than defending it later.

One structural constraint shapes the whole script. SWE-bench keys predictions by
`instance_id`, and the surviving data is **twenty runs of one instance**. They
cannot share a predictions file — each run is its own evaluation with its own
`run_id`.
"""

from __future__ import annotations

import argparse
import glob
import json
import os
from pathlib import Path

MODEL = "agentseism"


def collect(roots: list[str]) -> list[dict]:
    """Every trajectory that submitted a non-empty patch."""
    rows = []
    for root in roots:
        batch = Path(root).name
        for path in sorted(glob.glob(f"{root}/*.json")):
            name = Path(path).stem
            if name.endswith(".probe"):
                continue
            data = json.loads(Path(path).read_text())
            info = data.get("info", {})
            patch = (info.get("submission") or "").strip()
            if str(info.get("exit_status")) != "Submitted" or not patch:
                continue
            # Continuations are named A_0 / B_3; Phase A runs carry the instance
            # in the filename. Both need the instance id to evaluate.
            instance = name.rsplit("__r", 1)[0] if "__r" in name else None
            if instance is None:
                instance = json.loads(
                    Path(path).read_text()
                )["info"]["config"]["environment"]["image"]
                instance = instance.split(".")[-1].split(":")[0].replace("_1776_", "__")
            rows.append({
                "batch": batch,
                "run": name,
                "instance_id": instance,
                "patch": patch,
                "run_key": f"{batch}__{name}",
            })
    return rows


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--runs", nargs="+", required=True)
    ap.add_argument("--out", required=True, help="directory for per-run prediction files")
    args = ap.parse_args()

    rows = collect(args.runs)
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)

    index = []
    for row in rows:
        prediction = {
            "instance_id": row["instance_id"],
            "model_name_or_path": MODEL,
            "model_patch": row["patch"] if row["patch"].endswith("\n") else row["patch"] + "\n",
        }
        path = out / f"{row['run_key']}.jsonl"
        path.write_text(json.dumps(prediction) + "\n")
        index.append({k: row[k] for k in ("batch", "run", "instance_id", "run_key")}
                     | {"predictions": str(path), "patch_bytes": len(row["patch"])})

    (out / "index.json").write_text(json.dumps(index, indent=1) + "\n")
    by_instance: dict[str, int] = {}
    for row in index:
        by_instance[row["instance_id"]] = by_instance.get(row["instance_id"], 0) + 1
    print(f"{len(index)} submitted runs across {len(by_instance)} instances")
    for instance, count in sorted(by_instance.items()):
        print(f"  {instance:<34} {count}")
    print(f"\nwrote {out}/index.json and {len(index)} prediction files")


if __name__ == "__main__":
    main()

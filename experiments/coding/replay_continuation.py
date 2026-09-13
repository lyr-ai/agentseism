"""Regenerate archives for continuations that were run without archiving on.

Phase B was collected with `probe_output` but not `probe_archive`, so three of
the four failing trajectories cannot be forked from — there are no step
archives behind their fingerprints. Replay is the bridge that already exists for
exactly this: re-execute the recorded commands with archiving enabled, no model
in the loop, Docker and no GPU.

A continuation is not replayable from a clean image, though. It begins at its
donor's fork state, so the container is first materialised from the donor's
archive and only then are the continuation's own commands replayed into it.
"""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from agents.coding.fork import materialize
from experiments.coding.replay import probe_rows


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--runs", required=True)
    ap.add_argument("--manifest", required=True)
    ap.add_argument("--run", required=True, help="continuation name, e.g. A_3")
    ap.add_argument("--archive", required=True, help="where to write the new archive")
    ap.add_argument("--platform", default="linux/amd64")
    ap.add_argument("--timeout", type=int, default=600)
    args = ap.parse_args()

    manifest = json.loads(Path(args.manifest).read_text())
    arm = args.run.split("_")[0]
    donor = manifest["arms"][arm]
    runs = Path(args.runs)
    step_dir = runs / "h2_phase_a1" / donor["archive"]

    archive = Path(args.archive)
    archive.mkdir(parents=True, exist_ok=True)
    probe_out = archive / "replay.probe.jsonl"
    probe_out.unlink(missing_ok=True)

    run_args = ["--rm"] + ([f"--platform={args.platform}"] if args.platform else [])
    env, snapshot = materialize(
        step_dir, manifest["image"],
        {"tracked_diff_hash": donor["tracked_diff_hash"],
         "workspace_diff_hash": donor["workspace_diff_hash"]},
        probe_output=str(probe_out), probe_archive=str(archive),
        timeout=args.timeout, run_args=run_args,
    )
    print(f"materialised {arm} fork point: {snapshot['tracked_diff_hash'][:12]}")

    original = probe_rows(runs / "h2_phase_b" / f"{args.run}.probe.jsonl")
    trajectory = json.loads((runs / "h2_phase_b" / f"{args.run}.json").read_text())
    messages = trajectory["messages"]
    prefix = donor["prefix_messages"]

    # Message positions are found by walking, not by arithmetic. A format error
    # inserts messages without advancing the environment's step counter, so
    # `prefix + 2*(step-1)` lands on the wrong turn the moment one occurs -- and
    # one does, at step 12 of A_3.
    acting = [i for i, m in enumerate(messages[prefix:], start=prefix)
              if m.get("role") == "assistant" and (m.get("extra", {}).get("actions"))]

    mismatches = []
    try:
        for row in original:
            step = row["step"]
            command = row["command"]
            if step > len(acting):
                raise ValueError(f"step {step}: no acting message for it")
            index = acting[step - 1]
            recorded = messages[index]["extra"]["actions"][0]["command"]
            if recorded != command:
                raise ValueError(f"step {step}: probe and message disagree")
            env.execute({"command": command})
            fresh = probe_rows(probe_out)[-1]
            if fresh["tracked_diff_hash"] != row["tracked_diff_hash"]:
                mismatches.append(step)
            (env.step_dir() / "messages.json").write_text(json.dumps(
                {"env_step": env.step_index, "replayed": True,
                 "coherent_fork_point": True,
                 "absolute_step": donor["fork_step"] + step,
                 "messages": messages[: index + 2]}, indent=1))
    finally:
        env.cleanup()

    print(f"{args.run}: replayed {len(original)} steps into {archive}")
    print(f"  tracked-state mismatches: {mismatches or 'none'}")
    if mismatches:
        raise SystemExit(1)


if __name__ == "__main__":
    main()

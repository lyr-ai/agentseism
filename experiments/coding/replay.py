"""Re-execute a recorded trajectory's commands, with no model in the loop.

The primary experiment stored fingerprints and not the bytes behind them, so
nothing can be forked from it directly. Replay is the bridge: the commands are
in the probe log, they are deterministic shell, and running them again in the
same image reproduces the states the fingerprints name -- this time with the
archive turned on.

There is no model call here, which is the point. Replay costs Docker and no GPU,
and it lets the fork machinery be validated before any GPU is rented. It is also
a check on its own premise: if replaying a trajectory does not reproduce its
recorded `tracked_diff_hash`, then those states were not reachable from the
recorded commands alone, and that is worth knowing before designing around them.

Replay reproduces *state*, not outputs. A command whose stdout differs, or which
times out, is not a failure of replay unless the repository ends up different.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path


def load_trajectory(path: str | Path) -> dict:
    return json.loads(Path(path).read_text())


def probe_rows(path: str | Path) -> list[dict]:
    return [json.loads(line) for line in Path(path).read_text().splitlines() if line.strip()]


def message_prefix(messages: list[dict], step: int) -> list[dict]:
    """The message log as it stood just after environment step `step`.

    The layout is fixed by the agent loop: system, instance, then one assistant
    message and one observation per action. Every message in the primary
    experiment carried exactly one action, which is asserted rather than assumed
    -- a message with two would break the arithmetic silently, and the resulting
    prefix would end mid-turn.
    """
    assistants = [i for i, m in enumerate(messages) if m.get("role") == "assistant"]
    for index in assistants:
        actions = messages[index].get("extra", {}).get("actions", [])
        if len(actions) != 1:
            raise ValueError(f"message {index} carries {len(actions)} actions, not 1")
    if step < 1 or 2 + 2 * step > len(messages):
        raise ValueError(f"step {step} outside trajectory of {len(messages)} messages")
    return messages[: 2 + 2 * step]


def replay(
    trajectory: str | Path,
    probe: str | Path,
    image: str,
    archive: str | Path,
    upto: int,
    *,
    repo: str = "/testbed",
    timeout: int = 600,
    run_args: list[str] | None = None,
) -> dict:
    """Run steps 1..`upto` of a recorded trajectory into a fresh container."""
    from agents.coding.instrumented_docker import InstrumentedDockerEnvironment

    rows = probe_rows(probe)
    messages = load_trajectory(trajectory)["messages"]
    archive = Path(archive)
    archive.mkdir(parents=True, exist_ok=True)

    env = InstrumentedDockerEnvironment(
        image=image,
        probe_repo=repo,
        probe_output=str(archive / "replay.probe.jsonl"),
        probe_archive=str(archive),
        timeout=timeout,
        run_args=run_args if run_args is not None else ["--rm"],
    )
    results = []
    try:
        for row in rows:
            step = row["step"]
            if step > upto:
                break
            command = row["command"]
            # Alignment: the assistant message for this step must hold the same
            # command the probe recorded, or the message prefix written below
            # belongs to a different point in the run.
            recorded = messages[2 + 2 * (step - 1)]["extra"]["actions"][0]["command"]
            if recorded != command:
                raise ValueError(f"step {step}: probe command and message action disagree")
            env.execute({"command": command})
            (env.step_dir() / "messages.json").write_text(
                json.dumps(
                    {
                        "env_step": env.step_index,
                        "n_messages": 2 + 2 * step,
                        "coherent_fork_point": True,
                        "replayed": True,
                        "messages": message_prefix(messages, step),
                    },
                    indent=1,
                )
            )
            fresh = probe_rows(archive / "replay.probe.jsonl")[-1]
            results.append(
                {
                    "step": step,
                    "original_tracked": row["tracked_diff_hash"],
                    "replay_tracked": fresh["tracked_diff_hash"],
                    "original_workspace": row["workspace_diff_hash"],
                    "replay_workspace": fresh["workspace_diff_hash"],
                    "tracked_match": row["tracked_diff_hash"] == fresh["tracked_diff_hash"],
                    "workspace_match": row["workspace_diff_hash"] == fresh["workspace_diff_hash"],
                }
            )
    finally:
        env.cleanup()
    return {"archive": str(archive), "steps": results}


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--trajectory", required=True)
    ap.add_argument("--probe", required=True)
    ap.add_argument("--image", required=True)
    ap.add_argument("--archive", required=True)
    ap.add_argument("--upto", type=int, required=True)
    ap.add_argument("--platform", default="linux/amd64")
    args = ap.parse_args()

    run_args = ["--rm"] + ([f"--platform={args.platform}"] if args.platform else [])
    out = replay(args.trajectory, args.probe, args.image, args.archive, args.upto, run_args=run_args)
    print(f"{'step':>5}{'tracked':>10}{'workspace':>12}")
    for row in out["steps"]:
        print(f"{row['step']:>5}{str(row['tracked_match']):>10}{str(row['workspace_match']):>12}")
    bad = [r["step"] for r in out["steps"] if not r["tracked_match"]]
    print(f"\ntracked-state mismatches: {bad or 'none'}")


if __name__ == "__main__":
    main()

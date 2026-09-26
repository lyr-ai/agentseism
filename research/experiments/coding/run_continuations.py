"""Phase B: continue from one recorded state, three times over, with different context.

Every continuation starts in a container holding the same tracked source `S` and
differs only in what it carries into it:

    arm A     donor A's message log and donor A's untracked files
    arm B     donor B's, likewise
    fresh     the system and instance messages only, and no scratch files

The manifest is read, never recomputed. Selecting the fork point is Phase A's
job and it is finished; recomputing it here would leave the choice open at a
point where the outcomes are becoming visible, which is the freedom the manifest
exists to remove.

The fresh arm's opening messages are copied from a donor's own prefix rather than
re-rendered from the templates. They are the same two messages by construction --
same task, same templates -- and taking them from the archive means the three
arms cannot differ through a template variable that was set differently here than
in Phase A.
"""

from __future__ import annotations

import argparse
import copy
import json
import os
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import yaml
from minisweagent.agents.interactive import InteractiveAgent

from agents.coding.archiving_agent import archiving
from agents.coding.fork import ForkMismatch, forking, load_step, materialize
from agents.coding.instrumented_model import InstrumentedLitellmModel

ForkedAgent = forking(archiving(InteractiveAgent))


def task_text(instance_message: dict) -> str:
    """The PR description, recovered from the rendered instance message.

    Templates that run later -- the observation and the format-error message --
    are rendered with `StrictUndefined`, so `task` has to be defined even though
    the instance template itself is never re-rendered here.
    """
    content = instance_message.get("content") or ""
    match = re.search(r"<pr_description>\s*(.*?)\s*</pr_description>", content, re.S)
    return match.group(1) if match else content


def run_one(manifest: dict, arm: str, index: int, out: Path, mini: Path, platform: str) -> dict:
    donor = manifest["arms"]["A" if arm == "fresh" else arm]
    step_dir = Path(manifest["runs_dir"]) / donor["archive"]
    archived = load_step(step_dir)
    prefix = archived["messages"]
    if not prefix:
        raise ForkMismatch(f"no archived message log at {step_dir}")
    if arm == "fresh":
        prefix = prefix[:2]
    elif json.dumps(prefix, sort_keys=True) and donor["prefix_messages"] != len(prefix):
        raise ForkMismatch(
            f"arm {arm}: archived prefix is {len(prefix)} messages, "
            f"manifest froze {donor['prefix_messages']}"
        )

    name = f"{arm}_{index}"
    probe = out / f"{name}.probe.jsonl"
    probe.unlink(missing_ok=True)
    env, snapshot = materialize(
        step_dir, manifest["image"],
        {"tracked_diff_hash": donor["tracked_diff_hash"],
         "workspace_diff_hash": donor["workspace_diff_hash"]},
        include_untracked=(arm != "fresh"),
        probe_output=str(probe), timeout=120,
        run_args=["--rm"] + ([f"--platform={platform}"] if platform else []),
    )

    config = yaml.safe_load((mini / "src/minisweagent/config/benchmarks/swebench.yaml").read_text())
    agent_config = dict(config.get("agent", {}))
    agent_config.update({
        # Equal for every continuation in every arm. Donor prefixes differ in
        # length, so leaving the limit where Phase A had it would hand the
        # shorter-prefix arm more remaining steps and confound context with budget.
        "step_limit": manifest["continuation_step_limit"],
        "mode": "yolo",
        "confirm_exit": False,
        "output_path": str(out / f"{name}.json"),
    })
    agent = ForkedAgent(
        InstrumentedLitellmModel(
            model_name="openai/Qwen/Qwen3.6-27B-FP8",
            model_kwargs={"drop_params": True},
            stream=True, attempt_timeout=180, max_attempts=6,
        ),
        env,
        prefix_messages=copy.deepcopy(prefix),
        **agent_config,
    )
    try:
        result = agent.run(task=task_text(prefix[1]))
    finally:
        env.cleanup()
    return {
        "arm": arm, "index": index, "exit_status": result.get("exit_status"),
        "submission_bytes": len(result.get("submission") or ""),
        "start_tracked": snapshot["tracked_diff_hash"],
        "start_workspace": snapshot["workspace_diff_hash"],
        "prefix_messages": len(prefix),
    }


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--manifest", required=True)
    ap.add_argument("--runs-dir", required=True, help="where the Phase A archives live")
    ap.add_argument("--out", required=True)
    ap.add_argument("--mini", required=True)
    ap.add_argument("--platform", default="linux/amd64")
    ap.add_argument("--arms", default="A,B,fresh")
    ap.add_argument("--n", type=int, default=8)
    args = ap.parse_args()

    manifest = json.loads(Path(args.manifest).read_text()) | {"runs_dir": args.runs_dir}
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)

    for arm in args.arms.split(","):
        for index in range(args.n):
            if (out / f"{arm}_{index}.json").exists():
                print(f"skip  {arm}_{index}", flush=True)
                continue
            try:
                row = run_one(manifest, arm, index, out, Path(args.mini), args.platform)
                print(f"{arm}_{index}  {row['exit_status']}  {row['submission_bytes']} B  "
                      f"start {row['start_tracked'][:12]}/{row['start_workspace'][:12]}", flush=True)
            except Exception as exc:  # noqa: BLE001
                print(f"{arm}_{index}  FAILED  {type(exc).__name__}: {exc}", flush=True)


if __name__ == "__main__":
    main()

"""The Phase A gate: a mechanical report, and a manifest only if it all passes.

Phase B compares continuations that differ only in carried context. That
comparison is identified only if three things hold at once, and Phase A data has
to decide the third for itself:

    a shared non-empty source state S           the fork point exists
    different carried contexts C_A, C_B         there is something to vary
    different terminal targets F_A != F_B       there is something to detect

The third is the one no amount of engineering can supply. If both donors end on
the same source state, the primary measure cannot separate the arms however many
continuations are run, and the correct response is to stop and report that --
not to reach for the second-best donor pair, which is choosing a comparison by
how well it separates.

So there are three legal outcomes and the script names which one happened:

    QUALIFIED       rule-selected donors, F_A != F_B, rebuild verified
    UNIDENTIFIABLE  a fork point exists but the donors end alike
    NO FORK POINT   no shared non-empty state among completed runs

The manifest is written only on QUALIFIED. Once continuations start coming back,
a fork point that can still be recomputed is a fork point that can still be
reselected, and "we tried the other shared state" would be indistinguishable in
the record from "we used the one the rule gave us".
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

from experiments.coding.fork_validation import select_donors, shared_state
from experiments.coding.replay import probe_rows

STEP_LIMIT = 250
"""The primary experiment's step limit, unchanged.

It never bound there -- the longest run used 34 of 250 -- and is not being used
as a limit now but as the constant each arm's equal allowance is measured from.
"""


def digest(obj) -> str:
    return hashlib.sha256(json.dumps(obj, sort_keys=True).encode()).hexdigest()


def run_stats(trajectory: dict) -> dict:
    """Wall clock, context peak and reasoning share, from the recorded responses.

    Wall clock is the span of model-call timestamps, which excludes container
    start and is therefore a lower bound; it is here to compare runs with each
    other, not to price the experiment.
    """
    calls = [m.get("extra", {}) for m in trajectory["messages"] if m.get("role") == "assistant"]
    stamps = [c["timestamp"] for c in calls if c.get("timestamp")]
    usages = [c.get("response", {}).get("usage") or {} for c in calls]
    prompts = [u.get("prompt_tokens") or 0 for u in usages]
    reasoning = [(u.get("completion_tokens_details") or {}).get("reasoning_tokens") or 0 for u in usages]
    completion = [u.get("completion_tokens") or 0 for u in usages]
    return {
        "api_calls": len(calls),
        "wall_clock_s": round(max(stamps) - min(stamps), 1) if len(stamps) > 1 else 0.0,
        "context_peak_tokens": max(prompts) if prompts else 0,
        "completion_tokens": sum(completion),
        "reasoning_tokens": sum(reasoning),
    }


def build(runs: Path, task: str, image: str, expect: int) -> dict:
    trajectories = sorted(runs.glob(f"{task}__r*.json"))
    report: dict = {"task": task, "image": image, "runs": {}, "failures": [], "outcome": None}
    if len(trajectories) != expect:
        report["failures"].append(f"expected {expect} Phase A runs, found {len(trajectories)}")

    probes, finals, exits = {}, {}, {}
    for path in trajectories:
        run = path.name.split("__r")[-1].split(".")[0]
        data = json.loads(path.read_text())
        probes[run] = probe_rows(runs / f"{task}__r{run}.probe.jsonl")
        exits[run] = str(data["info"].get("exit_status"))
        finals[run] = probes[run][-1]["tracked_diff_hash"] if probes[run] else None
        archive = runs / f"{task}__r{run}.archive"
        report["runs"][run] = {
            "exit_status": exits[run],
            "steps": len(probes[run]),
            "fork_points": len(list(archive.glob("step_*/messages.json"))) if archive.exists() else 0,
            "submission_bytes": len(data["info"].get("submission") or ""),
            "final_tracked_hash": finals[run],
            **run_stats(data),
        }
        if report["runs"][run]["fork_points"] != len(probes[run]):
            report["failures"].append(
                f"r{run}: {len(probes[run])} probe steps but "
                f"{report['runs'][run]['fork_points']} archived message logs"
            )

    # A run cut short has no final state, so no outcome target: it cannot be a
    # donor. It stays in the report, because censoring is data.
    usable = {run: rows for run, rows in probes.items() if exits[run] == "Submitted"}
    if len(usable) < 2:
        report["outcome"] = "NO FORK POINT"
        report["failures"].append(f"fewer than two completed runs: {exits}")
        return report
    try:
        state, carriers = shared_state(usable)
    except SystemExit as exc:
        report["outcome"] = "NO FORK POINT"
        report["failures"].append(str(exc))
        return report

    donors, reason = select_donors(carriers, {r: finals[r] for r in carriers})
    if not donors:
        report["outcome"] = "UNIDENTIFIABLE"
        report["fork_point"] = {"tracked_diff_hash": state, "first_arrival_step": carriers}
        report["run_finals_at_fork"] = {r: finals[r] for r in carriers}
        report["failures"].append(reason)
        return report
    arms = {}
    for arm, run in donors.items():
        step = carriers[run]
        row = next(r for r in probes[run] if r["step"] == step)
        step_dir = runs / f"{task}__r{run}.archive" / f"step_{step:04d}"
        messages_file = step_dir / "messages.json"
        messages = json.loads(messages_file.read_text())["messages"] if messages_file.exists() else None
        if messages is None:
            report["failures"].append(f"arm {arm}: no archived message log at {step_dir}")
        elif messages[-1].get("role") not in ("tool", "user"):
            report["failures"].append(f"arm {arm}: prefix ends on {messages[-1].get('role')}, not an observation")
        arms[arm] = {
            "run": run,
            "fork_step": step,
            "archive": str(step_dir.relative_to(runs)),
            "tracked_diff_hash": row["tracked_diff_hash"],
            "workspace_diff_hash": row["workspace_diff_hash"],
            "prefix_messages": len(messages) if messages else 0,
            "prefix_digest": digest(messages) if messages else None,
            "prefix_last_role": messages[-1].get("role") if messages else None,
            "final_tracked_hash": finals[run],
            "exit_status": exits[run],
            "total_steps": len(probes[run]),
        }

    report["fork_point"] = {"tracked_diff_hash": state, "first_arrival_step": carriers}
    report["arms"] = arms
    report["continuation_step_limit"] = STEP_LIMIT - max(a["fork_step"] for a in arms.values())
    report["outcome_targets"] = {"F_A": arms["A"]["final_tracked_hash"],
                                 "F_B": arms["B"]["final_tracked_hash"]}

    if arms["A"]["workspace_diff_hash"] == arms["B"]["workspace_diff_hash"]:
        report["failures"].append("donors carry the same workspace; there is nothing to vary")
    if arms["A"]["prefix_digest"] and arms["A"]["prefix_digest"] == arms["B"]["prefix_digest"]:
        report["failures"].append("donors carry the same message prefix; there is nothing to vary")
    return report


def rebuild_check(runs: Path, report: dict, image: str, platform: str) -> None:
    from agents.coding.fork import ForkMismatch, materialize

    run_args = ["--rm"] + ([f"--platform={platform}"] if platform else [])
    for arm, info in report["arms"].items():
        expected = {"tracked_diff_hash": info["tracked_diff_hash"],
                    "workspace_diff_hash": info["workspace_diff_hash"]}
        try:
            env, snapshot = materialize(runs / info["archive"], image, expected,
                                        run_args=run_args, timeout=600)
            env.cleanup()
            info["rebuilt"] = True
        except ForkMismatch as exc:
            info["rebuilt"] = False
            report["failures"].append(f"arm {arm}: {exc}")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--runs", required=True)
    ap.add_argument("--task", default="pytest-dev__pytest-10051")
    ap.add_argument("--image", default="swebench/sweb.eval.x86_64.pytest-dev_1776_pytest-10051:latest")
    ap.add_argument("--manifest", required=True)
    ap.add_argument("--report", help="where the gate report is written, pass or fail")
    ap.add_argument("--expect-runs", type=int, default=5)
    ap.add_argument("--platform", default="")
    ap.add_argument("--skip-rebuild", action="store_true")
    args = ap.parse_args()

    runs = Path(args.runs)
    report = build(runs, args.task, args.image, args.expect_runs)

    print(f"{'run':>4}{'exit':>12}{'steps':>7}{'forks':>7}{'wall(s)':>9}"
          f"{'ctx peak':>10}{'reasoning':>11}{'patch B':>9}  final")
    for run, info in sorted(report["runs"].items()):
        print(f"{run:>4}{info['exit_status']:>12}{info['steps']:>7}{info['fork_points']:>7}"
              f"{info['wall_clock_s']:>9.0f}{info['context_peak_tokens']:>10}"
              f"{info['reasoning_tokens']:>11}{info['submission_bytes']:>9}  "
              f"{str(info['final_tracked_hash'])[:12]}")

    if report.get("arms"):
        state = report["fork_point"]["tracked_diff_hash"]
        print(f"\nshared non-empty S   {state[:16]}   first arrival "
              f"{report['fork_point']['first_arrival_step']}")
        for arm, info in report["arms"].items():
            print(f"  arm {arm}  r{info['run']} @ step {info['fork_step']:>3}  "
                  f"workspace {info['workspace_diff_hash'][:12]}  "
                  f"prefix {info['prefix_messages']:>3} ({info['prefix_last_role']}) "
                  f"{str(info['prefix_digest'])[:12]}  "
                  f"F_{arm} {str(info['final_tracked_hash'])[:12]}")
        same = report["outcome_targets"]["F_A"] == report["outcome_targets"]["F_B"]
        print(f"  F_A == F_B ?  {same}")
        print(f"  continuation step limit  {report['continuation_step_limit']}  (A, B and fresh alike)")
        if not args.skip_rebuild and report["outcome"] is None:
            print("\n[rebuild] fresh containers from the archived fork points")
            rebuild_check(runs, report, args.image, args.platform)
            for arm, info in report["arms"].items():
                print(f"  arm {arm}  rebuilt {info.get('rebuilt')}")

    if report["outcome"] is None:
        report["outcome"] = "QUALIFIED" if not report["failures"] else "FAILED"
    print(f"\n──── {report['outcome']} ────")
    for line in report["failures"]:
        print(f"  - {line}")

    # The report is written whatever the outcome. It is the manifest that is
    # withheld on failure: a stopped experiment still has to leave behind the
    # numbers that stopped it, or the stop is unauditable.
    if args.report:
        Path(args.report).write_text(json.dumps(report, indent=1) + "\n")
        print(f"\nwrote {args.report}")

    if report["outcome"] != "QUALIFIED":
        print("\nno manifest written; Phase B does not start")
        raise SystemExit(1)

    manifest = {
        "preregistration": "paper/INTERVENTION_PREREG_H2.md",
        "phase": "A",
        "task": report["task"],
        "image": report["image"],
        "serving": "inference/configs/model_h2.yaml",
        "model": {"id": "Qwen/Qwen3.6-27B-FP8",
                  "revision": "e89b16ebf1988b3d6befa7de50abc2d76f26eb09",
                  "max_model_len": 131072},
        "fork_point": report["fork_point"],
        "runs": report["runs"],
        "arms": report["arms"],
        "continuation_step_limit": report["continuation_step_limit"],
        "outcome_targets": report["outcome_targets"],
        "arms_planned": ["A", "B", "fresh"],
        "continuations_per_arm": 8,
    }
    Path(args.manifest).write_text(json.dumps(manifest, indent=1) + "\n")
    print(f"\nwrote {args.manifest}")


if __name__ == "__main__":
    main()

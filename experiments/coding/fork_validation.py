"""Zero-LLM gate: does a fork reproduce the state it claims to fork from?

Phase B of the H2 pre-registration compares continuations that differ only in
carried context. That comparison is worth nothing if the containers they start
in are not actually the same on tracked source, or not actually different on the
arm's own workspace. Both are mechanical facts, both are checkable without a
model, and both are checked here before any GPU is rented.

Four things must hold, and all four are failures if they do not:

    replay      re-executing a donor's recorded commands reproduces the
                fingerprints the primary experiment recorded for it
    identity    the two arms' rebuilt containers agree on tracked source
    difference  they disagree on workspace, each matching its own donor
    context     each arm has a coherent message prefix, ending on an
                observation, and the two prefixes are not the same

The third is the one that is easy to forget. A rebuild that restores source and
quietly drops the scratch files would look correct on the primary fingerprint
and would have silently turned the experiment into a different one.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

from agents.coding.fork import ForkMismatch, load_step, materialize
from experiments.coding.replay import probe_rows, replay

EMPTY_DIFF = hashlib.sha256(b"").hexdigest()


def shared_state(probes: dict[str, list[dict]]) -> tuple[str, dict[str, int]]:
    """The fork point, by the rule fixed in the pre-registration.

    Non-empty, held by the most runs, and among ties reached at the smallest
    maximum step index -- earliest in the sense that every run holding it has
    got there.
    """
    held = {
        run: {r["tracked_diff_hash"]: r["step"] for r in reversed(rows)
              if r.get("tracked_diff_hash") and r["tracked_diff_hash"] != EMPTY_DIFF}
        for run, rows in probes.items()
    }
    best = None
    for state in set().union(*[set(h) for h in held.values()]):
        carriers = {run: h[state] for run, h in held.items() if state in h}
        if len(carriers) < 2:
            continue
        key = (-len(carriers), max(carriers.values()))
        if best is None or key < best[0]:
            best = (key, state, carriers)
    if best is None:
        raise SystemExit("no tracked state is held by two or more runs; H2 is not testable here")
    return best[1], best[2]


def select_donors(carriers: dict[str, int], finals: dict[str, str]) -> tuple[dict[str, str], str | None]:
    """The donor pair, under amendment H2.1. Returns ({A, B}, reason-if-none).

    Eligibility is a property of the *pair*, not of a run:

        both completed, both carry S, and their final tracked states differ.

    The third condition is what H2.1 adds, and it is an estimand eligibility
    condition rather than a finding. The primary contrast is
    `P(F_A | C_A) - P(F_A | C_B)`; if `F_A == F_B` that expression does not
    distinguish "context carried the agent back to A's repair" from "context
    carried it back to B's repair", because they are the same repair. The
    contrast is undefined, not zero.

    Among eligible pairs the tie-break is the original outcome-independent one,
    made total: the widest spread in first-arrival step -- the earliest arrival
    against the latest -- then the earliest A, then run id. Nothing in the
    tie-break reads a final state; eligibility has already done the only reading
    that H2.1 permits.

    The fork point S itself is still chosen by the unamended rule. Conditioning
    S on yielding an eligible pair would be a second selection, and the
    conservative reading is that a batch whose S has no eligible pair has failed,
    not that another S should be tried.
    """
    eligible = [
        (x, y) for i, x in enumerate(sorted(carriers)) for y in sorted(carriers)[i + 1:]
        if finals.get(x) and finals.get(y) and finals[x] != finals[y]
    ]
    if not eligible:
        return {}, ("every pair of runs holding S ends on the same source state; "
                    "the H2b contrast is undefined, not zero")
    best = min(
        eligible,
        key=lambda pair: (
            -abs(carriers[pair[1]] - carriers[pair[0]]),
            min(carriers[pair[0]], carriers[pair[1]]),
            sorted(pair),
        ),
    )
    early, late = sorted(best, key=lambda run: (carriers[run], run))
    return {"A": early, "B": late}, None


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--runs", required=True, help="directory of *__r*.json / *.probe.jsonl")
    ap.add_argument("--task", default="pytest-dev__pytest-10051")
    ap.add_argument("--image", default="swebench/sweb.eval.x86_64.pytest-dev_1776_pytest-10051:latest")
    ap.add_argument("--work", required=True, help="directory for replay archives")
    ap.add_argument("--platform", default="linux/amd64")
    ap.add_argument(
        "--no-replay", action="store_true",
        help="the runs already carry their own archive; rebuild from it directly",
    )
    args = ap.parse_args()

    runs = Path(args.runs)
    probes = {
        path.name.split("__r")[-1].split(".")[0]: probe_rows(path)
        for path in sorted(runs.glob(f"{args.task}__r*.probe.jsonl"))
    }
    state, carriers = shared_state(probes)
    finals = {run: rows[-1]["tracked_diff_hash"] for run, rows in probes.items() if rows}
    donors, reason = select_donors(carriers, finals)
    if not donors:
        raise SystemExit(reason)
    print(f"fork point {state[:12]}  held by {carriers}")
    print(f"donor A = r{donors['A']} @ step {carriers[donors['A']]}   "
          f"donor B = r{donors['B']} @ step {carriers[donors['B']]}\n")

    run_args = ["--rm"] + ([f"--platform={args.platform}"] if args.platform else [])
    work = Path(args.work)
    failures: list[str] = []
    arms: dict[str, dict] = {}

    for arm, run in donors.items():
        step = carriers[run]
        if args.no_replay:
            # A run collected with the archive on already holds the bytes. Replay
            # is the bridge for trajectories recorded before the archive existed,
            # and re-running commands that were already recorded would only add a
            # way for the two to disagree.
            step_dir = runs / f"{args.task}__r{run}.archive" / f"step_{step:04d}"
            if not step_dir.exists():
                failures.append(f"arm {arm}: no archive at {step_dir}")
        else:
            archive = work / f"{args.task}__r{run}"
            print(f"[replay] arm {arm}: r{run} steps 1..{step}")
            out = replay(
                runs / f"{args.task}__r{run}.json",
                runs / f"{args.task}__r{run}.probe.jsonl",
                args.image, archive, step, run_args=run_args,
            )
            mismatched = [r["step"] for r in out["steps"] if not r["tracked_match"]]
            if mismatched:
                failures.append(f"arm {arm}: replay diverged from the record at steps {mismatched}")
            if not out["steps"][-1]["workspace_match"]:
                failures.append(f"arm {arm}: replay reproduced source but not workspace at step {step}")
            step_dir = archive / f"step_{step:04d}"
        expected = [r for r in probe_rows(runs / f"{args.task}__r{run}.probe.jsonl") if r["step"] == step][0]
        arms[arm] = {"run": run, "step": step, "dir": step_dir, "expected": expected}

    for arm, info in arms.items():
        if not Path(info["dir"]).exists():
            continue
        print(f"[rebuild] arm {arm}: fresh container from {info['dir']}")
        try:
            env, snapshot = materialize(
                info["dir"], args.image, info["expected"], run_args=run_args, timeout=600,
            )
        except ForkMismatch as exc:
            failures.append(f"arm {arm}: {exc}")
            continue
        env.cleanup()
        info["rebuilt"] = snapshot
        archived = load_step(info["dir"])
        messages = archived["messages"]
        if not messages:
            failures.append(f"arm {arm}: no coherent message prefix archived")
        elif messages[-1].get("role") not in ("tool", "user"):
            failures.append(f"arm {arm}: prefix ends on {messages[-1].get('role')}, not an observation")
        info["messages"] = messages

    if "rebuilt" in arms.get("A", {}) and "rebuilt" in arms.get("B", {}):
        a, b = arms["A"], arms["B"]
        if a["rebuilt"]["tracked_diff_hash"] != b["rebuilt"]["tracked_diff_hash"]:
            failures.append("arms disagree on tracked source after rebuild; there is no controlled state")
        if a["rebuilt"]["tracked_diff_hash"] != state:
            failures.append("rebuilt source is not the fork point the rule selected")
        if a["rebuilt"]["workspace_diff_hash"] == b["rebuilt"]["workspace_diff_hash"]:
            failures.append("arms agree on workspace; the treatment was not restored")
        if a.get("messages") and b.get("messages") and a["messages"] == b["messages"]:
            failures.append("arms carry identical message prefixes; there is nothing to vary")

    print("\n──── result ────")
    for arm, info in arms.items():
        rebuilt = info.get("rebuilt", {})
        print(f"  arm {arm}  r{info['run']} @ step {info['step']}  "
              f"tracked {rebuilt.get('tracked_diff_hash', '?')[:12]}  "
              f"workspace {rebuilt.get('workspace_diff_hash', '?')[:12]}  "
              f"prefix {len(info.get('messages') or [])} messages")
    if failures:
        print("\nFAIL")
        for line in failures:
            print(f"  - {line}")
        sys.exit(1)
    print("\nPASS  source identical across arms, workspace and context arm-specific")
    (work / "validation.json").write_text(json.dumps(
        {"state": state, "carriers": carriers,
         "arms": {k: {"run": v["run"], "step": v["step"], "dir": str(v["dir"]),
                      "rebuilt": v.get("rebuilt"), "prefix_messages": len(v.get("messages") or [])}
                  for k, v in arms.items()}}, indent=1))


if __name__ == "__main__":
    main()

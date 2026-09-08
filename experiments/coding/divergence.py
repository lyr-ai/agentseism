"""Divergence, reconvergence and persistence from `coding/1` trajectories.

Reconvergence excludes the empty state, and that exclusion is the correction.
The first analysis classified 17 of 25 pairs as anomalous -- reconverged yet
ending with different patches -- which the pre-registration declares a
measurement bug rather than a finding. It was: the only state two runs shared was
`sha256("")`, the hash of an empty diff, held by every run before it modifies
anything. Divergence in command signatures typically appears at step 0 or 1 while
the repository stays untouched for many steps, so every pair "reconverged" on
having changed nothing yet.

Two runs that have not yet edited the repository have not converged on a
solution; they have not started. Reconvergence now requires a shared **non-empty**
source state after the divergence point.
"""

from __future__ import annotations

import argparse
import collections
import glob
import hashlib
import itertools
import json
import os
import re

EMPTY_DIFF = hashlib.sha256(b"").hexdigest()
"""`git diff HEAD` on a clean tree is empty, and every run begins there."""


def signature(cmd: str) -> str:
    segs = [s.strip() for s in re.split(r"&&|\|\||;", cmd or "") if s.strip()]
    segs = [s for s in segs if not s.startswith("cd ")] or segs
    if not segs:
        return ""
    toks = segs[0].split()
    exe = toks[0] if toks else ""
    marks = []
    if re.search(r"<<\s*'?\w+'?", segs[0]):
        marks.append("heredoc")
    if re.search(r"(?<![0-9])>>", segs[0]):
        marks.append("append")
    elif re.search(r"(?<![0-9])>(?!&)", segs[0]):
        marks.append("redirect")
    for t in toks[1:]:
        if re.fullmatch(r"--?[A-Za-z][\w-]*", t):
            marks.append(t)
    return exe + (":" + ",".join(dict.fromkeys(marks)) if marks else "")


def load(directory: str) -> dict:
    runs: dict = collections.defaultdict(dict)
    for path in sorted(glob.glob(f"{directory}/*__r*.json")):
        task, idx = os.path.basename(path).replace(".json", "").rsplit("__r", 1)
        info = json.load(open(path))["info"]
        probe = path.replace(".json", ".probe.jsonl")
        steps = [json.loads(l) for l in open(probe)] if os.path.exists(probe) else []
        runs[task][int(idx)] = {
            "exit": str(info.get("exit_status") or "-"),
            "patch": info.get("submission") or "",
            "signatures": [signature(s.get("command", "")) for s in steps],
            "states": [s.get("tracked_diff_hash") for s in steps],
        }
    return runs


def classify(a: dict, b: dict) -> dict:
    """One pair, as three independent facts rather than one label.

        D  the command-signature sequences ever differ
        R  after D, both runs hold the same non-empty tracked source state
        F  the final tracked source states are equal

    Kept separate because collapsing them lost a real topology. The
    pre-registered scheme had two outcomes, absorbed and persistent, and
    implicitly assumed reconvergence is terminal. Five pairs here are D=1, R=1,
    F=0: they meet on a real state and part again. That is not an anomaly, it is
    a third shape the vocabulary could not express.

    Two persistence measures are reported, and the pre-registered one is kept.

        F_v1   the submitted patch strings are equal   (pre-registered)
        F_v2   the final tracked_diff_hash values are equal

    They disagree, and the disagreement is a construct mismatch visible without
    reference to the hypothesis. `submission` is a string the agent produced and
    can carry files that are not tracked source: sphinx r2 submitted 19,439
    bytes against a 720-byte source diff, the extra 18kB being its own scratch
    file, while all three runs of that task ended on the identical
    `tracked_diff_hash` with byte-identical changes to the one source file. If
    the question is whether two runs reached the same source-code solution,
    counting r2 as a different solution is a measurement error.
    """
    divergence = next(
        (i for i, (x, y) in enumerate(zip(a["signatures"], b["signatures"])) if x != y),
        None,
    )
    if divergence is None and len(a["signatures"]) != len(b["signatures"]):
        divergence = min(len(a["signatures"]), len(b["signatures"]))

    final_a = a["states"][-1] if a["states"] else None
    final_b = b["states"][-1] if b["states"] else None
    f_v1 = a["patch"] == b["patch"]
    f_v2 = bool(final_a) and final_a == final_b

    if divergence is None:
        return {"D": False, "R": None, "F_v1": f_v1, "F_v2": f_v2,
                "divergence": None, "topology": "identical"}

    def real(run):
        return {s for s in run["states"][divergence:] if s and s != EMPTY_DIFF}

    r = bool(real(a) & real(b))
    if r and f_v2:
        topology = "absorbed"
    elif not r and not f_v2:
        topology = "persistent"
    elif r and not f_v2:
        topology = "re-divergence"
    else:
        # Same final state without ever sharing one is only possible if both
        # ended empty, i.e. neither changed any source.
        topology = "no-source-change" if not final_a or final_a == EMPTY_DIFF else "unexplained"
    return {"D": True, "R": r, "F_v1": f_v1, "F_v2": f_v2,
            "divergence": divergence, "topology": topology}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dir", required=True)
    args = ap.parse_args()

    runs = load(args.dir)
    print(f"{'task':<30}{'pair':>6}{'div@':>6}{'D':>4}{'R':>6}{'F_v1':>6}{'F_v2':>6}  topology")
    totals = collections.Counter()
    v1_totals = collections.Counter()
    per_task: dict = {}
    disagree = 0
    for task in sorted(runs):
        usable = [r for r in sorted(runs[task]) if runs[task][r]["exit"] == "Submitted"]
        if len(usable) < 2:
            print(f"{task:<30}  no usable pair ({len(usable)}/3 submitted)")
            per_task[task] = None
            continue
        labels = []
        for x, y in itertools.combinations(usable, 2):
            r = classify(runs[task][x], runs[task][y])
            labels.append(r["topology"])
            totals[r["topology"]] += 1
            # The pre-registered scheme, kept so the conclusion can be checked
            # against it: absorbed iff reconverged and the patch strings match.
            v1_totals["absorbed" if r["R"] and r["F_v1"]
                      else "persistent" if not r["R"] and not r["F_v1"]
                      else "unresolved"] += 1
            disagree += r["F_v1"] != r["F_v2"]
            print(f"{task:<30}{f'{x}-{y}':>6}{str(r['divergence']):>6}"
                  f"{str(r['D'])[0]:>4}{str(r['R']):>6}{str(r['F_v1'])[0]:>6}"
                  f"{str(r['F_v2'])[0]:>6}  {r['topology']}")
        per_task[task] = dict(collections.Counter(labels))

    print("\n──── per task ────")
    for task, counts in sorted(per_task.items()):
        print(f"  {task:<30} {counts if counts else 'no data'}")
    print(f"\nv2 (canonical source state): {dict(totals)}")
    print(f"v1 (pre-registered, submission string): {dict(v1_totals)}")
    print(f"pairs where F_v1 and F_v2 disagree: {disagree}")


if __name__ == "__main__":
    main()

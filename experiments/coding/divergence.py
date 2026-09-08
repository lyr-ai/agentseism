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
    divergence = next(
        (i for i, (x, y) in enumerate(zip(a["signatures"], b["signatures"])) if x != y),
        None,
    )
    if divergence is None and len(a["signatures"]) != len(b["signatures"]):
        divergence = min(len(a["signatures"]), len(b["signatures"]))

    persistent = a["patch"] != b["patch"]
    if divergence is None:
        return {"divergence": None, "reconverged": None, "persistent": persistent,
                "label": "identical"}

    def real(run):
        return {s for s in run["states"][divergence:] if s and s != EMPTY_DIFF}

    reconverged = bool(real(a) & real(b))
    label = ("absorbed" if reconverged and not persistent
             else "persistent" if not reconverged and persistent
             else "anomalous")
    return {"divergence": divergence, "reconverged": reconverged,
            "persistent": persistent, "label": label}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dir", required=True)
    args = ap.parse_args()

    runs = load(args.dir)
    print(f"{'task':<32}{'pair':>6}{'diverge@':>10}{'reconv':>8}{'persist':>9}  label")
    totals = collections.Counter()
    per_task: dict = {}
    for task in sorted(runs):
        usable = [r for r in sorted(runs[task]) if runs[task][r]["exit"] == "Submitted"]
        if len(usable) < 2:
            print(f"{task:<32}  no usable pair ({len(usable)}/3 submitted)")
            per_task[task] = None
            continue
        labels = []
        for x, y in itertools.combinations(usable, 2):
            r = classify(runs[task][x], runs[task][y])
            labels.append(r["label"])
            totals[r["label"]] += 1
            print(f"{task:<32}{f'{x}-{y}':>6}{str(r['divergence']):>10}"
                  f"{str(r['reconverged']):>8}{str(r['persistent']):>9}  {r['label']}")
        per_task[task] = dict(collections.Counter(labels))

    print("\n──── per task ────")
    for task, counts in sorted(per_task.items()):
        print(f"  {task:<32} {counts if counts else 'no data'}")
    print("\ntotals:", dict(totals))


if __name__ == "__main__":
    main()

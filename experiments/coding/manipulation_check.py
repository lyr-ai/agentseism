"""The pre-registered validity gate: is the fork faithful?

From `paper/INTERVENTION_PREREG_H2.md`:

    At temperature 0 a faithful fork should partly reproduce the donor's own
    continuation. Gate: at least one of the 8 arm-A continuations reproduces
    donor A's next 3 command signatures, and likewise for B. If both arms fail
    this, the fork is not faithful -- most likely the container reconstruction --
    and the experiment is void and reported as void, not reinterpreted. Passing
    on one arm only is reported and the run continues.

This decides what the primary result means. Fifteen continuations produced
fifteen distinct final states and none matched either donor, which is either a
system whose repair phase is close to maximally stochastic, or a fork that never
really put the agent where it claimed to. The gate separates those two readings,
and it was written down before either was visible.
"""

from __future__ import annotations

import argparse
import glob
import json
import os
import re
from pathlib import Path


def signature(cmd: str) -> str:
    """Command signature, identical to experiments/coding/divergence.py."""
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


def probe(path) -> list[dict]:
    return [json.loads(l) for l in open(path)] if os.path.exists(path) else []


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--phase-a", required=True)
    ap.add_argument("--phase-b", required=True)
    ap.add_argument("--manifest", required=True)
    ap.add_argument("--k", type=int, default=3)
    args = ap.parse_args()

    manifest = json.loads(Path(args.manifest).read_text())
    task = manifest["task"]
    verdict = {}
    for arm in ("A", "B"):
        donor = manifest["arms"][arm]
        rows = probe(Path(args.phase_a) / f"{task}__r{donor['run']}.probe.jsonl")
        fork = donor["fork_step"]
        # The donor's own next k commands, the ones a faithful replay of its
        # context from this state has a chance of repeating.
        target = [signature(r["command"]) for r in rows if r["step"] > fork][: args.k]
        print(f"\n── arm {arm}: donor r{donor['run']} after step {fork}")
        print(f"   donor next {args.k}: {target}")
        hits = 0
        for path in sorted(glob.glob(f"{args.phase_b}/{arm}_*.probe.jsonl")):
            got = [signature(r["command"]) for r in probe(path)][: args.k]
            match = got == target
            hits += match
            prefix_len = sum(1 for x, y in zip(got, target) if x == y)
            print(f"   {os.path.basename(path)[:-12]:<6} {got}"
                  f"   {'MATCH' if match else f'first {prefix_len}/{args.k}'}")
        verdict[arm] = hits
        print(f"   arm {arm}: {hits} of {len(glob.glob(f'{args.phase_b}/{arm}_*.probe.jsonl'))} reproduce all {args.k}")

    print("\n──── gate ────")
    if verdict.get("A", 0) == 0 and verdict.get("B", 0) == 0:
        print("  VOID — neither arm reproduces its donor's next commands even once.")
        print("  The pre-registration says this is a fork that did not put the agent")
        print("  where it claimed to, and that the experiment is reported as void")
        print("  rather than reinterpreted.")
        raise SystemExit(1)
    if 0 in verdict.values():
        failed = [k for k, v in verdict.items() if v == 0]
        print(f"  PASS on one arm only — arm(s) {failed} never reproduce the donor's")
        print("  next commands. Recorded; the pre-registration lets the run continue.")
    else:
        print("  PASS — both arms reproduce their donor's next commands at least once,")
        print("  so the fork puts the agent where it claims to and the primary null")
        print("  is a fact about the system rather than about the apparatus.")


if __name__ == "__main__":
    main()

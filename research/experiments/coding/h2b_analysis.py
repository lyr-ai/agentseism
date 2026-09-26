"""H2b: does carried context bias a continuation toward its own donor's repair?

The three layers were declared before any outcome was read -- the first two in
`paper/INTERVENTION_PREREG_H2.md`, the third in
`paper/PHASE_B_TRANSPORT_STOP_RULE.md` -- and they are computed here in that
order, in one pass, so that no layer is inspected before the next is defined.

    primary       every usable continuation in its assigned arm
    sensitivity   split by whether the run contained a transport retry
    secondary     hunk locations rather than exact state equality

The primary statistic is the pre-registered one:

    P(F_c == F_A | arm A) − P(F_c == F_A | arm B),  predicted > 0

with the symmetric statistic on F_B computed alongside. Both were declared part
of the primary claim and both must point the same way for H2b to be supported.

`B_1` is excluded: thirteen calls, no exit status, no recorded exception, and the
runner's stdout filter destroyed whatever would have explained it. It is not
rerun, because replacing a missing observation after the rest of the data exists
is a new degree of freedom, and it is not counted, because nothing is known about
why it stopped.
"""

from __future__ import annotations

import argparse
import collections
import glob
import json
import math
import os
import re
from pathlib import Path

EXCLUDED = {"B_1": "stopped after 13 calls with no exit status or recorded exception"}


def fisher_one_sided(a: int, b: int, c: int, d: int) -> float:
    """P(as extreme or more, in the predicted direction) for the 2x2 [[a,b],[c,d]].

    Rows are arms, columns are hit and miss. The predicted direction is "arm A
    hits more often", so the tail sums over tables with at least `a` hits in arm
    A, holding both margins fixed.
    """
    n = a + b + c + d
    row1, col1 = a + b, a + c
    total = math.comb(n, col1)
    return sum(
        math.comb(row1, k) * math.comb(n - row1, col1 - k)
        for k in range(a, min(row1, col1) + 1)
    ) / total if total else 1.0


def hunks(patch: str) -> frozenset:
    """(file, hunk start, hunk length) triples, from a unified diff.

    The pre-registration defines this on the final diff. Phase B recorded
    fingerprints and not diff bytes, so it is computed from the submitted patch
    for continuations *and* for donors alike -- the same construct on both sides
    of every comparison, which is what the comparison needs, even though it is
    not the same construct the primary measure uses. The primary experiment
    already showed these two can disagree: a submission may carry files that are
    not tracked source.
    """
    out, current = [], None
    for line in (patch or "").splitlines():
        if line.startswith("+++ b/"):
            current = line[6:].strip()
        elif line.startswith("@@") and current:
            match = re.search(r"\+(\d+)(?:,(\d+))?", line)
            if match:
                out.append((current, int(match.group(1)), int(match.group(2) or 1)))
    return frozenset(out)


def load(directory: str, manifest: dict) -> list[dict]:
    rows = []
    for path in sorted(glob.glob(f"{directory}/*.json")):
        name = os.path.basename(path)[:-5]
        arm = name.rsplit("_", 1)[0]
        if arm not in ("A", "B", "fresh"):
            continue
        data = json.loads(Path(path).read_text())
        probe = path.replace(".json", ".probe.jsonl")
        steps = [json.loads(l) for l in open(probe)] if os.path.exists(probe) else []
        prefix = 2 if arm == "fresh" else manifest["arms"][arm]["prefix_messages"]
        own = [m.get("extra", {}) for m in data["messages"][prefix:] if m.get("role") == "assistant"]
        rows.append({
            "run": name, "arm": arm,
            "exit_status": str(data["info"].get("exit_status") or ""),
            "final": steps[-1]["tracked_diff_hash"] if steps else None,
            "submission": data["info"].get("submission") or "",
            "calls": len(own),
            "retried": sum(1 for c in own if c.get("transport_retried")),
            "excluded": EXCLUDED.get(name),
        })
    return rows


def contingency(rows: list[dict], hit) -> tuple[int, int, int, int]:
    a = sum(1 for r in rows if r["arm"] == "A" and hit(r))
    b = sum(1 for r in rows if r["arm"] == "A" and not hit(r))
    c = sum(1 for r in rows if r["arm"] == "B" and hit(r))
    d = sum(1 for r in rows if r["arm"] == "B" and not hit(r))
    return a, b, c, d


def report(rows: list[dict], hit, label: str) -> dict:
    a, b, c, d = contingency(rows, hit)
    pa = a / (a + b) if a + b else float("nan")
    pb = c / (c + d) if c + d else float("nan")
    p = fisher_one_sided(a, b, c, d)
    print(f"  {label:<34} A {a}/{a+b} = {pa:.3f}   B {c}/{c+d} = {pb:.3f}   "
          f"diff {pa - pb:+.3f}   Fisher one-sided p = {p:.4f}")
    return {"label": label, "a": a, "b": b, "c": c, "d": d,
            "p_A": pa, "p_B": pb, "effect": pa - pb, "fisher_p": p}


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--runs", required=True)
    ap.add_argument("--manifest", required=True)
    ap.add_argument("--out")
    args = ap.parse_args()

    manifest = json.loads(Path(args.manifest).read_text())
    F_A = manifest["outcome_targets"]["F_A"]
    F_B = manifest["outcome_targets"]["F_B"]
    donor_hunks = {}
    for arm in ("A", "B"):
        donor = manifest["arms"][arm]
        donor_hunks[arm] = None  # filled below if a donor submission is available

    rows = load(args.runs, manifest)
    usable = [r for r in rows if r["exit_status"] == "Submitted" and not r["excluded"]]

    print("──── the table ────")
    counts = collections.Counter()
    for r in rows:
        counts[(r["arm"], "collected")] += 1
        if r in usable:
            counts[(r["arm"], "usable")] += 1
    for arm in ("A", "B", "fresh"):
        n_all, n_ok = counts[(arm, "collected")], counts[(arm, "usable")]
        note = "  (not collected: stop rule)" if arm == "fresh" and not n_all else ""
        print(f"  arm {arm:<6} collected {n_all}   usable {n_ok}{note}")
    for r in rows:
        if r["excluded"]:
            print(f"  excluded {r['run']}: {r['excluded']}")

    print("\n  final state distribution")
    for arm in ("A", "B"):
        dist = collections.Counter(r["final"][:12] if r["final"] else "none"
                                   for r in usable if r["arm"] == arm)
        print(f"    arm {arm}: {dict(dist)}")
    print(f"    F_A = {F_A[:12]}    F_B = {F_B[:12]}")

    results = {}
    print("\n──── layer 1: primary, all usable runs ────")
    results["primary_FA"] = report(usable, lambda r: r["final"] == F_A, "match F_A (predicted A > B)")
    results["primary_FB"] = report(usable, lambda r: r["final"] == F_B, "match F_B (predicted A < B)")
    other = [r for r in usable if r["final"] not in (F_A, F_B)]
    print(f"  neither donor's final state: {len(other)} of {len(usable)}")

    print("\n──── layer 2: transport sensitivity ────")
    clean = [r for r in usable if r["retried"] == 0]
    dirty = [r for r in usable if r["retried"] > 0]
    print(f"  retry-free {len(clean)} ({sum(1 for r in clean if r['arm']=='A')} A, "
          f"{sum(1 for r in clean if r['arm']=='B')} B)   "
          f"retried {len(dirty)} ({sum(1 for r in dirty if r['arm']=='A')} A, "
          f"{sum(1 for r in dirty if r['arm']=='B')} B)")
    if clean:
        results["clean_FA"] = report(clean, lambda r: r["final"] == F_A, "retry-free: match F_A")
        results["clean_FB"] = report(clean, lambda r: r["final"] == F_B, "retry-free: match F_B")
    if dirty:
        results["dirty_FA"] = report(dirty, lambda r: r["final"] == F_A, "retried only: match F_A")

    print("\n──── layer 3: secondary, hunk locations ────")
    donor_patch = {arm: manifest["arms"][arm].get("submission") for arm in ("A", "B")}
    if not all(donor_patch.values()):
        # The manifest froze hashes, not patches. Recover each donor's submitted
        # patch from its own Phase A1 trajectory, which is the run the target
        # state came from.
        for arm in ("A", "B"):
            run = manifest["arms"][arm]["run"]
            path = Path(args.runs).parent / "h2_phase_a1" / f"{manifest['task']}__r{run}.json"
            donor_patch[arm] = json.loads(path.read_text())["info"].get("submission") or ""
    hA, hB = hunks(donor_patch["A"]), hunks(donor_patch["B"])
    print(f"  donor A hunks {sorted(hA)}")
    print(f"  donor B hunks {sorted(hB)}")
    if hA == hB:
        print("  donors share hunk locations: the secondary measure cannot separate the arms")
    else:
        results["secondary_FA"] = report(usable, lambda r: hunks(r["submission"]) == hA,
                                         "hunks match donor A")
        results["secondary_FB"] = report(usable, lambda r: hunks(r["submission"]) == hB,
                                         "hunks match donor B")

    if args.out:
        Path(args.out).write_text(json.dumps(
            {"rows": rows, "results": results, "F_A": F_A, "F_B": F_B}, indent=1) + "\n")
        print(f"\nwrote {args.out}")


if __name__ == "__main__":
    main()

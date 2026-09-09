"""Trajectory agreement as a function of horizon, from a reconstructed state.

Exploratory on pytest by construction: this is the batch that generated H3, and
only `h = 3` on signatures was pre-registered, as the H2 manipulation check.
Everything else here exists to find out what the measurement looks like, whether
it has any dynamic range, and whether the bookkeeping is right -- before flask is
collected under `paper/PREREG_H3_REPRODUCIBILITY_DECAY.md`.

Two curves, three granularities, two views.

    pointwise(h)   agreement at step h alone; can fall and recover
    survival(h)    agreement at every step 1..h; monotone by construction

Both, because the 30-run experiment found trajectories that diverge, meet again
and part. `survival` cannot represent that and would report a pair as lost from
its first disagreement onward.

    signature   the coding/1 command signature -- `sed -n '1,5p' f` -> `sed:-n`
    command     the exact command string
    state       tracked_diff_hash after the action

Agreement is not one thing. Two runs that both ran `sed -n` on different line
ranges agree on signature and disagree on command, and the existing 14/16 result
is on signatures alone.

    censored    transport-censored: each continuation ends at its first retried
                step, because that step drew from the model more than once and
                everything after it inherits the extra draw
    raw         no transport censoring; diagnostic only, to see how much the
                contamination moves the curve. It cannot be used to rescue a
                result, and is printed second for that reason.

Every point carries `n` -- the continuations still at risk. A survival of 0.5
over two remaining trajectories says nothing, and the denominator is the only
thing that shows it.
"""

from __future__ import annotations

import argparse
import json
import glob
import os
import re
from pathlib import Path


def signature(cmd: str) -> str:
    """Identical to experiments/coding/divergence.py."""
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


GRAINS = {
    "signature": lambda row: signature(row.get("command", "")),
    "command": lambda row: row.get("command", ""),
    "state": lambda row: row.get("tracked_diff_hash", ""),
}


def probe(path) -> list[dict]:
    return [json.loads(l) for l in open(path)] if os.path.exists(path) else []


def first_retry_step(trajectory: dict, prefix: int) -> int | None:
    """The continuation's own step index at which a step was sampled twice.

    Retries are recorded per model call, and a call that produced no action --
    a format error -- advances the call counter without advancing the
    environment. So the mapping is rebuilt here by walking the run's own
    messages and counting only those that carried an action.
    """
    step = 0
    for message in trajectory["messages"][prefix:]:
        if message.get("role") != "assistant":
            continue
        extra = message.get("extra", {})
        if not (extra.get("actions") or []):
            continue
        step += 1
        if extra.get("transport_retried"):
            return step
    return None


def curves(runs_b: str, runs_a: str, manifest: dict, censor: bool) -> dict:
    task = manifest["task"]
    out: dict = {}
    for arm in ("A", "B"):
        donor = manifest["arms"][arm]
        donor_rows = probe(Path(runs_a) / f"{task}__r{donor['run']}.probe.jsonl")
        fork = donor["fork_step"]
        after = [r for r in donor_rows if r["step"] > fork]

        series = []
        for path in sorted(glob.glob(f"{runs_b}/{arm}_*.probe.jsonl")):
            name = os.path.basename(path)[:-12]
            trajectory = json.loads(Path(f"{runs_b}/{name}.json").read_text())
            if str(trajectory["info"].get("exit_status")) != "Submitted":
                continue
            rows = probe(path)
            limit = len(rows)
            if censor:
                cut = first_retry_step(trajectory, donor["prefix_messages"])
                if cut is not None:
                    limit = min(limit, cut - 1)
            series.append({"name": name, "rows": rows[:limit]})

        arm_out = {}
        for grain, project in GRAINS.items():
            points = []
            for h in range(1, len(after) + 1):
                at_risk = [s for s in series if len(s["rows"]) >= h]
                if not at_risk:
                    break
                target = project(after[h - 1])
                match = [project(s["rows"][h - 1]) == target for s in at_risk]
                alive = [s for s in at_risk
                         if all(project(s["rows"][i]) == project(after[i]) for i in range(h))]
                points.append({
                    "h": h, "n": len(at_risk), "matches": sum(match),
                    "pointwise": sum(match) / len(at_risk),
                    "survival": len(alive) / len(at_risk),
                    "censored_by_h": len(series) - len(at_risk),
                })
            arm_out[grain] = points
        out[arm] = {"n_continuations": len(series), "points": arm_out,
                    "donor_steps_after_fork": len(after)}
    return out


def show(label: str, data: dict) -> None:
    print(f"\n════ {label} ════")
    for arm, info in data.items():
        print(f"\n  arm {arm}: {info['n_continuations']} continuations, "
              f"donor has {info['donor_steps_after_fork']} steps after the fork")
        print(f"    {'h':>3}{'n':>5}   " + "   ".join(f"{g:^17}" for g in GRAINS))
        print(f"    {'':>3}{'':>5}   " + "   ".join(f"{'point  surv':^17}" for _ in GRAINS))
        horizons = sorted({p["h"] for g in info["points"].values() for p in g})
        for h in horizons:
            cells, n = [], None
            for grain in GRAINS:
                point = next((p for p in info["points"][grain] if p["h"] == h), None)
                if point is None:
                    cells.append(f"{'-':^17}")
                else:
                    n = point["n"]
                    cells.append(f"{point['pointwise']:^7.2f}{point['survival']:^10.2f}")
            flag = "" if (n or 0) >= max(1, info["n_continuations"] / 2) else "  (thin)"
            print(f"    {h:>3}{n or 0:>5}   " + "   ".join(cells) + flag)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--phase-a", required=True)
    ap.add_argument("--phase-b", required=True)
    ap.add_argument("--manifest", required=True)
    ap.add_argument("--out")
    args = ap.parse_args()

    manifest = json.loads(Path(args.manifest).read_text())
    censored = curves(args.phase_b, args.phase_a, manifest, censor=True)
    raw = curves(args.phase_b, args.phase_a, manifest, censor=False)

    print("EXPLORATORY. Only h=3 on signatures was pre-registered (the H2")
    print("manipulation check). Nothing here selects anything about flask.")
    show("primary view — transport-censored at first retried step", censored)
    show("diagnostic view — uncensored, to size the contamination only", raw)

    if args.out:
        Path(args.out).write_text(json.dumps(
            {"exploratory": True, "censored": censored, "raw": raw}, indent=1) + "\n")
        print(f"\nwrote {args.out}")


if __name__ == "__main__":
    main()

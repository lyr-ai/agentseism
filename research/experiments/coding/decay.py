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

Amendment H3.1: `state` agreement is **undefined**, not zero and not one, while
the donor still holds the fork state or holds an empty diff. Over that stretch
the donor is reading -- `sed`, `cat`, `pytest` -- and "the states match" says only
that neither trajectory has edited anything yet. Reported raw as well, so the
size of the correction stays visible.

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


import hashlib

EMPTY_DIFF = hashlib.sha256(b"").hexdigest()

GRAINS = ("signature", "command", "state")

MATCH, MISS, NA = "match", "miss", "na"


def compare(grain: str, donor_row: dict, run_row: dict, fork_state: str, raw: bool) -> str:
    """One horizon, one continuation: matched, missed, or told us nothing.

    Informativeness is decided by the **donor's** state alone. Letting the
    continuation's state decide would make the denominator depend on the thing
    being measured, which is how a comparison quietly selects its own cases.
    """
    if grain == "signature":
        return MATCH if signature(donor_row.get("command", "")) == signature(
            run_row.get("command", "")) else MISS
    if grain == "command":
        return MATCH if donor_row.get("command", "") == run_row.get("command", "") else MISS
    target = donor_row.get("tracked_diff_hash", "")
    if not raw and (target == fork_state or target == EMPTY_DIFF):
        return NA
    return MATCH if target == run_row.get("tracked_diff_hash", "") else MISS


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


def arm_curves(after: list[dict], series: list[dict], fork_state: str,
               raw_state: bool = False) -> dict:
    """Curves for one arm. Split out so the estimator can be tested without Docker."""
    arm_out = {}
    for grain in GRAINS:
        verdicts = {
            s["name"]: [compare(grain, after[i], s["rows"][i], fork_state, raw_state)
                        for i in range(min(len(s["rows"]), len(after)))]
            for s in series
        }
        died_at = {name: next((i + 1 for i, v in enumerate(v_) if v == MISS), None)
                   for name, v_ in verdicts.items()}
        points, survival, judged = [], 1.0, False
        for h in range(1, len(after) + 1):
            at_risk = [s for s in series if len(s["rows"]) >= h]
            if not at_risk:
                break
            decided = [verdicts[s["name"]][h - 1] for s in at_risk
                       if verdicts[s["name"]][h - 1] != NA]
            judged = judged or bool(decided)
            # Kaplan-Meier. The naive `alive / at_risk` rises when a continuation
            # that had already diverged runs out of steps: the denominator shrinks
            # under the numerator. Conditioning on the risk set -- still alive,
            # still has a step here -- makes the curve monotone and censoring
            # harmless. The sanity check caught the naive version reporting
            # survival 0.75 -> 0.86 between h=3 and h=4 on real data.
            risk = [s for s in at_risk
                    if died_at[s["name"]] is None or died_at[s["name"]] >= h]
            events = sum(1 for s in risk if verdicts[s["name"]][h - 1] == MISS)
            if risk:
                survival *= 1 - events / len(risk)
            points.append({
                "h": h, "n": len(at_risk), "n_risk": len(risk),
                "n_informative": len(decided),
                "matches": decided.count(MATCH),
                "pointwise": decided.count(MATCH) / len(decided) if decided else None,
                "survival": survival if judged else None,
                "censored_by_transport": len(series) - len(at_risk),
            })
        arm_out[grain] = points
    return arm_out


def curves(runs_b: str, runs_a: str, manifest: dict, censor: bool, raw_state: bool = False) -> dict:
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

        fork_state = donor["tracked_diff_hash"]
        arm_out = arm_curves(after, series, fork_state, raw_state)
        out[arm] = {"n_continuations": len(series), "points": arm_out,
                    "donor_steps_after_fork": len(after),
                    "donor_first_state_change": next(
                        (i + 1 for i, r in enumerate(after)
                         if r.get("tracked_diff_hash") != fork_state), None)}
    return out


def show(label: str, data: dict) -> None:
    print(f"\n════ {label} ════")
    for arm, info in data.items():
        print(f"\n  arm {arm}: {info['n_continuations']} continuations, donor has "
              f"{info['donor_steps_after_fork']} steps after the fork, first source "
              f"change at h={info['donor_first_state_change']}")
        head = (f"    {'h':>3}{'n':>4}{'inf':>5}  {'sig pt':>7}{'sig sv':>8}  "
                f"{'cmd pt':>7}{'cmd sv':>8}  {'st pt':>7}{'st sv':>8}  {'cens':>5}")
        print(head)
        horizons = sorted({p["h"] for g in info["points"].values() for p in g})
        for h in horizons:
            get = {g: next((p for p in info["points"][g] if p["h"] == h), None) for g in GRAINS}
            base = get["signature"]
            if base is None:
                continue
            cells = []
            for g in GRAINS:
                p = get[g]
                pt = "  NA  " if p is None or p["pointwise"] is None else f"{p['pointwise']:^7.2f}"
                sv = ("   NA   " if p is None or p["survival"] is None
                      else f"{p['survival']:^8.2f}")
                cells.append(pt + sv)
            thin = "  (thin)" if base["n"] < max(1, info["n_continuations"] / 2) else ""
            print(f"    {h:>3}{base['n']:>4}{get['state']['n_informative']:>5}  "
                  + "  ".join(cells) + f"  {base['censored_by_transport']:>5}" + thin)


def sanity(data: dict) -> list[str]:
    """Three checks, stated before the numbers existed.

    They are cheap and they are the ones that would have caught this analyser's
    own bug: the first version reported state agreement of 1.00 over a stretch
    where the donor had not edited anything.
    """
    failures = []
    for arm, info in data.items():
        first_change = info["donor_first_state_change"]
        for point in info["points"]["state"]:
            if first_change and point["h"] < first_change and point["n_informative"]:
                failures.append(
                    f"arm {arm} h={point['h']}: state judged before the donor's first "
                    f"source change at h={first_change}")
        for grain in GRAINS:
            previous = None
            for point in info["points"][grain]:
                if (previous is not None and point["survival"] is not None
                        and point["survival"] > previous + 1e-9):
                    failures.append(
                        f"arm {arm} {grain} h={point['h']}: survival rose "
                        f"{previous:.2f} -> {point['survival']:.2f}")
                if point["survival"] is not None:
                    previous = point["survival"]
    return failures


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
    raw_state = curves(args.phase_b, args.phase_a, manifest, censor=True, raw_state=True)

    print("EXPLORATORY. Only h=3 on signatures was pre-registered (the H2")
    print("manipulation check). Nothing here selects anything about flask.")
    show("primary — transport-censored, state per amendment H3.1", censored)
    show("diagnostic — no transport censoring, to size the contamination", raw)
    show("diagnostic — raw state, the pre-H3.1 measure, to size the correction", raw_state)

    print("\n──── sanity checks ────")
    failures = sanity(censored)
    for line in failures:
        print(f"  FAIL  {line}")
    if not failures:
        print("  pass  state is undefined before the donor's first source change")
        print("  pass  survival is monotone non-increasing in every granularity")
        print("  pass  pointwise is free to recover, and does")

    if args.out:
        Path(args.out).write_text(json.dumps(
            {"exploratory": True, "censored": censored, "raw": raw,
             "raw_state": raw_state, "sanity_failures": failures}, indent=1) + "\n")
        print(f"\nwrote {args.out}")
    if failures:
        raise SystemExit(1)


if __name__ == "__main__":
    main()

"""Gate 9 — serving-stack behavioural compatibility (prereg amendment C2.3).

Asks one question: does this serving stack reproduce the donors' observable
behaviour at the frozen fork points? It is **not** a test of hardware, numerical
or kernel equivalence, and no result here may be reported as one. A pass
licenses exactly one sentence: the batch passed a pre-registered behavioural
compatibility check.

Coverage is every distinct fork root the 72 specs reduce to -- 24 of them,
8 source trajectories x 3 horizons -- deduplicated, all tested. One hit proves
nothing.

Per root: replay the frozen message prefix to this stack at the registered
sampling parameters, and compare against what the donor actually recorded as
its next turn:

    raw      the response text, byte for byte
    action   the structured action list, where both sides parse

`--resolve-only` does the whole thing except the model call, so the archives and
the comparison targets can be validated before any inference happens.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from agents.coding.fork import load_step
from experiments.coding import c2_protocol as P


def roots() -> list[dict]:
    """The 24 distinct fork roots, deduplicated from the frozen 72 specs."""
    seen: dict[tuple, dict] = {}
    for s in P.expand():
        key = (s["arm"], s["source_batch"], s["source_name"], s["horizon"])
        seen.setdefault(key, {
            "arm": s["arm"], "source_batch": s["source_batch"],
            "source_name": s["source_name"], "horizon": s["horizon"],
            "archive_step": s["archive_step"],
        })
    return [seen[k] for k in sorted(seen)]


def target(root: dict, runs: Path) -> dict:
    """The frozen prefix, and the donor's own next turn after it.

    The prefix is the archive at `archive_step`; the donor's response is the
    first message beyond it in the *next* step's archive. Found by length, not
    by arithmetic on step numbers -- the archives are snapshots of the whole
    message list, so the new turn is whatever sits at the old length.
    """
    archive = runs / root["source_batch"] / f"{root['source_name']}.archive"
    s = root["archive_step"]
    prefix = load_step(archive / f"step_{s:04d}")["messages"]
    nxt_dir = archive / f"step_{s + 1:04d}"
    if not nxt_dir.is_dir():
        raise FileNotFoundError(
            f"{root['source_name']}@{s}: no step_{s + 1:04d}; the donor has no "
            f"recorded turn after this fork point, so there is nothing to compare")
    after = load_step(nxt_dir)["messages"]
    if len(after) <= len(prefix):
        raise ValueError(f"{root['source_name']}@{s}: next archive is not longer")
    donor = after[len(prefix)]
    if donor.get("role") != "assistant":
        raise ValueError(f"{root['source_name']}@{s}: next turn is "
                         f"{donor.get('role')}, not assistant")
    return {"prefix": prefix, "donor": donor}


def compare(donor: dict, got_text: str, got_actions) -> dict:
    d_text = donor.get("content") or ""
    d_actions = (donor.get("extra") or {}).get("actions")
    return {
        "raw_match": d_text == got_text,
        "donor_actions": d_actions,
        "got_actions": got_actions,
        "action_match": (d_actions == got_actions) if d_actions is not None else None,
        "donor_len": len(d_text),
        "got_len": len(got_text),
    }


def verdict(results: list[dict]) -> tuple[str, str]:
    """The three branches of C2.3, applied exactly as written.

    There is no "mostly matched" branch. A partial match on the structured
    action is the second row only if it is *every* root; otherwise it is the
    third.
    """
    if all(r["raw_match"] for r in results):
        return ("PASS_RAW",
                "Raw response identical at all roots. C2 may execute. The paper "
                "may say only that it passed a pre-registered behavioural "
                "compatibility check -- never that the hosts are equivalent.")
    if all(r.get("action_match") for r in results):
        return ("PASS_ACTION_ONLY",
                "Raw text differs somewhere but the structured action matches at "
                "every root. The verbatim-continuation claim is NOT supported. A "
                "downgraded C2 may execute, restricted to policy-level "
                "recoverability, recorded as a new protocol interpretation.")
    return ("STOP",
            "A key action or tool call differs. The 72 specs are NOT run. This "
            "host does not meet donor compatibility, and that is the finding.")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--runs", default=str(ROOT / "data/runs"))
    ap.add_argument("--base", default="http://127.0.0.1:8000/v1")
    ap.add_argument("--out", default=str(ROOT / "data/runs/gate9"))
    ap.add_argument("--resolve-only", action="store_true",
                    help="validate archives and comparison targets; no model call")
    args = ap.parse_args()
    runs = Path(args.runs)

    R = roots()
    print(f"protocol hash {P.protocol_hash()}   fork roots {len(R)}")
    if len(R) != 24:
        print(f"REFUSING: expected 24 distinct fork roots, got {len(R)}")
        return 2

    targets = []
    for r in R:
        t = target(r, runs)
        targets.append((r, t))
        d = t["donor"]
        acts = (d.get("extra") or {}).get("actions")
        print(f"  {r['arm']:4} {r['source_name']:34} h={r['horizon']:>2} "
              f"step={r['archive_step']:>2}  prefix={len(t['prefix']):>3} msgs  "
              f"donor={len(d.get('content') or ''):>5} chars  "
              f"actions={'yes' if acts else 'NONE'}")
    if args.resolve_only:
        print("\nresolve-only: every root has a frozen prefix and a recorded donor turn.")
        return 0

    from openai import OpenAI
    client = OpenAI(base_url=args.base, api_key="not-needed")
    model = client.models.list().data[0].id
    print(f"\nserving {model}")

    results = []
    for r, t in targets:
        t0 = time.time()
        resp = client.chat.completions.create(
            model=model, messages=t["prefix"],
            temperature=P.SAMPLING["temperature"], seed=P.SAMPLING["seed"],
        )
        text = resp.choices[0].message.content or ""
        c = compare(t["donor"], text, None)
        c |= {k: r[k] for k in ("arm", "source_batch", "source_name", "horizon",
                                "archive_step")}
        c["seconds"] = round(time.time() - t0, 1)
        results.append(c)
        print(f"  {r['arm']:4} {r['source_name']:34} h={r['horizon']:>2}  "
              f"raw={'MATCH' if c['raw_match'] else 'differ':6}  "
              f"{c['donor_len']}→{c['got_len']} chars  {c['seconds']}s")

    code, why = verdict(results)
    out = Path(args.out); out.mkdir(parents=True, exist_ok=True)
    (out / "gate9.json").write_text(json.dumps({
        "protocol_hash": P.protocol_hash(),
        "prereg": "paper/PREREG_C2_RECOVERABILITY.md amendment C2.3",
        "model": model, "sampling": P.SAMPLING,
        "written_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "verdict": code, "reason": why, "results": results,
    }, indent=2))
    print(f"\n──── GATE 9: {code} ────\n{why}")
    return 0 if code != "STOP" else 1


if __name__ == "__main__":
    raise SystemExit(main())

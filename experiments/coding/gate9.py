"""Gate 9 — serving-stack behavioural compatibility (prereg amendment C2.3).

Asks one question: does this serving stack reproduce the donors' observable
behaviour at the frozen fork points? It is **not** a test of hardware, numerical
or kernel equivalence, and no result here may be reported as one. A pass
licenses exactly one sentence: the batch passed a pre-registered behavioural
compatibility check.

Coverage is every distinct fork root the 72 specs reduce to -- 24 of them,
8 source trajectories x 3 horizons -- deduplicated. One hit proves nothing.

Per amendment C2.3.1, `A_6 h=16` carries no archived donor turn: the donor
emitted a response with no tool call, the scaffold injected its correction and
kept only the retry. That root is `compatibility_unknown` -- not a pass and not
a fail -- and the verdict is computed over the 23 archived-comparable roots. The
retry is not substituted for it, another horizon is not substituted for it, and
no looser matching rule is introduced. The only admissible phrasing downstream
is "all 23 archived-comparable fork roots ...", never "all fork roots".

Per root: replay the frozen message prefix to this stack **through the same
client the continuation uses** -- `InstrumentedLitellmModel` constructed exactly
as `run_c2.py` constructs it, `stream=True`, `attempt_timeout=180`,
`max_attempts=6` -- and compare against what the donor actually recorded as its
next turn:

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
        # C2.3.1: the scaffold discarded a malformed donor turn and kept only
        # the retry, so no comparison target exists. Not an error and not a
        # failure -- the root is excluded from the verdict and recorded as such.
        return {"prefix": prefix, "donor": None,
                "unknown_reason": f"next turn is {donor.get('role')}, not assistant: "
                                  "scaffold correction, donor response not archived"}
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
        if d is None:
            print(f"  {r['arm']:4} {r['source_name']:34} h={r['horizon']:>2} "
                  f"step={r['archive_step']:>2}  prefix={len(t['prefix']):>3} msgs  "
                  f"COMPATIBILITY_UNKNOWN (C2.3.1)")
            continue
        acts = (d.get("extra") or {}).get("actions")
        print(f"  {r['arm']:4} {r['source_name']:34} h={r['horizon']:>2} "
              f"step={r['archive_step']:>2}  prefix={len(t['prefix']):>3} msgs  "
              f"donor={len(d.get('content') or ''):>5} chars  "
              f"actions={'yes' if acts else 'NONE'}")
    comparable = sum(1 for _, t in targets if t["donor"] is not None)
    print(f"\narchived-comparable roots: {comparable}   "
          f"compatibility_unknown: {len(targets) - comparable}")
    if comparable != 23:
        print(f"REFUSING: C2.3.1 fixes 23 archived-comparable roots, found {comparable}")
        return 2
    if args.resolve_only:
        return 0

    # The same client, built the same way, because C2.3 asks for the generation
    # parameters the continuation would use and not for an approximation of
    # them. An earlier revision of this file issued a plain non-streaming
    # OpenAI call, which has no `attempt_timeout`: the agent aborts and retries
    # an attempt that is still generating at 180 s, and without that bound a
    # single root ran past 36,000 tokens with no end in sight. That was a
    # defect in this instrument, not an observation about the host.
    import os
    os.environ.setdefault("OPENAI_API_BASE", args.base)
    os.environ.setdefault("OPENAI_API_KEY", "not-needed")
    from agents.coding.instrumented_model import InstrumentedLitellmModel
    client = InstrumentedLitellmModel(
        model_name=f"openai/{P.MODEL['id']}", model_kwargs={"drop_params": True},
        stream=True, attempt_timeout=180, max_attempts=6)
    model = P.MODEL["id"]
    print(f"\nserving {model}  (stream, attempt_timeout=180, max_attempts=6)")

    results, unknown = [], []
    for r, t in targets:
        if t["donor"] is None:
            unknown.append({**{k: r[k] for k in ("arm", "source_batch",
                             "source_name", "horizon", "archive_step")},
                            "status": "compatibility_unknown",
                            "reason": t["unknown_reason"]})
            print(f"  {r['arm']:4} {r['source_name']:34} h={r['horizon']:>2}  "
                  f"SKIPPED — compatibility_unknown (C2.3.1)")
            continue
        t0 = time.time()
        try:
            msg = client.query(list(t["prefix"]))
            text = msg.get("content") or ""
            acts = (msg.get("extra") or {}).get("actions")
            err = None
        except Exception as exc:  # noqa: BLE001
            # Recorded, not retried around. A root the registered client cannot
            # complete is a fact about this stack under the registered
            # configuration, and it is carried into the verdict as a non-match.
            text, acts, err = "", None, f"{type(exc).__name__}: {str(exc)[:200]}"
        c = compare(t["donor"], text, acts)
        c["error"] = err
        c |= {k: r[k] for k in ("arm", "source_batch", "source_name", "horizon",
                                "archive_step")}
        c["seconds"] = round(time.time() - t0, 1)
        results.append(c)
        print(f"  {r['arm']:4} {r['source_name']:34} h={r['horizon']:>2}  "
              f"raw={'MATCH' if c['raw_match'] else 'differ':6}  "
              f"act={'MATCH' if c['action_match'] else 'differ':6}  "
              f"{c['donor_len']}→{c['got_len']} chars  {c['seconds']}s"
              + (f"  [{c['error']}]" if c.get("error") else ""))
        sys.stdout.flush()

    code, why = verdict(results)
    out = Path(args.out); out.mkdir(parents=True, exist_ok=True)
    (out / "gate9.json").write_text(json.dumps({
        "protocol_hash": P.protocol_hash(),
        "prereg": "paper/PREREG_C2_RECOVERABILITY.md amendment C2.3",
        "model": model, "sampling": P.SAMPLING,
        "written_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "verdict": code, "reason": why,
        "archived_comparable": len(results),
        "compatibility_unknown": unknown,
        "reporting_rule": "Admissible phrasing is 'all 23 archived-comparable "
                          "fork roots ...'. 'All fork roots passed' is not a "
                          "sentence this experiment may write. (C2.3.1)",
        "results": results,
    }, indent=2))
    print(f"\n──── GATE 9: {code} ────  over {len(results)} archived-comparable "
          f"roots, {len(unknown)} compatibility_unknown\n{why}")
    return 0 if code != "STOP" else 1


if __name__ == "__main__":
    raise SystemExit(main())

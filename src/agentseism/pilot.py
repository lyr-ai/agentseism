"""Execute the Gate 2 pilot, or prove it could be executed.

    --resolve-only   regenerate the plan, verify the hash, check the budget
                     machine. No agent, no model, no container.
    --backend fake   run all 18 cells against a synthetic agent. Marked
                     synthetic in every artifact and in the report.
    --backend real   requires --execute-registered-pilot as well.

The runner executes frozen rules and decides nothing. Arms, order, cap and
stops come from `pilot_protocol`, which is `PREREG_PILOT.md` turned into data.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
import time
from pathlib import Path

os.environ.setdefault("MSWEA_COST_TRACKING", "ignore_errors")

from agentseism import pilot_protocol as P  # noqa: E402
from agentseism.budget import (  # noqa: E402
    Budget, BudgetStop, RunLog, session_fingerprint, write_atomic,
)


PILOT_THRESHOLDS = {"warning": P.WARNING_USD,
                    "no_new_block": P.NO_NEW_BLOCK_USD,
                    "stop_stage": float("inf"),
                    "absolute": P.ABSOLUTE_LIMIT_USD}
"""The registered pilot stops, mapped honestly onto the machine's three slots.

The registration has **$20 warning · $25 start no new block · $30 absolute**.
There is no "stop the current stage" level, so `stop_stage` is unreachable
rather than aliased to $25 — aliasing would turn "do not start another block"
into "abandon the block you are in", which is stricter than what was
registered and would truncate work already paid for.

$20 is a warning: it is reported, and it starts nothing on its own. It was
registered and then left out of the implementation, so a run passing $20 said
nothing at all; `warning` now carries it, and `check` logs `budget_warning`
beside `budget_ok` without refusing anything. `WARNING_USD` was already inside
`protocol_hash`, so naming it here changes no hash."""


class PilotStop(RuntimeError):
    """A registered stop. Artifacts are kept; no release verdict follows."""


def artifact(cell: dict, result: dict, identity: dict, synthetic: bool) -> dict:
    return {
        "schema_version": P.SCHEMA_VERSION,
        "protocol_hash": P.protocol_hash(), "order_hash": P.ORDER_HASH,
        "synthetic": synthetic,
        "order_index": cell["order_index"], "replicate": cell["replicate"],
        "task": cell["task"], "arm": cell["arm"],
        "step_limit": cell["step_limit"], "hint": cell["hint"],
        "challenge_requested": cell["challenge"],
        "identity": identity,
        **result,
    }


def freeze(out: Path, cell: dict, payload: dict) -> str:
    name = (f"run_{cell['order_index']:02d}_{cell['task']}_{cell['arm']}"
            f"_r{cell['replicate']}")
    return write_atomic(out / "runs" / f"{name}.json",
                        json.dumps(payload, indent=2, sort_keys=True, default=str))


def verify_artifact(path: Path) -> bool:
    d = Path(str(path) + ".sha256")
    if not (path.exists() and d.exists()):
        return False
    return (hashlib.sha256(path.read_text().encode()).hexdigest()
            == d.read_text().split()[0])


def completed_cells(out: Path) -> dict[int, dict]:
    """Only runs whose artifact still verifies. A tampered or truncated file
    is not a completed cell, and resume re-runs it."""
    done = {}
    for f in sorted((out / "runs").glob("run_*.json")):
        if not verify_artifact(f):
            continue
        d = json.loads(f.read_text())
        done[d["order_index"]] = d
    return done


def cell_validity(runs: list[dict]) -> dict:
    """Per (task, arm): a cell needs 2 of 2 valid to be interpreted (P.1 §2).

    No re-running, no substitution, no borrowing. Without this, "exactly two
    replicates" quietly becomes "two, and more when two is not enough".
    """
    by: dict[tuple, list[dict]] = {}
    for r in runs:
        by.setdefault((r["task"], r["arm"]), []).append(r)
    out = {}
    for k, rs in by.items():
        valid = [r for r in rs if r["termination"] in P.SCORABLE]
        out[k] = {"n": len(rs), "valid": len(valid),
                  "interpretable": len(valid) == P.REPLICATES,
                  "terminations": sorted(r["termination"] for r in rs)}
    return out


def run_pilot(out: Path, backend, task_ids: list[str], synthetic: bool,
              log: RunLog, budget: Budget, on_block=None) -> dict:
    """`on_block` supplies the billing reading each block requires.

    One reading authorises one block, so the hook exists rather than a bypass:
    the synthetic path enters a zero reading, a real operator enters the page
    total. The rule is the same in both, which is the point of exercising it
    synthetically at all.
    """
    cells = P.verify(task_ids)
    identity = session_fingerprint()
    log.append("plan", protocol_hash=P.protocol_hash(), order_hash=P.ORDER_HASH,
               cells=len(cells), tasks=task_ids, synthetic=synthetic)

    # Read the authorisation; do not take it. Calling `check("after_setup")`
    # here consumed the reading that the first block needs, and re-authorised
    # the checkpoint on whatever number happened to be last -- which on host 2
    # would have been the reading entered for block 0.
    auth = budget.authorisation("after_setup")
    if auth is None:
        raise PilotStop(
            "no un-superseded after_setup authorisation in the run log. Take "
            "it with a reading from now:  python -m agentseism.pilot_budget "
            "--reading <page total> --checkpoint after_setup --not-before "
            "@setup_started")
    log.append("authorisation_read", checkpoint="after_setup",
               authorised_at=auth["ts"], usd=auth["usd"],
               reading_seq=auth.get("reading_seq"))
    done = completed_cells(out)
    last_block = None
    for cell in cells:
        if cell["order_index"] in done:
            continue
        block = (cell["replicate"], cell["task"])
        if block != last_block:
            # A block boundary is a registered checkpoint. Inside one, no
            # threshold fires and nothing is re-decided.
            if on_block:
                on_block(block)
            budget.check("before_block", cell["order_index"])
            last_block = block
        t0 = time.time()
        result = backend(cell)
        result.setdefault("elapsed_seconds", round(time.time() - t0, 2))
        if result["termination"] not in P.TERMINATIONS:
            raise PilotStop(f"unknown termination {result['termination']!r}")
        payload = artifact(cell, result, identity, synthetic)
        digest = freeze(out, cell, payload)
        path = (out / "runs" /
                f"run_{cell['order_index']:02d}_{cell['task']}_{cell['arm']}"
                f"_r{cell['replicate']}.json")
        if not verify_artifact(path):
            raise PilotStop(f"artifact failed its own digest: {path}")
        log.append("run", order_index=cell["order_index"], task=cell["task"],
                   arm=cell["arm"], replicate=cell["replicate"],
                   termination=result["termination"], sha256=digest,
                   elapsed=result["elapsed_seconds"])
        done[cell["order_index"]] = payload

    runs = [done[i] for i in sorted(done)]
    validity = cell_validity(runs)
    complete = len(runs) == P.CELLS and all(v["interpretable"]
                                            for v in validity.values())
    report = {
        "state": "complete_18" if complete else "censored_feasibility_run",
        "verdict_allowed": False,     # always: this is a feasibility pilot
        "synthetic": synthetic,
        "cells_done": len(runs), "cells_registered": P.CELLS,
        "interpretable_cells": sum(1 for v in validity.values()
                                   if v["interpretable"]),
        "validity": {f"{t}|{a}": v for (t, a), v in validity.items()},
        "protocol_hash": P.protocol_hash(), "order_hash": P.ORDER_HASH,
    }
    write_atomic(out / "report.json",
                 json.dumps(report, indent=2, sort_keys=True))
    return report


def fake_backend(cell: dict) -> dict:
    """Synthetic. Deterministic per cell, and never mistaken for evidence."""
    seed = f"{cell['order_index']}|{cell['task']}|{cell['arm']}"
    h = int(hashlib.sha256(seed.encode()).hexdigest()[:8], 16)
    fired = (h % 10) != 0
    return {
        "termination": P.COMPLETED if fired else P.NOT_ELIGIBLE,
        "task_success": int((h >> 4) % 3 != 0),
        "challenge_status": "FIRED" if fired else P.NOT_ELIGIBLE,
        "recovered": int(fired and (h >> 8) % 4 != 0),
        "messages": [], "tool_calls": [], "transport_attempts": 1,
        "evaluator_output": {"synthetic": True},
        "note": "synthetic execution test — not pilot evidence",
    }


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="seism pilot", description=__doc__)
    ap.add_argument("--out", default="data/runs/pilot")
    ap.add_argument("--resolve-only", action="store_true")
    ap.add_argument("--backend", choices=("fake", "real"), default="fake")
    ap.add_argument("--execute-registered-pilot", action="store_true")
    ap.add_argument("--tasks", nargs="*", default=None)
    args = ap.parse_args(argv)
    out = Path(args.out)

    if args.resolve_only:
        cells = P.verify(args.tasks)
        print(f"protocol {P.protocol_hash()}   order {P.ORDER_HASH}   "
              f"cells {len(cells)}")
        for c in cells:
            print(f"  {c['order_index']:>2}  rep{c['replicate']}  {c['task']:<10}"
                  f"{c['arm']:<10} step_limit={c['step_limit']:<4} "
                  f"hint={c['hint']:<11} challenge={c['challenge']}")
        print(f"\ncap {P.RUN_TIMEOUT_SECONDS}s   stops "
              f"${P.WARNING_USD:.0f}/${P.NO_NEW_BLOCK_USD:.0f}/"
              f"${P.ABSOLUTE_LIMIT_USD:.0f} on pilot spend "
              "(current total - frozen baseline)")
        print("RESOLVE-ONLY: PASS")
        return 0

    if args.backend == "real" and not args.execute_registered_pilot:
        raise SystemExit(
            "refusing: --backend real requires --execute-registered-pilot. "
            "This spends money against a live serving stack.")
    if args.backend == "real":
        raise SystemExit(
            "the real backend is wired on the instance, after the six "
            "deployment checks. Nothing here runs an agent.")

    # Synthetic runs never share a directory with real ones.
    out = out / "synthetic" if args.backend == "fake" else out
    log = RunLog(out / "run.jsonl")
    budget = Budget(log, PILOT_THRESHOLDS)
    if budget.baseline() is None:
        budget.record_baseline(0.0, billing_period="synthetic",
                               note="fake backend; no real spend")
    budget.record_reading(0.0, billing_period="synthetic")
    # Taking the checkpoint is the caller's job; `run_pilot` only verifies that
    # someone took it. On a real host that caller is a human with the billing
    # page open.
    if budget.authorisation("after_setup") is None:
        budget.check("after_setup")
    try:
        rep = run_pilot(out, fake_backend, args.tasks or None, True, log,
                        budget,
                        on_block=lambda b: budget.record_reading(
                            0.0, billing_period="synthetic",
                            note=f"synthetic block {b}"))
    except BudgetStop as e:
        log.append("stopped", stop_kind=e.kind, detail=e.detail)
        print(f"stopped: {e.kind}", file=sys.stderr)
        return 1
    print(json.dumps(rep, indent=2, sort_keys=True))
    print("\nsynthetic execution test — not pilot evidence")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

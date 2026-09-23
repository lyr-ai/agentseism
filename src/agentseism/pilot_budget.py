"""Budget operations on the pilot run log, from the command line.

Exists because a checkpoint is a *reading*, not a moment. `after_setup` run on
the launch reading passes while the entire cost of setup is still absent from
the billing page, so the checkpoint has to be taken separately, after setup,
with a number read then.

The log is append-only. A checkpoint that turned out to be meaningless is
annotated as superseded, never deleted or rewritten: what was believed at the
time is part of the record.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from agentseism import pilot_protocol as P  # noqa: E402
from agentseism.budget import Budget, BudgetStop, RunLog  # noqa: E402
from agentseism.pilot import PILOT_THRESHOLDS, SPECS  # noqa: E402

DEFAULT_LOG = "data/runs/pilot/run.jsonl"


def phase_ts(log: RunLog, name: str) -> str:
    """When a named phase marker was written. Raises if it never was."""
    hits = [r for r in log.read() if r["kind"] == "phase" and r.get("name") == name]
    if not hits:
        raise SystemExit(f"no phase marker {name!r} in the log; the reading "
                         "cannot be checked against a moment that was never "
                         "recorded")
    return str(hits[-1]["ts"])


def status(log: RunLog) -> int:
    base = [r for r in log.read() if r["kind"] == "billing_baseline"]
    readings = [r for r in log.read() if r["kind"] == "billing_reading"]
    checks = [r for r in log.read() if r["kind"] in ("budget_ok", "budget_stop",
                                                     "budget_refused")]
    rows = log.read()
    sup_n = {r["supersedes_n"] for r in rows
             if r["kind"] == "budget_superseded" and r.get("supersedes_n") is not None}
    sup_ts = {r.get("supersedes_ts") for r in rows
              if r["kind"] == "budget_superseded" and r.get("supersedes_n") is None}
    if base:
        b = base[0]
        print(f"baseline    ${b['current_total']:.2f}  {b['billing_period']}  "
              f"{b.get('currency')}  frozen {b['ts']}")
    for r in readings:
        print(f"reading #{r.get('seq', 0)}  ${r['current_total']:.2f}  "
              f"{r['source']}  {r['ts']}")
    for r in checks:
        mark = ("  SUPERSEDED"
                if (r.get("n") in sup_n
                    or (r.get("n") is None and r["ts"] in sup_ts)) else "")
        print(f"{r['kind']:<15} {r.get('checkpoint', '-'):<13} "
              f"spend ${r.get('usd', 0):.2f}  {r['ts']}{mark}")
    return 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--log", default=DEFAULT_LOG)
    ap.add_argument("--status", action="store_true")
    ap.add_argument("--reading", type=float,
                    help="cumulative account total, read from the billing page now")
    ap.add_argument("--checkpoint", choices=("after_setup", "after_donors",
                                             "before_block"))
    ap.add_argument("--block", type=int)
    ap.add_argument("--not-before",
                    help="an ISO-8601 ...Z timestamp, or @<phase> to use when "
                         "that phase marker was written")
    ap.add_argument("--note", default="")
    ap.add_argument("--period", help="the billing period exactly as the page "
                                     "displays it (required with --observe)")
    ap.add_argument("--currency", help="the currency exactly as the page "
                                       "displays it (required with --observe)")
    ap.add_argument("--observe", type=float,
                    help="a settled page total read with NOTHING running, "
                         "before renting the next host. Verifies the period, "
                         "the currency and the thresholds, and records the "
                         "observation. Authorises nothing.")
    ap.add_argument("--project-after-block", type=int,
                    help="compute the P.7 cost projection from the readings "
                         "that bracket this block index")
    ap.add_argument("--supersede-checkpoint",
                    help="mark the last checkpoint record with this name as "
                         "superseded; requires --reason")
    ap.add_argument("--reason", default="")
    ap.add_argument("--cells-in-block", type=int, default=0)
    ap.add_argument("--experiment", choices=("pilot", "f3"), default="pilot",
                    help="whose registered thresholds this reading is "
                         "checked against")
    args = ap.parse_args(argv)

    log = RunLog(Path(args.log))
    spec = SPECS[args.experiment]
    budget = Budget(log, spec.thresholds)

    if args.status:
        return status(log)

    if args.observe is not None:
        base = budget.baseline()
        if base is None:
            return _fail(f"no frozen baseline in {args.log}")
        # Verified against what the page shows, not copied from the
        # baseline. Reading the period out of the record we are comparing
        # against cannot detect that the page has moved to a new one, and a
        # difference against the wrong period is not this experiment's spend.
        if not args.period or not args.currency:
            return _fail(
                "--observe requires --period and --currency, as the page "
                "displays them. Carrying them over from the baseline would "
                "make the check unable to notice the thing it is for")
        if args.period != base["billing_period"]:
            return _fail(f"the page shows period {args.period!r}, the baseline "
                         f"is {base['billing_period']!r}; the difference "
                         "between them is not this experiment's spend")
        if args.currency != base.get("currency"):
            return _fail(f"the page shows currency {args.currency!r}, the "
                         f"baseline is {base.get('currency')!r}")
        usd = round(args.observe - base["current_total"], 2)
        if usd < 0:
            return _fail(f"${args.observe:.2f} is below the frozen baseline of "
                         f"${base['current_total']:.2f}; a cumulative total "
                         "cannot fall, so one of the two is wrong")
        t = spec.thresholds
        print(f"  experiment_billing_baseline  ${base['current_total']:.2f}  "
              f"{base['billing_period']}  {base.get('currency')}")
        print(f"  settled page total           ${args.observe:.2f}")
        label = f"cumulative_{spec.name}_spend"
        print(f"  {label:<29}${usd:.2f}")
        for name, level in (("warning", t["warning"]),
                            ("no new block", t["no_new_block"]),
                            ("absolute stop", t["absolute"])):
            page = base["current_total"] + level
            hit = "REACHED" if usd >= level else f"{level - usd:>6.2f} to go"
            print(f"  {name:<28} ${page:.2f}   {hit}")
        rec = log.append(
            "billing_observation", current_total=float(args.observe),
            usd=usd, source="manual", instances_running=0,
            billing_period=args.period, currency=args.currency,
            observed_period_matches_baseline=True,
            note=args.note or "settled page total read with nothing running, "
                              "before renting the next host. An observation: "
                              "it authorises nothing and is not a baseline")
        print(f"  recorded                     billing_observation #{rec['n']} "
              f"at {rec['ts']}")
        if usd >= t["absolute"]:
            print("\n  STOP — the absolute limit is already reached; do not "
                  "rent another host.", file=sys.stderr)
            return 1
        if usd >= t["no_new_block"]:
            print("\n  STOP — past the no-new-block level; a further host "
                  "would start work that cannot be authorised.", file=sys.stderr)
            return 1
        if usd >= t["warning"]:
            print(f"\n  WARNING — cumulative spend has reached "
                  f"${t['warning']:.0f}.")
        return 0

    if args.project_after_block is not None:
        rows = log.read()
        auth = [r for r in rows if r["kind"] == "budget_ok"
                and r.get("checkpoint") == "before_block"
                and r.get("block_index") == args.project_after_block]
        if not auth:
            return _fail(f"no before_block authorisation for block "
                         f"{args.project_after_block}; the projection needs the "
                         "reading that opened it")
        last = log.last_billing()
        if last is None or last["source"] != "manual":
            return _fail("the projection needs a manual reading taken after "
                         "the block finished")
        base = budget.baseline()
        after = round(last["current_total"] - base["current_total"], 2)
        done = len([r for r in rows if r["kind"] == "run"])
        # A block is one (replicate, task): three cells, one per arm.
        cells_in_block = args.cells_in_block or len(spec.arms)
        proj = P.project_after_block(auth[-1]["usd"], after, cells_in_block,
                                     spec.cell_count - done)
        print(json.dumps(proj, indent=2, sort_keys=True))
        log.append("cost_projection", block_index=args.project_after_block,
                   **proj)
        if proj["halt"]:
            print("\n  HALT — finishing the plan at the observed rate would "
                  f"reach ${proj['projected_cumulative_spend']:.2f}, past the "
                  f"registered ${proj['absolute_limit']:.0f} stop. Re-model "
                  "before releasing another block.", file=sys.stderr)
            return 1
        print(f"\n  projection ${proj['projected_cumulative_spend']:.2f} is "
              f"within the registered ${proj['absolute_limit']:.0f} stop; "
              f"marginal ${proj['marginal_cost_per_run']:.2f}/run against an "
              f"expectation of ${proj['expectation_per_run']:.2f}")
        return 0

    if args.supersede_checkpoint:
        if not args.reason:
            return _fail("--supersede-checkpoint requires --reason")
        hits = [r for r in log.read()
                if r["kind"] in ("budget_ok", "budget_stop")
                and r.get("checkpoint") == args.supersede_checkpoint]
        if not hits:
            return _fail(f"no checkpoint record for {args.supersede_checkpoint!r}")
        target = hits[-1]
        rec = log.append("budget_superseded",
                         checkpoint=args.supersede_checkpoint,
                         supersedes_n=target.get("n"),
                         supersedes_ts=target["ts"],
                         supersedes_kind=target["kind"],
                         supersedes_reading_seq=target.get("reading_seq"),
                         supersedes_usd=target.get("usd"),
                         reason=args.reason)
        print(json.dumps(rec, indent=2, sort_keys=True))
        print("\nthe original record is left exactly as written; this annotation "
              "sits after it")
        return 0

    if args.reading is None or not args.checkpoint:
        return _fail("give --status, or --reading with --checkpoint, or "
                     "--supersede-checkpoint with --reason")

    not_before = args.not_before
    if not_before and not_before.startswith("@"):
        not_before = phase_ts(log, not_before[1:])

    base = budget.baseline()
    if base is None:
        return _fail(f"no frozen baseline in {args.log}")
    budget.record_reading(args.reading, source="manual",
                          billing_period=base["billing_period"],
                          currency=base.get("currency"),
                          note=args.note or f"reading for {args.checkpoint}")
    try:
        s = budget.check(args.checkpoint, args.block, not_before=not_before)
    except BudgetStop as e:
        print(f"STOP  {e.kind}\n  {e.detail}", file=sys.stderr)
        return 1
    print(f"  baseline      ${base['current_total']:.2f}")
    print(f"  reading       ${args.reading:.2f}   ({s['reading_ts']})")
    print(f"  {spec.name + '_spend':<14}${s['usd']:.2f}")
    print(f"  checkpoint    {args.checkpoint}: PASS")
    if s["warning"]:
        print(f"  WARNING       spend has reached ${s['warning_at']:.0f}")
    print(f"  stops         ${spec.thresholds['no_new_block']:.0f} no new block "
          f"· ${spec.thresholds['absolute']:.0f} absolute")
    return 0


def _fail(msg: str) -> int:
    print(msg, file=sys.stderr)
    return 2


if __name__ == "__main__":
    raise SystemExit(main())

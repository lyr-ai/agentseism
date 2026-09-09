"""What did the transport cost this batch, and does the diagnosis hold up?

Two questions, and they are different.

**Operational.** How often did a step have to be re-sent, and what failed when it
did. If streaming has removed the retries, that is strong evidence the earlier
stalls really were non-streaming duration crossing Cloudflare's ~120 s window,
and not the model or the server being unreliable -- the prediction is specific
and it is falsifiable here.

**Scientific.** A re-sent step is a fresh sample, not a replay. The endpoint
disagrees with itself at temperature 0 -- measured in
`experiments/coding/stream_equivalence.py`, where two identical unseeded requests
differed in content, reasoning, tool calls, and on one shape in how many commands
the agent was handed. So every retry is an extra draw from the model, kept in
place of the one that was lost. Rare retries are a nuisance covariate. Frequent
ones mean the batch's steps did not come from the same process as unretried ones,
and that is a fact about validity, not about latency.

Reports both. It does not decide validity; it produces the number that decision
needs.
"""

from __future__ import annotations

import argparse
import collections
import glob
import json
import os
from pathlib import Path


def audit(directory: str, pattern: str) -> dict:
    rows, per_run = [], {}
    for path in sorted(glob.glob(f"{directory}/{pattern}")):
        if path.endswith(".probe.jsonl"):
            continue
        run = os.path.basename(path)[:-5]
        data = json.loads(Path(path).read_text())
        calls = [m.get("extra", {}) for m in data["messages"] if m.get("role") == "assistant"]
        retried, attempts, exceptions, seconds_lost, where = 0, 0, collections.Counter(), 0.0, []
        for index, call in enumerate(calls, 1):
            events = call.get("transport_events") or []
            n = call.get("transport_attempts", 1 if not events else len(events))
            attempts += n
            if call.get("transport_retried"):
                retried += 1
                # Position in the trajectory and which attempt was finally used.
                # A retried step was inferred more than once and the later draw
                # kept, so where it sits and how many draws it took are what a
                # sensitivity analysis needs -- an arm-level rate alone cannot
                # say whether the extra draws landed early, late, or in one arm.
                where.append({"step": index, "attempt_used": n})
            for event in events:
                if event.get("outcome") != "ok":
                    exceptions[event.get("exception", "?")] += 1
                    seconds_lost += event.get("seconds", 0.0)
        per_run[run] = {
            "exit_status": str(data["info"].get("exit_status")),
            "calls": len(calls),
            "attempts": attempts,
            "retried_steps": retried,
            "retry_rate": round(retried / len(calls), 4) if calls else 0.0,
            "seconds_lost": round(seconds_lost, 1),
            "exceptions": dict(exceptions),
            "retried_at": where,
            # Present only if the run used the instrumented model at all: a run
            # without these marks cannot be audited, and saying so is the point.
            "instrumented": any("transport_attempts" in c for c in calls),
        }
        rows.append(run)
    return per_run


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--runs", required=True)
    ap.add_argument("--task", default="pytest-dev__pytest-10051")
    ap.add_argument("--pattern", help="filename glob; defaults to the task's Phase A runs")
    ap.add_argument("--out")
    args = ap.parse_args()

    per_run = audit(args.runs, args.pattern or f"{args.task}__r*.json")
    if not per_run:
        raise SystemExit(f"no trajectories matching in {args.runs}")

    print(f"{'run':>10}{'exit':>12}{'calls':>7}{'attempts':>10}{'retried':>9}"
          f"{'rate':>8}{'lost s':>9}  exceptions")
    total_calls = total_attempts = total_retried = 0
    for run, info in sorted(per_run.items()):
        mark = "" if info["instrumented"] else "  (NOT INSTRUMENTED)"
        print(f"{run:>10}{info['exit_status']:>12}{info['calls']:>7}{info['attempts']:>10}"
              f"{info['retried_steps']:>9}{info['retry_rate']:>8.3f}{info['seconds_lost']:>9.0f}  "
              f"{info['exceptions'] or '-'}{mark}")
        total_calls += info["calls"]
        total_attempts += info["attempts"]
        total_retried += info["retried_steps"]

    rate = total_retried / total_calls if total_calls else 0.0
    print(f"\n  {total_calls} calls, {total_attempts} attempts, "
          f"{total_retried} retried steps, rate {rate:.3f}")
    for run, info in sorted(per_run.items()):
        if info["retried_at"]:
            print(f"    {run} retried at {info['retried_at']}")

    # A threshold has to be stated somewhere or it gets chosen after the fact.
    # One retried step in fifty is a covariate to note; one in ten is a different
    # sampling process, and the batch has to be argued for rather than assumed.
    print()
    if total_retried == 0:
        print("  no retries: the streaming fix holds, and every step is a single draw")
    elif rate < 0.02:
        print(f"  retry rate {rate:.3f} < 0.02 — nuisance covariate, recorded per step")
    else:
        print(f"  retry rate {rate:.3f} >= 0.02 — enough extra draws that this batch cannot be "
              f"treated as one unretried process without an argument")

    if args.out:
        Path(args.out).write_text(json.dumps(per_run, indent=1) + "\n")
        print(f"\nwrote {args.out}")


if __name__ == "__main__":
    main()

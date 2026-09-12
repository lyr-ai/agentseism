"""Join correctness labels onto the recorded trajectories.

Exploratory. No pre-registration covers correctness -- it was not part of the
coding experiment, H2 or H3 -- so every relationship visible here is
hypothesis-generating and is labelled as such wherever it is reported.
"""

from __future__ import annotations

import argparse
import json
from collections import Counter
from glob import glob
from pathlib import Path


def load_reports(directory: str) -> dict[str, dict]:
    out = {}
    for path in glob(f"{directory}/agentseism.*.json"):
        key = Path(path).name[len("agentseism."):-len(".json")]
        data = json.loads(Path(path).read_text())
        out[key] = data
    return out


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--index", required=True)
    ap.add_argument("--reports", required=True)
    ap.add_argument("--runs", required=True)
    ap.add_argument("--manifest", required=True)
    ap.add_argument("--out")
    args = ap.parse_args()

    index = json.loads(Path(args.index).read_text())
    reports = load_reports(args.reports)
    manifest = json.loads(Path(args.manifest).read_text())
    donors = {f"r{v['run']}": arm for arm, v in manifest["arms"].items()}

    rows = []
    for entry in index:
        key = entry["run_key"]
        report = reports.get(key)
        resolved = bool(report and report.get("resolved_ids"))
        probe = Path(args.runs) / entry["batch"] / f"{entry['run']}.probe.jsonl"
        steps = [json.loads(l) for l in open(probe)] if probe.exists() else []
        short = entry["run"].replace("pytest-dev__pytest-10051__", "")
        rows.append({
            "batch": entry["batch"].replace("h2_phase_", ""),
            "run": short,
            "role": ("donor " + donors[short]) if short in donors else
                    ("fork " + short.split("_")[0] if "_" in short else ""),
            "steps": len(steps),
            "final": (steps[-1]["tracked_diff_hash"][:12] if steps else "?"),
            "patch_bytes": entry["patch_bytes"],
            "resolved": resolved,
            "has_report": report is not None,
        })

    rows.sort(key=lambda r: (r["batch"], r["run"]))
    print(f"{'batch':<8}{'run':<6}{'role':<10}{'steps':>6}{'final':>15}"
          f"{'patch B':>9}  correct")
    for r in rows:
        mark = "-" if not r["has_report"] else ("PASS" if r["resolved"] else "FAIL")
        print(f"{r['batch']:<8}{r['run']:<6}{r['role']:<10}{r['steps']:>6}"
              f"{r['final']:>15}{r['patch_bytes']:>9}  {mark}")

    print("\n──── summary ────")
    for group, label in (("a1", "A1  fresh runs"),
                         ("b", "B   continuations")):
        sub = [r for r in rows if r["batch"] == group]
        if not sub:
            continue
        ok = sum(1 for r in sub if r["resolved"])
        print(f"  {label:<22} {ok}/{len(sub)} correct")
    for arm in ("A", "B"):
        sub = [r for r in rows if r["batch"] == "b" and r["run"].startswith(arm + "_")]
        ok = sum(1 for r in sub if r["resolved"])
        donor = next((r for r in rows if r["role"] == f"donor {arm}"), None)
        note = f"donor {donor['run']} {'PASS' if donor['resolved'] else 'FAIL'}" if donor else ""
        print(f"    arm {arm}                 {ok}/{len(sub)} correct   ({note})")
    total = sum(1 for r in rows if r["resolved"])
    print(f"\n  overall                {total}/{len(rows)} correct")
    finals = Counter(r["final"] for r in rows)
    print(f"  distinct final states  {len(finals)} across {len(rows)} runs")
    mixed = 0 < total < len(rows)
    print(f"\n  MIXED CORRECTNESS: {mixed}")

    if args.out:
        Path(args.out).write_text(json.dumps(
            {"exploratory": True, "rows": rows,
             "overall_correct": total, "n": len(rows)}, indent=1) + "\n")
        print(f"\nwrote {args.out}")


if __name__ == "__main__":
    main()

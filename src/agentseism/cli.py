"""`seism` — the CLI.

Three commands a developer runs in their own repository:

    seism init        scaffold .agentseism/
    seism baseline    freeze a reusable baseline
    seism check       compare a candidate against it, and say whether to merge

The hard ordering lives here, not in a convention:

    load contract → resolve → load baseline fingerprint → check comparability
      ├── mismatch → INCOMPARABLE, **zero candidate trials**
      └── comparable → run candidate → scorecard → verdict
                          └── REGRESSION → offline RCA → report

Importing this module runs nothing: no agent, no model, no container, no
network. `--dry-run` prints the plan and writes nothing at all.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
import time
from pathlib import Path

from agentseism.contract import Measurement, decide, precheck_comparability
from agentseism.execution import (
    CallableRunner, ShellEvaluator, ShellRunner, fingerprint, run_trials,
)
from agentseism.pr_report import Row, render
from agentseism.resolve import provenance, resolve_and_validate

HOME = ".agentseism"

CONTRACT_TEMPLATE = """# AgentSeism contract. You name the thresholds; the tool
# names the statistics and prints every one of them in the report.
runner:
  type: shell
  command: "python run_agent.py --task {task_file} --out {artifact_dir}"

evaluator:
  command: "python check_result.py {artifact_dir}"

features:
  task_success:     {gate: true,    regression_threshold: 0.10}
  cost_per_success: {gate: warning, regression_threshold: 0.25}
"""

TASKS_TEMPLATE = """# One line per task. Anything your runner understands.
- tasks/example_task.json
"""

EXAMPLE_TASK = """{"id": "example", "prompt": "replace with a real task"}\n"""

GITIGNORE = """
# AgentSeism — baselines are reusable, runs are not
.agentseism/runs/
"""


def _atomic(path: Path, text: str) -> str:
    """Write, fsync, rename, and record a digest beside it.

    An interrupted write must not leave a baseline that looks complete.
    """
    import os
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    with tmp.open("w") as f:
        f.write(text); f.flush(); os.fsync(f.fileno())
    os.replace(tmp, path)
    d = hashlib.sha256(text.encode()).hexdigest()
    Path(str(path) + ".sha256").write_text(f"{d}  {path.name}\n")
    return d


def cmd_init(args) -> int:
    root = Path(args.dir) / HOME
    made, kept = [], []
    for rel, text in ((Path("contract.yaml"), CONTRACT_TEMPLATE),
                      (Path("tasks.yaml"), TASKS_TEMPLATE)):
        p = root / rel
        if p.exists():
            kept.append(str(p)); continue
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text); made.append(str(p))
    for d in ("baselines", "runs"):
        (root / d).mkdir(parents=True, exist_ok=True)
    ex = Path(args.dir) / "tasks/example_task.json"
    if not ex.exists():
        ex.parent.mkdir(parents=True, exist_ok=True)
        ex.write_text(EXAMPLE_TASK); made.append(str(ex))
    gi = Path(args.dir) / ".gitignore"
    if GITIGNORE.strip() not in (gi.read_text() if gi.exists() else ""):
        with gi.open("a") as f:
            f.write(GITIGNORE)
        made.append(f"{gi} (appended)")

    for m in made:
        print(f"  created  {m}")
    for k in kept:
        print(f"  kept     {k}  (existing files are never overwritten)")
    print(f"\nNext: edit {root/'contract.yaml'}, then `seism baseline`.")
    print("Everything stays local. No account, no upload.")
    return 0


def _load(args):
    import yaml
    root = Path(args.dir) / HOME
    surface = yaml.safe_load((root / "contract.yaml").read_text())
    tasks = yaml.safe_load((root / "tasks.yaml").read_text()) or []
    c, s, src = resolve_and_validate(surface, str(root / "contract.yaml"))
    return root, c, s, src, [str(Path(args.dir) / t) for t in tasks]


def _build(surface, args):
    r = surface.get("runner") or {}
    if r.get("type") == "python":
        mod, _, fn = r["callable"].partition(":")
        import importlib
        runner = CallableRunner(getattr(importlib.import_module(mod), fn))
    else:
        runner = ShellRunner(r.get("command", ""),
                             timeout=int(r.get("timeout", 3600)))
    ev = surface.get("evaluator") or {}
    return runner, ShellEvaluator(ev.get("command", ""),
                                  timeout=int(ev.get("timeout", 600)))


def _plan(c, surface, tasks, trials, label) -> int:
    r = surface.get("runner") or {}
    print(f"── {label} plan (dry run — nothing is executed or written) ──")
    print(f"  tasks                {len(tasks)}")
    for t in tasks:
        print(f"    - {t}")
    print(f"  trials per task      {trials}")
    print(f"  total runner calls   {len(tasks) * trials}")
    print(f"  runner               {r.get('type', 'shell')}: "
          f"{r.get('command') or r.get('callable')}")
    print(f"  evaluator            {(surface.get('evaluator') or {}).get('command')}")
    print(f"  gating features      {', '.join(c.gating) or '(none)'}")
    print(f"  comparability        {', '.join(c.require_same)}")
    print(f"  contract             {c.raw['contract_version']} {c.content_sha256}")
    print(f"  verdict authority    {c.raw['verdict_authority']}")
    print("\n  cost: not estimated — AgentSeism does not know what your runner "
          "costs.\n        Supply a price and it will be reported; it will not "
          "be invented.")
    return 0


def cmd_baseline(args) -> int:
    root, c, surface, src, tasks = _load(args)
    if args.dry_run:
        return _plan(c, surface, tasks, args.trials, "baseline")
    runner, ev = _build(surface, args)
    started = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    results = run_trials(runner, ev, tasks, args.trials,
                         root / "runs" / args.name, "baseline",
                         on_progress=lambda r: print(
                             f"  {r.task} trial {r.trial} "
                             f"{'INVALID' if r.invalid else 'ok'} {r.seconds}s"))
    payload = {
        "name": args.name, "arm": "baseline",
        "started": started,
        "finished": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "trials_per_task": args.trials, "tasks": tasks,
        "fingerprint": fingerprint(),
        "runner": surface.get("runner"), "evaluator": surface.get("evaluator"),
        "contract_sha256": c.content_sha256,
        "effective_contract": c.raw, "surface_contract": surface,
        "field_sources": src,
        "results": [r.__dict__ for r in results],
    }
    # Written last, atomically: an interrupted baseline leaves no valid file.
    d = _atomic(root / "baselines" / f"{args.name}.json",
                json.dumps(payload, indent=2, sort_keys=True))
    print(f"\nbaseline '{args.name}' frozen  sha256 {d[:16]}")
    print("No verdict is produced at baseline time.")
    return 0


def _rates(results: list[dict], key: str) -> dict[str, list[float]]:
    """Per-task outcome values, valid runs only."""
    by: dict[str, list[float]] = {}
    for r in results:
        if r.get("invalid"):
            continue
        v = (r.get("outcome") or {}).get(key)
        if v is None:
            continue
        by.setdefault(r["task"], []).append(float(v))
    return by


def _paired_bootstrap(base: dict[str, list[float]], cand: dict[str, list[float]],
                      n: int = 2000, seed: int = 0) -> tuple[float, float, float]:
    """Resample tasks, not runs.

    The task is the independent unit the contract declares; resampling trials
    would treat repeated runs of one task as independent evidence and narrow
    the interval on something that is not there.
    """
    import random
    import statistics as st
    shared = sorted(set(base) & set(cand))
    if not shared:
        return 0.0, 0.0, 0.0
    diffs = [st.mean(cand[t]) - st.mean(base[t]) for t in shared]
    point = st.mean(diffs)
    rng = random.Random(seed)
    boots = [st.mean([diffs[rng.randrange(len(diffs))] for _ in diffs])
             for _ in range(n)]
    boots.sort()
    return point, boots[int(.025 * n)], boots[int(.975 * n) - 1]


def _measure(contract, baseline: dict, candidate: list[dict], tasks: list[str],
             trials: int) -> tuple[dict, dict]:
    """Real arithmetic on real artifacts. Only features we can compute appear.

    A feature the runs do not carry is left out rather than defaulted to zero:
    a missing measurement is not evidence of no change.
    """
    ms, detail = {}, {}
    for name, f in contract.features.items():
        key = {"task_success": "success", "recovery_success": "recovered",
               "cost_per_success": "cost"}.get(name)
        if key is None:
            continue
        b = _rates(baseline["results"], key)
        c = _rates(candidate, key)
        if not (b and c):
            continue
        eff, lo, hi = _paired_bootstrap(b, c)
        ms[name] = Measurement(
            effect=eff, ci_low=lo, ci_high=hi,
            evidence={"scenarios": len(set(b) & set(c)),
                      "trials_per_condition": trials,
                      "eligible_scenarios": len(set(b) & set(c))},
            invalid=sum(1 for r in candidate if r.get("invalid")))
        import statistics as st
        detail[name] = {
            "baseline": st.mean([st.mean(v) for v in b.values()]),
            "candidate": st.mean([st.mean(v) for v in c.values()]),
            "effect": eff, "ci": (lo, hi), "scenarios": len(set(b) & set(c))}
    return ms, detail


def cmd_check(args) -> int:
    root, c, surface, src, tasks = _load(args)
    if args.dry_run:
        return _plan(c, surface, tasks, args.trials, "check")

    bl_path = root / "baselines" / f"{args.baseline}.json"
    if not bl_path.exists():
        print(f"no baseline '{args.baseline}'. Run `seism baseline` first.",
              file=sys.stderr)
        return 2
    baseline = json.loads(bl_path.read_text())

    # Comparability first — before a single candidate call.
    cand_fp = fingerprint()
    incomparable = precheck_comparability(c, baseline["fingerprint"], cand_fp)
    if incomparable:
        v = incomparable
        out = render(v, None,
                     [f"Baseline `{args.baseline}` was recorded "
                      f"{baseline['started']}.",
                      "No candidate trials were run."])
        _atomic(root / "runs" / "last-report.md", out)
        print(out)
        return 1

    runner, ev = _build(surface, args)
    results = run_trials(runner, ev, tasks, args.trials,
                         root / "runs" / "candidate", "candidate",
                         on_progress=lambda r: print(
                             f"  {r.task} trial {r.trial} "
                             f"{'INVALID' if r.invalid else 'ok'} {r.seconds}s"))
    rows_src = [r.__dict__ for r in results]
    ms, detail = _measure(c, baseline, rows_src, tasks, args.trials)
    v = decide(c, baseline["fingerprint"], cand_fp, ms)

    rows = []
    for name, d in detail.items():
        dec = ("REGRESSION" if name in v.get("regressed", []) else
               "WARNING" if name in v.get("warnings", []) else
               "INSUFFICIENT" if name in v.get("insufficient", []) else "PASS")
        rows.append(Row(name.replace("_", " ").capitalize(),
                        f"{d['baseline']:.2f}", f"{d['candidate']:.2f}",
                        f"{d['effect']:+.2f} [{d['ci'][0]:+.2f}, {d['ci'][1]:+.2f}]",
                        dec))
    ev_lines = [
        f"Baseline `{args.baseline}` recorded {baseline['started']}, "
        f"{baseline['trials_per_task']} trials/task.",
        f"Candidate: {args.trials} trials/task over {len(tasks)} task(s).",
        f"Independent unit: scenario. Intervals are paired bootstrap over "
        f"tasks, not over runs.",
    ]
    invalid = sum(1 for r in rows_src if r.get("invalid"))
    if invalid:
        ev_lines.append(f"**{invalid} invalid run(s)** — not scored as failures.")
    out = render(v, rows, ev_lines)
    _atomic(root / "runs" / "last-report.md", out)
    _atomic(root / "runs" / "last-report.json",
            json.dumps({"verdict": v, "detail": detail,
                        "provenance": provenance(c, surface, src)},
                       indent=2, sort_keys=True, default=str))
    print(out)
    return 1 if v["verdict"] == "REGRESSION" else 0


def cmd_diagnose(args) -> int:
    print("`seism diagnose` reads traces from a confirmed REGRESSION. No such "
          "comparison exists yet, and it makes no model calls by design.")
    return 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(
        prog="seism",
        description="AgentSeism — turn stochastic agent runs into trustworthy "
                    "CI decisions.")
    ap.add_argument("--dir", default=".", help="repository root")
    sub = ap.add_subparsers(dest="cmd", required=True)

    sub.add_parser("init", help="scaffold .agentseism/").set_defaults(fn=cmd_init)

    b = sub.add_parser("baseline", help="freeze a reusable baseline")
    b.add_argument("--name", default="main")
    b.add_argument("--trials", type=int, default=5)
    b.add_argument("--dry-run", action="store_true")
    b.set_defaults(fn=cmd_baseline)

    ch = sub.add_parser("check", help="compare a candidate against a baseline")
    ch.add_argument("--baseline", default="main")
    ch.add_argument("--trials", type=int, default=5)
    ch.add_argument("--dry-run", action="store_true")
    ch.set_defaults(fn=cmd_check)

    d = sub.add_parser("diagnose", help="RCA for a confirmed regression")
    d.add_argument("comparison_id", nargs="?")
    d.set_defaults(fn=cmd_diagnose)

    args = ap.parse_args(argv)
    return args.fn(args)


if __name__ == "__main__":
    raise SystemExit(main())

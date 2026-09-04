"""GAIA pilot: 10 tasks x 5 runs (DESIGN.md §25 Week 1).

Deliberately small. Before paying for 500 executions, find out three things:

  1. does the trace come back complete on every run?
  2. does the final answer vary at all?
  3. is there alignable structure -- or does the projection lose most of the
     trajectory?

Only if all three hold does the full 50 x 10 slice make sense.

    python experiments/natural_variation/gaia_pilot.py --app my_module:app
    python experiments/natural_variation/gaia_pilot.py --stub   # offline plumbing check
"""

from __future__ import annotations

import argparse
import importlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT / "src"), str(ROOT)]

from agentseism import scan  # noqa: E402
from agents.gaia import answer_equivalent, build_state, extract_answer, is_correct, outcome  # noqa: E402
from agents.langgraph_adapter import LangGraphAgent  # noqa: E402
from agents.trajectory import OUTCOME_SLOT  # noqa: E402

PILOT_TRIALS = 5
CORE_SLOTS = (
    "intake", "plan", "tool_sequence", "tool_set", "evidence", "n_steps", "final_answer",
)


def load_app(spec: str):
    module_name, _, attr = spec.partition(":")
    module = importlib.import_module(module_name)
    app = getattr(module, attr or "app")
    return app() if callable(app) and not hasattr(app, "invoke") else app


def stub_tasks(n: int) -> list[dict]:
    return [
        {
            "id": f"stub-{i}",
            "input": {"task_id": f"stub-{i}", "question": f"stub question {i}", "file_name": ""},
            "metadata": {"reference_answer": "answer-0"},
        }
        for i in range(n)
    ]


def gaia_tasks(n: int) -> list[dict]:
    from benchmarks.gaia import load_gaia, save_spec, select

    tasks = select(load_gaia(), n)
    print(f"slice spec written to {save_spec(tasks, 'pilot').relative_to(ROOT)}")
    return tasks


def checks(report, tasks) -> dict:
    runs = report.experiment.runs
    ok_runs = [r for r in runs if r.ok]
    run_ok_rate = len(ok_runs) / len(runs) if runs else 0.0

    slot_names = {e.name for r in ok_runs for e in r.events}
    missing_core = [s for s in CORE_SLOTS if s not in slot_names]
    complete_traces = sum(
        1 for r in ok_runs if {e.name for e in r.events} >= set(CORE_SLOTS)
    )
    trace_completeness = complete_traces / len(ok_runs) if ok_runs else 0.0

    varying_tasks = [t for t in report.tasks if t.variation > 0]
    truncated = [
        r for r in ok_runs
        if (r.output or {}).get("trajectory", {}).get("iterations_beyond_projection", 0) > 0
    ]
    truncation_rate = len(truncated) / len(ok_runs) if ok_runs else 0.0
    varying_slots = [w for w in report.weak_points if w.local_variation > 0]

    references = {t["id"]: t.get("metadata", {}).get("reference_answer") for t in tasks}
    graded = [
        (r.task_id, is_correct(r.outcome, references[r.task_id]))
        for r in ok_runs
        if references.get(r.task_id) is not None
    ]
    accuracy = sum(1 for _, c in graded if c) / len(graded) if graded else None

    return {
        "run_ok_rate": run_ok_rate,
        "trace_completeness": trace_completeness,
        "missing_core_slots": missing_core,
        "median_consistency": report.median_consistency,
        "tasks_with_variation": len(varying_tasks),
        "n_tasks": len(report.tasks),
        "truncation_rate": truncation_rate,
        "varying_slots": len(varying_slots),
        "accuracy": accuracy,
    }


def verdict(c: dict) -> tuple[bool, list[str]]:
    reasons = []
    if c["run_ok_rate"] < 0.9:
        reasons.append(f"only {c['run_ok_rate']:.0%} of runs completed -- fix the harness first")
    if c["trace_completeness"] < 1.0 or c["missing_core_slots"]:
        reasons.append(f"traces incomplete (missing {c['missing_core_slots'] or 'slots on some runs'})")
    if c["tasks_with_variation"] == 0:
        reasons.append("no outcome variation at all -- this agent cannot answer RQ1")
    if c["truncation_rate"] > 0.2:
        reasons.append(
            f"{c['truncation_rate']:.0%} of runs exceed the projection window -- "
            "raise max_iterations or the projection is discarding the interesting part"
        )
    return (not reasons, reasons)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--app", help="module:attr of a compiled LangGraph app")
    parser.add_argument("--stub", action="store_true", help="run the offline stub agent")
    parser.add_argument("--tasks", type=int, default=10)
    parser.add_argument("--trials", type=int, default=PILOT_TRIALS)
    args = parser.parse_args()

    if args.stub:
        from agents.stub_react import StubReActApp

        app, tasks, agent_id = StubReActApp(), stub_tasks(args.tasks), "stub-react"
    elif args.app:
        app, tasks, agent_id = load_app(args.app), gaia_tasks(args.tasks), args.app
    else:
        parser.error("pass --app module:attr, or --stub for an offline plumbing check")

    agent = LangGraphAgent(app, build_state=build_state, extract_answer=extract_answer)
    report = scan(
        agent,
        tasks,
        trials=args.trials,
        outcome=outcome,
        comparator=answer_equivalent,
        agent_id=agent_id,
        exclude_slots=(OUTCOME_SLOT,),
        save_to=str(ROOT / "results" / f"gaia_pilot_{_slug(agent_id)}_experiment.json"),
    )
    print(report.render())

    c = checks(report, tasks)
    passed, reasons = verdict(c)

    print("\nWeek 1 pilot checks")
    print("-" * 46)
    print(f"{'runs completed':<32}{c['run_ok_rate']:>12.0%}")
    print(f"{'traces complete':<32}{c['trace_completeness']:>12.0%}")
    print(f"{'median consistency':<32}{c['median_consistency']:>12.2f}")
    print(f"{'tasks with variation':<32}{c['tasks_with_variation']:>9}/{c['n_tasks']}")
    print(f"{'runs past projection window':<32}{c['truncation_rate']:>12.0%}")
    print(f"{'execution points that vary':<32}{c['varying_slots']:>12}")
    if c["accuracy"] is not None:
        print(f"{'accuracy vs reference (context)':<32}{c['accuracy']:>12.0%}")
    print()
    print("VERDICT: proceed to 50 x 10" if passed else "VERDICT: do not scale up yet")
    for reason in reasons:
        print(f"  - {reason}")
    if args.stub:
        print("\nStub agent: this checks the plumbing only. It is not evidence for any hypothesis.")

    out = ROOT / "results" / f"gaia_pilot_{_slug(agent_id)}.json"
    out.write_text(json.dumps({"agent": agent_id, "trials": args.trials, "checks": c,
                               "passed": passed, "reasons": reasons}, indent=2))
    print(f"wrote {out.relative_to(ROOT)}")


def _slug(text: str) -> str:
    return "".join(ch if ch.isalnum() else "_" for ch in text)


if __name__ == "__main__":
    main()

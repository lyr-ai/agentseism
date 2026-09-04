"""GAIA pilot: 10 tasks x 5 runs (DESIGN.md §25 Week 1).

Deliberately small. Before paying for 500 executions, check the five things in
DESIGN-FEATURE-PROJECTION.md §25 -- outcome variation, feature variation,
feature usefulness, comparator sanity, and baseline strength -- and report the
§26 success criteria for the adapter itself.

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

from agentseism import divergence_tables, scan  # noqa: E402
from agentseism.localization import correlation_only  # noqa: E402
from agentseism.features import MISSING, ObservationRole  # noqa: E402
from agents.gaia import answer_equivalent, build_state, extract_answer, is_correct, outcome  # noqa: E402
from agents.langgraph_adapter import LangGraphAgent  # noqa: E402
from agents.trajectory import ReActProjector  # noqa: E402

PILOT_TRIALS = 5
USEFUL_ASSOCIATION = 0.3
NOISY_VARIATION = 0.3


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


def comparator_sanity(tables) -> list[str]:
    """Features whose comparator cannot be telling runs apart (§25)."""
    complaints = []
    seen: dict[str, list[float]] = {}
    distinct: dict[str, set] = {}
    for columns, pairs in tables.values():
        for column in columns:
            values = [v for v in column.values.values() if v is not MISSING]
            distinct.setdefault(column.name, set()).update(
                repr(v) for v in values
            )
        for pair in pairs:
            for name, d in pair.features.items():
                seen.setdefault(name, []).append(d)
    for name, divergences in seen.items():
        n_distinct = len(distinct.get(name, ()))
        if n_distinct > 1 and max(divergences) == 0.0:
            complaints.append(f"{name}: values differ but divergence is always 0 (comparator too loose)")
        if n_distinct == 1 and min(divergences) > 0.0:
            complaints.append(f"{name}: identical values scored as different (comparator too strict)")
    return complaints


def checks(report, tasks) -> dict:
    runs = report.experiment.runs
    ok_runs = [r for r in runs if r.ok]
    schema = report.schema
    declared = [s.name for s in schema.specs if s.role is ObservationRole.FEATURE] if schema else []

    complete = sum(1 for r in ok_runs if all(n in r.features for n in declared))
    loop_lengths = {
        r.features["tool_call_count"].value for r in ok_runs if "tool_call_count" in r.features
    }

    weak = report.weak_points
    varying = [w for w in weak if w.local_variation > 0]
    useful = [w for w in weak if w.outcome_association >= USEFUL_ASSOCIATION]
    noisy_but_inconsequential = [
        w for w in weak
        if w.local_variation >= NOISY_VARIATION and w.outcome_association < USEFUL_ASSOCIATION
    ]

    tables = divergence_tables(
        report.experiment, comparator=answer_equivalent, schema=schema
    )
    # §22: compare within a scoring group. Positioned features and aggregates
    # are scored by different formulas, so a merged top-3 would compare nothing.
    correlation = correlation_only(tables, schema) if tables else []
    groups = {
        "positioned": [w.name for w in report.ranking.positioned] if report.ranking else [],
        "aggregate": [w.name for w in report.ranking.aggregates] if report.ranking else [],
    }
    comparison = {}
    for group, ours in groups.items():
        if not ours:
            continue
        theirs = [n for n in correlation if n in set(ours)]
        comparison[group] = {
            "agentseism": ours[:3],
            "correlation": theirs[:3],
            "matches": ours[:3] == theirs[:3],
        }

    references = {t["id"]: t.get("metadata", {}).get("reference_answer") for t in tasks}
    graded = [
        is_correct(r.outcome, references[r.task_id])
        for r in ok_runs
        if references.get(r.task_id) is not None
    ]

    return {
        "run_ok_rate": len(ok_runs) / len(runs) if runs else 0.0,
        "feature_completeness": complete / len(ok_runs) if ok_runs else 0.0,
        "distinct_loop_lengths": len(loop_lengths),
        "median_consistency": report.median_consistency,
        "tasks_with_variation": sum(1 for t in report.tasks if t.variation > 0),
        "n_tasks": len(report.tasks),
        "features_that_vary": len(varying),
        "features_associated_with_outcome": len(useful),
        "max_association": max((w.outcome_association for w in weak), default=0.0),
        "noisy_but_inconsequential": [w.name for w in noisy_but_inconsequential],
        "comparator_complaints": comparator_sanity(tables),
        "baseline_comparison": comparison,
        "correlation_matches_us": [g for g, c in comparison.items() if c["matches"]],
        "accuracy": sum(graded) / len(graded) if graded else None,
    }


def verdict(c: dict) -> tuple[bool, list[str]]:
    """§26: what makes the adapter useful. Not causal attribution."""
    reasons = []
    if c["run_ok_rate"] < 0.9:
        reasons.append(f"only {c['run_ok_rate']:.0%} of runs completed -- fix the harness first")
    if c["feature_completeness"] < 1.0:
        reasons.append(
            f"only {c['feature_completeness']:.0%} of runs produced every declared feature"
        )
    if c["distinct_loop_lengths"] < 2:
        reasons.append("loop length never varies -- this agent may be too deterministic to study")
    if c["tasks_with_variation"] == 0:
        reasons.append("no outcome variation at all -- this agent cannot answer RQ1")
    if c["features_associated_with_outcome"] == 0:
        reasons.append("no execution feature relates to outcome variation -- the schema may be wrong")
    if not c["noisy_but_inconsequential"]:
        reasons.append(
            "every high-variation feature also has high outcome association -- "
            "no discrimination yet, so the ranking may just be tracking whatever changes most"
        )
    if c["comparator_complaints"]:
        reasons.append(f"comparator problems: {'; '.join(c['comparator_complaints'])}")
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
        projector=ReActProjector(),
        agent_id=agent_id,
        save_to=str(ROOT / "results" / f"gaia_pilot_{_slug(agent_id)}_experiment.json"),
    )
    print(report.render())

    c = checks(report, tasks)
    passed, reasons = verdict(c)

    print("\nWeek 1 pilot checks")
    print("-" * 46)
    print(f"{'runs completed':<34}{c['run_ok_rate']:>12.0%}")
    print(f"{'runs with every feature':<34}{c['feature_completeness']:>12.0%}")
    print(f"{'distinct loop lengths':<34}{c['distinct_loop_lengths']:>12}")
    print(f"{'median consistency':<34}{c['median_consistency']:>12.2f}")
    print(f"{'tasks with variation':<34}{c['tasks_with_variation']:>9}/{c['n_tasks']}")
    print(f"{'features that vary':<34}{c['features_that_vary']:>12}")
    print(f"{'features tied to the outcome':<34}{c['features_associated_with_outcome']:>12}")
    print(f"{'noisy but inconsequential':<34}{', '.join(c['noisy_but_inconsequential']) or '-':>12}")
    if c["accuracy"] is not None:
        print(f"{'accuracy vs reference (context)':<34}{c['accuracy']:>12.0%}")
    print()
    for group, comp in c["baseline_comparison"].items():
        print(f"[{group}] AgentSeism  {comp['agentseism']}")
        print(f"[{group}] correlation {comp['correlation']}")
    for group in c["correlation_matches_us"]:
        print(
            f"Correlation-only already reproduces our {group} ranking (§22 risk)."
        )
    print()
    print("VERDICT: proceed to 50 x 10" if passed else "VERDICT: do not scale up yet")
    for reason in reasons:
        print(f"  - {reason}")
    if args.stub:
        print("\nStub agent: plumbing check only. Not evidence for any hypothesis.")

    out = ROOT / "results" / f"gaia_pilot_{_slug(agent_id)}.json"
    out.write_text(
        json.dumps(
            {
                "agent": agent_id,
                "trials": args.trials,
                "feature_schema_version": report.schema.version if report.schema else None,
                "checks": c,
                "passed": passed,
                "reasons": reasons,
            },
            indent=2,
        )
    )
    print(f"wrote {out.relative_to(ROOT)}")


def _slug(text: str) -> str:
    return "".join(ch if ch.isalnum() else "_" for ch in text)


if __name__ == "__main__":
    main()

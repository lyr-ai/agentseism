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
from agentseism.variation import consistency  # noqa: E402
from agents import gaia, gaia_markazhang  # noqa: E402
from agents.gaia import answer_equivalent, is_correct  # noqa: E402
from agents.langgraph_adapter import LangGraphAgent  # noqa: E402
from agents.trajectory import ReActProjector  # noqa: E402

ADAPTERS = {
    # The multi-node GAIA agent (github.com/MarkAZhang/gaia-agent). Streams,
    # because its memory_management node rewrites tool results in the state.
    "gaia-graph": {
        "projector": gaia_markazhang.GaiaGraphProjector,
        "build_state": gaia_markazhang.make_build_state,
        "extract_answer": gaia_markazhang.extract_answer,
        "outcome": gaia_markazhang.outcome,
        "stub": "agents.stub_gaia_graph:StubGaiaGraphApp",
    },
    # A plain ReAct loop with no post-processing nodes.
    "react": {
        "projector": ReActProjector,
        "build_state": lambda: gaia.build_state,
        "extract_answer": gaia.extract_answer,
        "outcome": gaia.outcome,
        "stub": "agents.stub_react:StubReActApp",
    },
}

PILOT_TRIALS = 5
USEFUL_ASSOCIATION = 0.3
NOISY_VARIATION = 0.3


def load_attr(spec: str):
    module_name, _, attr = spec.partition(":")
    module = importlib.import_module(module_name)
    return getattr(module, attr)


def load_app(spec: str):
    app = load_attr(spec) if ":" in spec else importlib.import_module(spec).app
    if callable(app) and not (hasattr(app, "invoke") or hasattr(app, "stream")):
        app = app()
    return app


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
    from benchmarks.gaia import check_access, load_gaia, save_spec, select

    ok, message = check_access()
    if not ok:
        raise SystemExit(f"GAIA access: {message}")
    print(f"GAIA access: {message}")

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


def diagnostics(report) -> dict:
    """Answer-level context: is the output formatter removing or adding variation?

    Kept out of localization -- both answers are declared outcomes -- but worth
    watching: a formatter that erases agent variation, or manufactures it, is an
    empirical finding either way.
    """
    raw, formatted, changed = [], [], []
    for task in report.tasks:
        runs = report.experiment.runs_for(task.task_id)
        raw_values = [
            r.features["raw_final_answer"].value for r in runs if "raw_final_answer" in r.features
        ]
        if len(raw_values) > 1:
            raw.append(consistency(raw_values, answer_equivalent))
            formatted.append(task.consistency)
    for run in report.experiment.runs:
        if run.ok and "formatter_changed_answer" in run.features:
            changed.append(bool(run.features["formatter_changed_answer"].value))

    if not raw:
        return {}
    return {
        "raw_answer_consistency": sum(raw) / len(raw),
        "formatted_answer_consistency": sum(formatted) / len(formatted),
        "formatter_changed_rate": (sum(changed) / len(changed)) if changed else None,
    }


def inspect_runs(report, limit: int = 2) -> None:
    """Print raw trace next to projected values, for manual verification.

    Two things need a human eye once, before any number is trusted: that
    `evidence_set` holds tool output rather than a serialized wrapper, and that
    `answer_format_retries` really counts format rejections.
    """
    ok_runs = [r for r in report.experiment.runs if r.ok][:limit]
    for run in ok_runs:
        print("\n" + "=" * 60)
        print(f"RAW TRACE vs PROJECTION — run {run.id}")
        print("=" * 60)

        print("\nraw `tools` events:")
        for event in run.events:
            if event.name == "tools":
                print(f"  [{event.metadata.get('role')}] {event.input} -> {_clip(event.output)}")
        evidence = run.features.get("evidence_set")
        print(f"projected evidence_set ({len(evidence.value) if evidence else 0}):")
        for item in (evidence.value if evidence else []):
            print(f"  {_clip(item)}")

        print("\nraw `check_and_get_final_answer` events:")
        for event in run.events:
            if event.name == "check_and_get_final_answer":
                print(f"  [{event.metadata.get('role')}] {_clip(event.output)}")
        for name in ("answer_format_retries", "raw_final_answer", "final_answer",
                     "formatter_changed_answer", "termination"):
            if name in run.features:
                print(f"projected {name:<26}{_clip(run.features[name].value)}")


def _clip(value, width: int = 90) -> str:
    text = str(value).replace("\n", " ")
    return text if len(text) <= width else text[: width - 1] + "…"


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

    # Projection windows: only some projectors summarise a bounded number of
    # iterations. Report the rate where it applies, and None where the concept
    # does not exist, rather than a zero that reads like "nothing was dropped".
    windowed = [
        r for r in ok_runs
        if "iterations_beyond_projection" in (r.output or {}).get("trajectory", {})
    ]
    truncated = [
        r for r in windowed if r.output["trajectory"]["iterations_beyond_projection"] > 0
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
        "past_projection_window": (len(truncated) / len(windowed)) if windowed else None,
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
    parser.add_argument(
        "--adapter", choices=sorted(ADAPTERS), default="gaia-graph",
        help="which agent shape to project (default: the multi-node GAIA graph)",
    )
    parser.add_argument(
        "--system-prompt",
        help="module:attr of the agent repo's own build_system_prompt(file_path)",
    )
    parser.add_argument("--tasks", type=int, default=10)
    parser.add_argument("--trials", type=int, default=PILOT_TRIALS)
    parser.add_argument(
        "--inspect", type=int, default=2, metavar="N",
        help="print raw trace next to projected values for N runs (0 to skip)",
    )
    args = parser.parse_args()

    adapter = ADAPTERS[args.adapter]
    if args.stub:
        app = load_app(adapter["stub"])()
        tasks, agent_id = stub_tasks(args.tasks), f"stub-{args.adapter}"
    elif args.app:
        app, tasks, agent_id = load_app(args.app), gaia_tasks(args.tasks), args.app
    else:
        parser.error("pass --app module:attr, or --stub for an offline plumbing check")

    build_state = adapter["build_state"]
    if args.adapter == "gaia-graph":
        build_state = build_state(
            load_attr(args.system_prompt) if args.system_prompt else None
        )
        if not args.system_prompt and not args.stub:
            print(
                "warning: no --system-prompt given, so the agent runs with a generic "
                "prompt instead of its own. That changes what is being measured."
            )
    else:
        build_state = build_state()

    agent = LangGraphAgent(
        app, build_state=build_state, extract_answer=adapter["extract_answer"]
    )
    report = scan(
        agent,
        tasks,
        trials=args.trials,
        outcome=adapter["outcome"],
        comparator=answer_equivalent,
        projector=adapter["projector"](),
        agent_id=agent_id,
        save_to=str(ROOT / "results" / f"gaia_pilot_{_slug(agent_id)}_experiment.json"),
    )
    print(report.render())

    c = checks(report, tasks)
    d = diagnostics(report)
    passed, reasons = verdict(c)

    if args.inspect:
        inspect_runs(report, args.inspect)

    print("\nWeek 1 pilot checks")
    print("-" * 46)
    window = c["past_projection_window"]
    changed = d.get("formatter_changed_rate")
    print(f"{'1. runs completed':<34}{c['run_ok_rate']:>12.0%}")
    print(f"{'2. traces complete':<34}{c['feature_completeness']:>12.0%}")
    print(f"{'3. median outcome consistency':<34}{c['median_consistency']:>12.2f}")
    print(f"{'4. tasks with variation':<34}{c['tasks_with_variation']:>9}/{c['n_tasks']}")
    print(
        f"{'5. runs past projection window':<34}"
        + (f"{window:>12.0%}" if window is not None else f"{'n/a':>12}")
    )
    print(
        f"{'6. formatter changed answer':<34}"
        + (f"{changed:>12.0%}" if changed is not None else f"{'n/a':>12}")
    )
    print()
    print(f"{'distinct loop lengths':<34}{c['distinct_loop_lengths']:>12}")
    print(f"{'features that vary':<34}{c['features_that_vary']:>12}")
    print(f"{'features tied to the outcome':<34}{c['features_associated_with_outcome']:>12}")
    print(f"{'noisy but inconsequential':<34}{', '.join(c['noisy_but_inconsequential']) or '-':>12}")
    if c["accuracy"] is not None:
        print(f"{'accuracy vs reference (context)':<34}{c['accuracy']:>12.0%}")

    if d:
        print("\nAnswer-level diagnostics (context, not localization)")
        print(f"{'raw answer consistency':<34}{d['raw_answer_consistency']:>12.2f}")
        print(f"{'formatted answer consistency':<34}{d['formatted_answer_consistency']:>12.2f}")
        gap = d["formatted_answer_consistency"] - d["raw_answer_consistency"]
        if gap > 0.05:
            print("  → the output formatter is REMOVING agent variation")
        elif gap < -0.05:
            print("  → the output formatter is INTRODUCING variation of its own")
    print()
    for group, comp in c["baseline_comparison"].items():
        print(f"[{group}] AgentSeism  {comp['agentseism']}")
        print(f"[{group}] correlation {comp['correlation']}")
    for group in c["correlation_matches_us"]:
        print(
            f"Correlation-only already reproduces our {group} ranking (§22 risk)."
        )
    print(
        "\n10 x 5 is too small for a method comparison. What decides go/no-go is\n"
        "whether real behavioral variation exists and propagates with structure."
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
                "diagnostics": d,
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
